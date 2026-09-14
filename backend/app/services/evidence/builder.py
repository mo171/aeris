"""Turns what a stage measured into what an operator can click: layers, the evidence records they draw, and the claims that rest on them.

what  : `build_raster_layer()` - a tile layer over a retained COG; `build_region_evidence()` - a thresholded
        mask as a raster-mask layer *and* a polygon layer, its evidence items, and its claims;
        `build_detection_evidence()` (1.10) - a detector's oriented boxes as a polygon layer, one evidence
        record per class, and a count claim per class asked for.
where : S15 (`services/pipeline/nodes/evidence_localisation.py`, and from 1.10 the detection, class and
        change localisers) and S12 (`feature_extraction.py`). The geometry is
        `segmentation/math/vectorize.py` and `evidence/math/`; this file contains none of it.
how   : `architecture-context.md` invariant 14: every mask is produced in both representations. Raster
        tiles for display - every pixel, through TiTiler - and polygons for evidence, because a raster is a
        picture and a polygon is what makes a claim clickable. Both carry the same provenance.

        **Every claim resolves to pixels, by construction.** A claim points at evidence ids; every evidence
        item points at a layer and the features on it; every feature is a ring of ground the mask marked.
        The builder mints all three in one place so the chain cannot be assembled with a link missing, and
        `tests/integration/test_evidence.py` walks it back from a claim to the raster.

        **The number a claim quotes is the measurement, not the drawing.** `MINIMUM_FEATURE_REGION_PIXELS`
        bounds the vector payload - thousands of one-pixel rings serve nobody - but the hectares on the
        evidence and in the claim are the whole mask's, from `services/evidence/spatial.py`. The title says
        how many regions were drawn of how many were counted.

        **An empty mask is a negative claim, not an empty result.** "No sparse vegetation was detected in
        the observed ground" is a finding with evidence behind it (`ClaimKind.NEGATIVE`); silence would be
        indistinguishable from not having looked.

        Confidence is `None` for the index and geospatial engines, which are deterministic and decline to
        assert a probability (`architecture-context.md` §8 rule 10). A specialist that states one
        (a detector's score, a change model's mean winning probability) passes it in and it travels on the
        claim, the evidence and the layer alike.

        **A picture with no grid gets claims and no layers** (1.10). Nothing is placed on the globe because
        there is no ground to place it on; the evidence records carry `layerId: null` like a statistic
        does, and the numbers are pixels, or hectares labelled nominal when the operator declared a pixel
        size. That is the honest form for a benchmark crop or a photograph, and it is the same builder, so
        a claim over a picture has the same shape as one over a scene.
"""

import asyncio
import math
from dataclasses import dataclass

import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import Polygon

from app.constants.color_ramps import ColorRampId
from app.constants.evidence import (
    COUNT_PRECISION,
    HECTARES_PRECISION,
    INDEX_VALUE_PRECISION,
    MAXIMUM_METRIC_PRECISION,
    MINIMUM_FEATURE_REGION_PIXELS,
    PERCENTAGE_PRECISION,
    POLYGON_SIMPLIFICATION_TOLERANCE_METRES,
    SCORE_PRECISION,
    ClaimKind,
    EvidenceKind,
    MetricDirection,
)
from app.constants.geo import SQUARE_METRES_PER_HECTARE
from app.constants.layers import REGION_LAYER_OPACITY, ComparatorSide, LayerKind, LayerRenderMode
from app.constants.licences import COPERNICUS_ATTRIBUTION
from app.constants.model_ids import ModelId
from app.constants.spectral import GEOSPATIAL_ENGINE_VERSION
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.lib.tiles import xyz_template
from app.schemas.events import (
    Claim,
    ClaimMetric,
    EvidenceFeature,
    EvidenceItem,
    EvidenceLayer,
    LayerProvenance,
    PolygonGeometry,
    ValueDomain,
)
from app.schemas.geo import GeoBoundingBox, GeoPoint
from app.services.detection.math.oriented_boxes import OrientedBox
from app.services.evidence.math.area import polygon_area
from app.services.evidence.math.simplification import outer_ring_geographic, simplify_outline
from app.services.evidence.spatial import MaskStatistics
from app.services.imagery.math.web_mercator import geographic_bounds, zoom_range
from app.services.segmentation.math.vectorize import label_regions, region_means, vectorise_regions

type AffineTransform = tuple[float, float, float, float, float, float]


