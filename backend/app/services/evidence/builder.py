"""Turns what a stage measured into what an operator can click: layers, the evidence records they draw, and the claims that rest on them.

what  : `build_raster_layer()` - a tile layer over a retained COG; `build_region_evidence()` - a thresholded
        mask as a raster-mask layer *and* a polygon layer, its evidence items, and its claims.
where : S15 (`services/pipeline/nodes/evidence_localisation.py`) and S12 (`feature_extraction.py`). The
        geometry is `segmentation/math/vectorize.py` and `evidence/math/`; this file contains none of it.
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

        Confidence is `None` on everything here: the index and geospatial engines are deterministic and
        decline to assert a probability (`architecture-context.md` §8 rule 10). Phase 1.6's models state one.
"""

import asyncio
from dataclasses import dataclass

import numpy as np

from app.constants.color_ramps import ColorRampId
from app.constants.evidence import (
    COUNT_PRECISION,
    HECTARES_PRECISION,
    INDEX_VALUE_PRECISION,
    MINIMUM_FEATURE_REGION_PIXELS,
    PERCENTAGE_PRECISION,
    POLYGON_SIMPLIFICATION_TOLERANCE_METRES,
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
from app.services.evidence.math.area import polygon_area
from app.services.evidence.math.simplification import outer_ring_geographic, simplify_outline
from app.services.evidence.spatial import MaskStatistics
from app.services.imagery.math.web_mercator import geographic_bounds, zoom_range
from app.services.segmentation.math.vectorize import label_regions, region_means, vectorise_regions

type AffineTransform = tuple[float, float, float, float, float, float]


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
    """Everything S15 emits for one thresholded mask, in the order it is emitted."""

    raster_layer: EvidenceLayer
    vector_layer: EvidenceLayer
    evidence: list[EvidenceItem]
    claims: list[Claim]
    regions_total: int
    regions_drawn: int


async def build_region_evidence(
    detected: np.ndarray,
    values: np.ndarray,
    *,
    statistics: MaskStatistics,
    transform: AffineTransform,
    crs: str,
    resolution_metres: float,
    run_id: str,
    trace_step_id: str,
    scene_id: str,
    mask_storage_uri: str,
    index_label: str,
    quantity_label: str,
    region_label: str,
    lower: float,
    upper: float,
    obscured_fraction: float | None,
    unphysical_fraction: float,
) -> RegionEvidence:
    """Both representations of one mask, the records that point at them, and the claims that rest on those.

    `obscured_fraction` and `unphysical_fraction` become metrics on the primary claim, because the answer
    states them as caveats and every number the answer speaks must be on a claim (invariant 15).
    """
    provenance = LayerProvenance(
        model_id=ModelId.GEOSPATIAL_ENGINE.value,
        model_version=GEOSPATIAL_ENGINE_VERSION,
        trace_step_id=trace_step_id,
        confidence=None,
    )
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
            confidence=None,
            area_hectares=draft.square_metres / SQUARE_METRES_PER_HECTARE,
            value=draft.mean_value,
            class_id=None,
        )
        for index, draft in enumerate(drafts)
    ]

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

    hectares = statistics.detected.hectares
    observed_hectares = statistics.observed.hectares
    coverage = statistics.coverage_fraction
    region_count = statistics.regions.region_count

    regions_item = EvidenceItem(
        id=new_identifier(IdentifierPrefix.EVIDENCE),
        kind=EvidenceKind.INDEX_MAP,
        title=f"{region_label} regions",
        layer_id=vector_layer.id,
        feature_ids=[feature.id for feature in features],
        area_hectares=hectares,
        magnitude=coverage,
        confidence=None,
        source_scene_ids=[scene_id],
    )
    measurement_item = EvidenceItem(
        id=new_identifier(IdentifierPrefix.EVIDENCE),
        kind=EvidenceKind.STATISTIC,
        title=f"{region_label} area over observed ground",
        layer_id=None,
        feature_ids=[],
        area_hectares=hectares,
        magnitude=coverage,
        confidence=None,
        source_scene_ids=[scene_id],
    )
    evidence = [regions_item, measurement_item]

    neutral = MetricDirection.NEUTRAL
    metrics = [
        ClaimMetric(label="Area", value=hectares, unit="ha", direction=neutral, precision=HECTARES_PRECISION),
        ClaimMetric(
            label="Share of observed ground", value=coverage * 100.0, unit="%", direction=neutral,
            precision=PERCENTAGE_PRECISION,
        ),
        ClaimMetric(label="Regions", value=float(region_count), unit="", direction=neutral, precision=COUNT_PRECISION),
        ClaimMetric(
            label="Observed ground", value=observed_hectares, unit="ha", direction=neutral, precision=HECTARES_PRECISION
        ),
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
    if region_count == 0:
        text = (
            f"No {region_label.lower()} ({quantity_label}) was detected in the "
            f"{observed_hectares:,.{HECTARES_PRECISION}f} hectares observed of {scene_id}."
        )
        kind = ClaimKind.NEGATIVE
    else:
        text = (
            f"{region_label} ({quantity_label}) covers {hectares:,.{HECTARES_PRECISION}f} hectares of {scene_id}: "
            f"{coverage:.{PERCENTAGE_PRECISION}%} of the {observed_hectares:,.{HECTARES_PRECISION}f} hectares "
            f"observed, in {region_count:,} regions."
        )
        kind = ClaimKind.QUANTITATIVE
    claims = [
        Claim(
            id=new_identifier(IdentifierPrefix.CLAIM),
            run_id=run_id,
            text=text,
            kind=kind,
            confidence=None,
            metrics=metrics,
            evidence_ids=[regions_item.id, measurement_item.id],
            model_id=ModelId.GEOSPATIAL_ENGINE,
            model_version=GEOSPATIAL_ENGINE_VERSION,
            trace_step_id=trace_step_id,
            is_primary=True,
        )
    ]

    if features:
        largest_feature = features[0]
        largest_item = EvidenceItem(
            id=new_identifier(IdentifierPrefix.EVIDENCE),
            kind=EvidenceKind.INDEX_MAP,
            title=f"Largest {region_label.lower()} region",
            layer_id=vector_layer.id,
            feature_ids=[largest_feature.id],
            area_hectares=largest_feature.area_hectares,
            magnitude=1.0,
            confidence=None,
            source_scene_ids=[scene_id],
        )
        evidence.append(largest_item)
        largest_hectares = largest_feature.area_hectares or 0.0
        largest_metrics = [
            ClaimMetric(label="Area", value=largest_hectares, unit="ha", direction=neutral, precision=HECTARES_PRECISION),
        ]
        reading = ""
        if largest_feature.value is not None:
            largest_metrics.append(
                ClaimMetric(
                    label=f"Mean {index_label}", value=largest_feature.value, unit="",
                    direction=MetricDirection.NEUTRAL, precision=INDEX_VALUE_PRECISION,
                )
            )
            reading = f", with a mean {index_label} of {largest_feature.value:.{INDEX_VALUE_PRECISION}f}"
        claims.append(
            Claim(
                id=new_identifier(IdentifierPrefix.CLAIM),
                run_id=run_id,
                text=f"The largest contiguous region covers {largest_hectares:,.{HECTARES_PRECISION}f} hectares{reading}.",
                kind=ClaimKind.SPATIAL,
                confidence=None,
                metrics=largest_metrics,
                evidence_ids=[largest_item.id],
                model_id=ModelId.GEOSPATIAL_ENGINE,
                model_version=GEOSPATIAL_ENGINE_VERSION,
                trace_step_id=trace_step_id,
                is_primary=False,
            )
        )

    return RegionEvidence(
        raster_layer=raster_layer,
        vector_layer=vector_layer,
        evidence=evidence,
        claims=claims,
        regions_total=regions_total,
        regions_drawn=len(features),
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