def hectares_precision_for(resolution_metres: float | None) -> int:
    """Decimals of a hectare figure such that the last one is about one pixel: 1 at 10 m, 4 at 0.5 m.

    `HECTARES_PRECISION` is the value at 10 m and the floor; the contract's ceiling is 4. Unknown
    resolution gets the floor, because nothing finer can be claimed about it.
    """
    if resolution_metres is None or resolution_metres <= 0:
        return HECTARES_PRECISION
    pixel_hectares = resolution_metres**2 / SQUARE_METRES_PER_HECTARE
    decimals = math.ceil(-math.log10(pixel_hectares)) - 1
    return max(HECTARES_PRECISION, min(MAXIMUM_METRIC_PRECISION, decimals))


@dataclass(frozen=True, slots=True)
class GridExtent:
    """Where a grid sits on the globe and which zooms show it. One computation per raster layer."""

    bounds: GeoBoundingBox
    minimum_zoom: int
    maximum_zoom: int


async def grid_extent(
    transform: AffineTransform, crs: str, shape: tuple[int, int], resolution_metres: float
) -> GridExtent:
    bounds = await asyncio.to_thread(geographic_bounds, transform, crs, shape)
    minimum, maximum = await asyncio.to_thread(zoom_range, bounds, resolution_metres)
    west, south, east, north = bounds
    return GridExtent(GeoBoundingBox(west=west, south=south, east=east, north=north), minimum, maximum)


async def build_raster_layer(
    *,
    title: str,
    kind: LayerKind,
    overlay_id: str | None,
    storage_uri: str,
    extent: GridExtent,
    color_ramp_id: ColorRampId,
    opacity: float,
    provenance: LayerProvenance,
    value_domain: ValueDomain | None = None,
    rendering: dict[str, str] | None = None,
) -> EvidenceLayer:
    """A draped tile layer over a COG in storage. The browser does no band math: the template carries it."""
    return EvidenceLayer(
        id=new_identifier(IdentifierPrefix.LAYER),
        kind=kind,
        render_mode=LayerRenderMode.DRAPED,
        title=title,
        overlay_id=overlay_id,
        value_domain=value_domain,
        color_ramp_id=color_ramp_id,
        opacity=opacity,
        is_visible=True,
        comparator_side=ComparatorSide.BOTH,
        tile_url_template=xyz_template(storage_uri, **(rendering or {})),
        attribution=COPERNICUS_ATTRIBUTION,
        bounds=extent.bounds,
        minimum_zoom=extent.minimum_zoom,
        maximum_zoom=extent.maximum_zoom,
        features=[],
        provenance=provenance,
    )


@dataclass(frozen=True, slots=True)
class _FeatureDraft:
    label: int
    pixel_count: int
    square_metres: float
    mean_value: float | None
    ring: list[tuple[float, float]]


@dataclass(frozen=True, slots=True)
class RegionEvidence:
    """Everything S15 emits for one thresholded mask, in the order it is emitted. The layers are `None`
    for a picture with no grid: nothing to drape, nothing to extrude."""

    raster_layer: EvidenceLayer | None
    vector_layer: EvidenceLayer | None
    evidence: list[EvidenceItem]
    claims: list[Claim]
    regions_total: int
    regions_drawn: int
    # Original connected-component label -> vector feature id. Consumers which partition a branch mask
    # later can retain precise references instead of repeating the class-wide evidence list.
    feature_ids_by_region_label: dict[int, str]

    @property
    def layers(self) -> list[EvidenceLayer]:
        return [layer for layer in (self.raster_layer, self.vector_layer) if layer is not None]


async def build_region_evidence(
    detected: np.ndarray,
    values: np.ndarray,
    *,
    statistics: MaskStatistics,
    transform: AffineTransform,
    crs: str | None,
    resolution_metres: float | None,
    run_id: str,
    trace_step_id: str,
    scene_id: str,
    mask_storage_uri: str | None,
    index_label: str,
    quantity_label: str,
    region_label: str,
    lower: float,
    upper: float,
    obscured_fraction: float | None,
    unphysical_fraction: float,
    model_id: ModelId = ModelId.GEOSPATIAL_ENGINE,
    model_version: str = GEOSPATIAL_ENGINE_VERSION,
    confidence: float | None = None,
    evidence_kind: EvidenceKind = EvidenceKind.INDEX_MAP,
    value_label: str | None = None,
    nominal_resolution: bool = False,
) -> RegionEvidence:
    """Both representations of one mask, the records that point at them, and the claims that rest on those.

    `obscured_fraction` and `unphysical_fraction` become metrics on the primary claim, because the answer
    states them as caveats and every number the answer speaks must be on a claim (invariant 15).

    `crs=None` is a picture: no layers, no features, claims in pixels or in nominal hectares (when
    `nominal_resolution`, the operator declared the pixel size and `statistics` was measured at it).
    `model_id`, `model_version` and `confidence` name who produced the mask and how sure they were - the
    geospatial engine by default, a specialist (1.10) when one did.
    """
    provenance = LayerProvenance(
        model_id=model_id.value, model_version=model_version, trace_step_id=trace_step_id, confidence=confidence,
    )
    features: list[EvidenceFeature] = []
    raster_layer: EvidenceLayer | None = None
    vector_layer: EvidenceLayer | None = None
    drafts: list[_FeatureDraft] = []
    regions_total = statistics.regions.region_count
    mean_label = value_label or f"Mean {index_label}"
    decimals = hectares_precision_for(resolution_metres)

    if crs is not None and resolution_metres is not None:
        extent = await grid_extent(transform, crs, detected.shape, resolution_metres)
        drafts, regions_total = await asyncio.to_thread(
            _draft_features, detected, values, transform, crs, statistics.equal_area_crs
        )
        largest = max((draft.square_metres for draft in drafts), default=0.0)
        features = [
            EvidenceFeature(
                id=new_identifier(IdentifierPrefix.FEATURE),
                label=f"{region_label} region {index + 1}",
                geometry=PolygonGeometry(ring=[GeoPoint(latitude=lat, longitude=lon) for lon, lat in draft.ring]),
                magnitude=draft.square_metres / largest if largest else 0.0,
                confidence=confidence,
                area_hectares=draft.square_metres / SQUARE_METRES_PER_HECTARE,
                value=draft.mean_value,
                class_id=None,
            )
            for index, draft in enumerate(drafts)
        ]
        if mask_storage_uri is not None:
            raster_layer = await build_raster_layer(
                title=f"{region_label} mask",
                kind=LayerKind.RASTER_MASK,
                overlay_id=None,
                storage_uri=mask_storage_uri,
                extent=extent,
                color_ramp_id=ColorRampId.MASK_AMBER,
                opacity=REGION_LAYER_OPACITY,
                provenance=provenance,
                rendering={"rescale": "0,1"},
            )
        vector_layer = EvidenceLayer(
            id=new_identifier(IdentifierPrefix.LAYER),
            kind=LayerKind.POLYGON_VECTOR,
            render_mode=LayerRenderMode.EXTRUDED,
            title=f"{region_label} regions ({len(features)} of {regions_total} drawn)",
            overlay_id=None,
            value_domain=ValueDomain(minimum=lower, maximum=upper),
            color_ramp_id=ColorRampId.MASK_AMBER,
            opacity=REGION_LAYER_OPACITY,
            is_visible=True,
            comparator_side=ComparatorSide.BOTH,
            tile_url_template=None,
            attribution=COPERNICUS_ATTRIBUTION,
            bounds=extent.bounds,
            minimum_zoom=None,
            maximum_zoom=None,
            features=features,
            provenance=provenance,
        )

    has_area = statistics.has_area
    hectares = statistics.detected.hectares if has_area else None
    observed_hectares = statistics.observed.hectares if has_area else None
    coverage = statistics.coverage_fraction
    region_count = statistics.regions.region_count

    regions_item = EvidenceItem(
        id=new_identifier(IdentifierPrefix.EVIDENCE),
        kind=evidence_kind,
        title=f"{region_label} regions",
        layer_id=vector_layer.id if vector_layer else None,
        feature_ids=[feature.id for feature in features],
        area_hectares=hectares,
        magnitude=coverage,
        confidence=confidence,
        source_scene_ids=[scene_id],
    )
    measurement_item = EvidenceItem(
        id=new_identifier(IdentifierPrefix.EVIDENCE),
        kind=EvidenceKind.STATISTIC,
        title=f"{region_label} {'area' if has_area else 'extent'} over observed ground",
        layer_id=None,
        feature_ids=[],
        area_hectares=hectares,
        magnitude=coverage,
        confidence=confidence,
        source_scene_ids=[scene_id],
    )
    evidence = [regions_item, measurement_item]

    neutral = MetricDirection.NEUTRAL
    if has_area:
        assert hectares is not None and observed_hectares is not None
        nominal_suffix = " (nominal)" if nominal_resolution else ""
        metrics = [
            ClaimMetric(label=f"Area{nominal_suffix}", value=hectares, unit="ha", direction=neutral, precision=decimals),
            ClaimMetric(
                label="Share of observed ground", value=coverage * 100.0, unit="%", direction=neutral,
                precision=PERCENTAGE_PRECISION,
            ),
            ClaimMetric(label="Regions", value=float(region_count), unit="", direction=neutral, precision=COUNT_PRECISION),
            ClaimMetric(
                label=f"Observed ground{nominal_suffix}", value=observed_hectares, unit="ha", direction=neutral, precision=decimals
            ),
        ]
        if nominal_resolution and resolution_metres is not None:
            metrics.append(ClaimMetric(label="Declared ground sample distance", value=resolution_metres, unit="m", direction=neutral, precision=2))
    else:
        metrics = [
            ClaimMetric(label="Pixels", value=float(statistics.detected.pixel_count), unit="px", direction=neutral, precision=COUNT_PRECISION),
            ClaimMetric(label="Share of observed pixels", value=coverage * 100.0, unit="%", direction=neutral, precision=PERCENTAGE_PRECISION),
            ClaimMetric(label="Regions", value=float(region_count), unit="", direction=neutral, precision=COUNT_PRECISION),
            ClaimMetric(label="Observed pixels", value=float(statistics.observed.pixel_count), unit="px", direction=neutral, precision=COUNT_PRECISION),
        ]
    if obscured_fraction is not None:
        metrics.append(
            ClaimMetric(
                label="Obscured by cloud and shadow", value=obscured_fraction * 100.0, unit="%",
                direction=neutral, precision=PERCENTAGE_PRECISION,
            )
        )
    if unphysical_fraction > 0.0:
        metrics.append(
            ClaimMetric(
                label="Refused by the formula", value=unphysical_fraction * 100.0, unit="%",
                direction=neutral, precision=PERCENTAGE_PRECISION,
            )
        )
    nominal = f" (nominal, at {resolution_metres:g} m per pixel)" if nominal_resolution and has_area else ""
    if region_count == 0:
        observed_text = (
            f"{observed_hectares:,.{decimals}f} hectares{nominal}" if has_area
            else f"{statistics.observed.pixel_count:,} pixels"
        )
        text = f"No {region_label.lower()} ({quantity_label}) was detected in the {observed_text} observed of {scene_id}."
        kind = ClaimKind.NEGATIVE
    elif has_area:
        text = (
            f"{region_label} ({quantity_label}) covers {hectares:,.{decimals}f} hectares of {scene_id}{nominal}: "
            f"{coverage:.{PERCENTAGE_PRECISION}%} of the {observed_hectares:,.{decimals}f} hectares "
            f"observed, in {region_count:,} regions."
        )
        kind = ClaimKind.QUANTITATIVE
    else:
        text = (
            f"{region_label} ({quantity_label}) covers {statistics.detected.pixel_count:,} pixels of {scene_id}: "
            f"{coverage:.{PERCENTAGE_PRECISION}%} of the {statistics.observed.pixel_count:,} pixels observed, "
            f"in {region_count:,} regions; no ground size is known for this picture."
        )
        kind = ClaimKind.QUANTITATIVE
    claims = [
        Claim(
            id=new_identifier(IdentifierPrefix.CLAIM),
            run_id=run_id,
            text=text,
            kind=kind,
            confidence=confidence,
            metrics=metrics,
            evidence_ids=[regions_item.id, measurement_item.id],
            model_id=model_id,
            model_version=model_version,
            trace_step_id=trace_step_id,
            is_primary=True,
        )
    ]

    if features and vector_layer is not None:
        largest_feature = features[0]
        largest_item = EvidenceItem(
            id=new_identifier(IdentifierPrefix.EVIDENCE),
            kind=evidence_kind,
            title=f"Largest {region_label.lower()} region",
            layer_id=vector_layer.id,
            feature_ids=[largest_feature.id],
            area_hectares=largest_feature.area_hectares,
            magnitude=1.0,
            confidence=confidence,
            source_scene_ids=[scene_id],
        )
        evidence.append(largest_item)
        largest_hectares = largest_feature.area_hectares or 0.0
        largest_metrics = [
            ClaimMetric(label="Area", value=largest_hectares, unit="ha", direction=neutral, precision=decimals),
        ]
        reading = ""
        if largest_feature.value is not None:
            largest_metrics.append(
                ClaimMetric(
                    label=mean_label, value=largest_feature.value, unit="",
                    direction=MetricDirection.NEUTRAL, precision=INDEX_VALUE_PRECISION,
                )
            )
            reading = f", with a {mean_label[0].lower() + mean_label[1:]} of {largest_feature.value:.{INDEX_VALUE_PRECISION}f}"
        claims.append(
            Claim(
                id=new_identifier(IdentifierPrefix.CLAIM),
                run_id=run_id,
                text=f"The largest contiguous region covers {largest_hectares:,.{decimals}f} hectares{reading}.",
                kind=ClaimKind.SPATIAL,
                confidence=confidence,
                metrics=largest_metrics,
                evidence_ids=[largest_item.id],
                model_id=model_id,
                model_version=model_version,
                trace_step_id=trace_step_id,
                is_primary=False,
            )
        )

    feature_ids_by_region_label = {
        draft.label: feature.id for draft, feature in zip(drafts, features, strict=True)
    }
    return RegionEvidence(
        raster_layer=raster_layer,
        vector_layer=vector_layer,
        evidence=evidence,
        claims=claims,
        regions_total=regions_total,
        regions_drawn=len(features),
        feature_ids_by_region_label=feature_ids_by_region_label,
    )


def _draft_features(
    detected: np.ndarray,
    values: np.ndarray,
    transform: AffineTransform,
    crs: str,
    equal_area_crs: str,
) -> tuple[list[_FeatureDraft], int]:
    """Label, vectorise, measure, simplify and project - sync, for `to_thread`. Largest region first."""
    labels, count = label_regions(detected)
    regions = vectorise_regions(labels, transform)
    means = region_means(labels, values, count)

    drafts = []
    for region in regions:
        if region.pixel_count < MINIMUM_FEATURE_REGION_PIXELS:
            continue
        square_metres = polygon_area(region.geometry, crs=crs, equal_area_crs=equal_area_crs)
        outline = simplify_outline(region.geometry, POLYGON_SIMPLIFICATION_TOLERANCE_METRES)
        mean = float(means[region.label - 1])
        drafts.append(
            _FeatureDraft(
                label=region.label,
                pixel_count=region.pixel_count,
                square_metres=square_metres,
                mean_value=mean if np.isfinite(mean) else None,
                ring=outer_ring_geographic(outline, crs=crs),
            )
        )
    drafts.sort(key=lambda draft: draft.square_metres, reverse=True)
    return drafts, count


# --- Detections (1.10) --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DetectionEvidence:
    """Everything S15 emits for a detector's boxes: the layer (georeferenced input only), the evidence
    records per class, and the claims. `counts` is boxes kept per class, for the trace and the record."""

    layer: EvidenceLayer | None
    evidence: list[EvidenceItem]
    claims: list[Claim]
    counts: dict[str, int]


def plural_of(class_name: str, count: int) -> str:
    return class_name if count == 1 else f"{class_name}s"


async def build_detection_evidence(
    boxes: list[OrientedBox],
    class_names: tuple[str, ...],
    *,
    asked: tuple[str, ...],
    shape: tuple[int, int],
    transform: AffineTransform,
    crs: str | None,
    resolution_metres: float | None,
    run_id: str,
    trace_step_id: str,
    scene_id: str,
    model_id: ModelId,
    model_version: str,
    score_threshold: float,
    observed_fraction: float,
    wants_location: bool,
    attribution: str | None = None,
) -> DetectionEvidence:
    """A detector's oriented boxes as evidence: one polygon feature per box (when there is ground to put
    it on), one evidence record per class, and one claim per class the operator asked for.

    **A count is the number of boxes the detector kept at or above its score threshold**, each with its
    own score; the claim's confidence is the mean score of that class - the model's certainty in what it
    reported, stated as such, and absent when it reported nothing (certainty about nothing is not a
    number). A class asked for and not found is a negative claim with the threshold and the observed
    share on it, so "none" reads as "looked and did not find" rather than silence. Nothing asked for
    means every class found is claimed.
    """
    counts: dict[str, int] = dict.fromkeys(asked, 0)
    for box in boxes:
        name = class_names[box.class_index]
        counts[name] = counts.get(name, 0) + 1
    ordinal: dict[str, int] = {}
    features: list[EvidenceFeature] = []
    feature_ids_by_class: dict[str, list[str]] = {}
    layer: EvidenceLayer | None = None

    if crs is not None and resolution_metres is not None:
        rings = await asyncio.to_thread(_box_rings_geographic, boxes, transform, crs)
        for box, ring in zip(boxes, rings, strict=True):
            name = class_names[box.class_index]
            ordinal[name] = ordinal.get(name, 0) + 1
            feature = EvidenceFeature(
                id=new_identifier(IdentifierPrefix.FEATURE),
                label=f"{name} {ordinal[name]}",
                geometry=PolygonGeometry(ring=[GeoPoint(latitude=lat, longitude=lon) for lon, lat in ring]),
                magnitude=float(box.confidence),
                confidence=float(box.confidence),
                area_hectares=None,
                value=float(box.confidence),
                class_id=name,
            )
            features.append(feature)
            feature_ids_by_class.setdefault(name, []).append(feature.id)
        # The extent is the picture's, not the boxes' hull: an empty result still says where the detector looked.
        extent = await grid_extent(transform, crs, shape, resolution_metres)
        layer = EvidenceLayer(
            id=new_identifier(IdentifierPrefix.LAYER),
            kind=LayerKind.POLYGON_VECTOR,
            render_mode=LayerRenderMode.DRAPED,
            title=f"Detections - {scene_id} ({len(boxes)} boxes)",
            overlay_id=None,
            value_domain=ValueDomain(minimum=score_threshold, maximum=1.0),
            color_ramp_id=ColorRampId.DETECTION_TEAL,
            opacity=REGION_LAYER_OPACITY,
            is_visible=True,
            comparator_side=ComparatorSide.BOTH,
            tile_url_template=None,
            attribution=attribution,
            bounds=extent.bounds,
            minimum_zoom=None,
            maximum_zoom=None,
            features=features,
            provenance=LayerProvenance(
                model_id=model_id.value, model_version=model_version, trace_step_id=trace_step_id, confidence=_mean_score(boxes),
            ),
        )

    neutral = MetricDirection.NEUTRAL
    evidence: list[EvidenceItem] = []
    claims: list[Claim] = []
    items_by_class: dict[str, EvidenceItem] = {}
    for name in sorted(counts, key=lambda n: (n not in asked, n)):
        class_boxes = [box for box in boxes if class_names[box.class_index] == name]
        item = EvidenceItem(
            id=new_identifier(IdentifierPrefix.EVIDENCE),
            kind=EvidenceKind.DETECTION,
            title=f"{plural_of(name, counts[name]).capitalize()} detected" if counts[name] else f"No {plural_of(name, 0)} detected",
            layer_id=layer.id if layer else None,
            feature_ids=feature_ids_by_class.get(name, []),
            area_hectares=None,
            magnitude=_mean_score(class_boxes) or 0.0,
            confidence=_mean_score(class_boxes),
            source_scene_ids=[scene_id],
        )
        evidence.append(item)
        items_by_class[name] = item

    targets = tuple(asked) if asked else tuple(name for name in counts if counts[name])
    for name in targets:
        count = counts.get(name, 0)
        class_boxes = [box for box in boxes if class_names[box.class_index] == name]
        score = _mean_score(class_boxes)
        if count:
            metrics = [
                ClaimMetric(label="Count", value=float(count), unit="", direction=neutral, precision=COUNT_PRECISION),
                ClaimMetric(label="Mean score", value=score or 0.0, unit="", direction=neutral, precision=SCORE_PRECISION),
            ]
            text = f"The detector found {count} {plural_of(name, count)} in {scene_id}, with a mean score of {score or 0.0:.{SCORE_PRECISION}f}."
            kind = ClaimKind.QUANTITATIVE
        else:
            metrics = [
                ClaimMetric(label="Count", value=0.0, unit="", direction=neutral, precision=COUNT_PRECISION),
                ClaimMetric(label="Score threshold", value=score_threshold, unit="", direction=neutral, precision=SCORE_PRECISION),
                ClaimMetric(label="Observed share", value=observed_fraction * 100.0, unit="%", direction=neutral, precision=PERCENTAGE_PRECISION),
            ]
            text = (
                f"No {plural_of(name, 0)} were detected in {scene_id} at a score of {score_threshold:.{SCORE_PRECISION}f} or above; "
                f"{observed_fraction:.{PERCENTAGE_PRECISION}%} of the picture was observed."
            )
            kind = ClaimKind.NEGATIVE
        claims.append(
            Claim(
                id=new_identifier(IdentifierPrefix.CLAIM), run_id=run_id, text=text, kind=kind, confidence=score,
                metrics=metrics, evidence_ids=[items_by_class[name].id], model_id=model_id, model_version=model_version,
                trace_step_id=trace_step_id, is_primary=True,
            )
        )
        if wants_location and class_boxes:
            best = max(class_boxes, key=lambda box: box.confidence)
            column, row = (float(value) for value in best.corners.mean(axis=0))
            if crs is not None:
                lon, lat = _pixel_to_geographic(column, row, transform, crs)
                where_metrics = [
                    ClaimMetric(label="Latitude", value=lat, unit="deg", direction=neutral, precision=4),
                    ClaimMetric(label="Longitude", value=lon, unit="deg", direction=neutral, precision=4),
                    ClaimMetric(label="Score", value=float(best.confidence), unit="", direction=neutral, precision=SCORE_PRECISION),
                ]
                where = (
                    f"The highest-scoring {name} (score {best.confidence:.{SCORE_PRECISION}f}) is centred at "
                    f"latitude {lat:.4f}, longitude {lon:.4f}."
                )
            else:
                where_metrics = [
                    ClaimMetric(label="Column", value=column, unit="px", direction=neutral, precision=0),
                    ClaimMetric(label="Row", value=row, unit="px", direction=neutral, precision=0),
                    ClaimMetric(label="Score", value=float(best.confidence), unit="", direction=neutral, precision=SCORE_PRECISION),
                ]
                where = (
                    f"The highest-scoring {name} (score {best.confidence:.{SCORE_PRECISION}f}) is centred at "
                    f"pixel column {column:.0f}, row {row:.0f}."
                )
            claims.append(
                Claim(
                    id=new_identifier(IdentifierPrefix.CLAIM), run_id=run_id, text=where, kind=ClaimKind.SPATIAL,
                    confidence=float(best.confidence), metrics=where_metrics, evidence_ids=[items_by_class[name].id],
                    model_id=model_id, model_version=model_version, trace_step_id=trace_step_id, is_primary=False,
                )
            )

    others = {name: count for name, count in counts.items() if name not in targets and count}
    if others:
        listed = ", ".join(f"{count} {plural_of(name, count)}" for name, count in sorted(others.items()))
        claims.append(
            Claim(
                id=new_identifier(IdentifierPrefix.CLAIM), run_id=run_id, text=f"Also found in {scene_id}: {listed}.",
                kind=ClaimKind.QUANTITATIVE,
                confidence=_mean_score([box for box in boxes if class_names[box.class_index] in others]),
                metrics=[
                    ClaimMetric(label=f"Count of {name}", value=float(count), unit="", direction=neutral, precision=COUNT_PRECISION)
                    for name, count in sorted(others.items())
                ],
                evidence_ids=[items_by_class[name].id for name in sorted(others)], model_id=model_id, model_version=model_version,
                trace_step_id=trace_step_id, is_primary=False,
            )
        )
    return DetectionEvidence(layer=layer, evidence=evidence, claims=claims, counts=counts)


def _mean_score(boxes: list[OrientedBox]) -> float | None:
    return float(np.mean([box.confidence for box in boxes])) if boxes else None


def _box_rings_geographic(boxes: list[OrientedBox], transform: AffineTransform, crs: str) -> list[list[tuple[float, float]]]:
    """Each box's four corners, pixel -> CRS by the affine -> WGS 84. Sync, for `to_thread`."""
    a, b, c, d, e, f = transform
    rings = []
    for box in boxes:
        columns, rows = box.corners[:, 0], box.corners[:, 1]
        x = a * columns + b * rows + c
        y = d * columns + e * rows + f
        rings.append(outer_ring_geographic(Polygon(list(zip(x.tolist(), y.tolist(), strict=True))), crs=crs))
    return rings


def _pixel_to_geographic(column: float, row: float, transform: AffineTransform, crs: str) -> tuple[float, float]:
    a, b, c, d, e, f = transform
    x, y = a * column + b * row + c, d * column + e * row + f
    lon, lat = Transformer.from_crs(CRS.from_user_input(crs), CRS.from_epsg(4326), always_xy=True).transform(x, y)
    return float(lon), float(lat)
