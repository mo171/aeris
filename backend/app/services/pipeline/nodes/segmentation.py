"""S13 and S15 for land cover - a class per pixel from the segmenter, then the classes asked for measured as regions.

what  : `segment_land_cover` (S13) and `localise_classes` (S15) of the single-image graph.
where : The SEGMENT branch: S1 -> (S7) -> S13 -> S15 -> S14 -> S16 -> S18 -> S19. The
        `segformer-landcover` model id's stage.
how   : S13 keeps two artefacts: the class map (categorical, one byte per pixel, the class id) and the
        model's per-pixel confidence (the softmax of the winning class), both COGs on the input's grid.
        The confidence surface is the layer and figure S13 stands behind - a continuous product the
        contract has a ramp for (`confidence-magma`) - and the class shares are recorded for the answer.
        The contract has no categorical ramp, so no class-map picture is drawn; the class map is retained
        and every class asked for is drawn by S15 as a mask over the true-colour picture, the same form an
        index region takes. (A categorical ramp is owed to the frontend vocabulary; `roadmap.md` 1.10.)

        **S15 measures the classes the question named, or every class present when it named none**,
        through the same region builder as an index (`services/evidence/builder.py`): hectares against
        observed ground, regions, polygons on a georeferenced input, and the mean per-pixel confidence of
        each region where an index region carries its mean value. The claim's confidence is the model's
        mean winning probability over that class's pixels - its own certainty, stated as such - and S18
        aggregates it. A class below `SEGMENTATION_MINIMUM_CLASS_FRACTION` is listed in the land-cover
        table and not localised when nothing named it; a class named and absent is a negative claim.

        Every class's share is one claim (the land-cover table): a SEGMENT answer with no named class is
        that table, and its numbers are on that claim.
"""

import logging
from pathlib import Path

import numpy as np

from app.constants.color_ramps import MATPLOTLIB_COLORMAPS, ColorRampId
from app.constants.evidence import (
    DETECTION_MASK_DETECTED,
    DETECTION_MASK_NOT_DETECTED,
    DETECTION_MASK_UNOBSERVED,
    PERCENTAGE_PRECISION,
    ClaimKind,
    EvidenceKind,
    MetricDirection,
)
from app.constants.fleet import FLEET
from app.constants.layers import SURFACE_LAYER_OPACITY, LayerKind
from app.constants.model_ids import ModelId
from app.constants.segmentation import (
    LOVEDA_CLASS_NAMES,
    SEGMENTATION_IGNORE_LABEL,
    SEGMENTATION_MINIMUM_CLASS_FRACTION,
)
from app.constants.stages import PipelineStage
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.schemas.events import (
    Claim,
    ClaimEvent,
    ClaimMetric,
    EvidenceItem,
    LayerProvenance,
    LayerReadyEvent,
    ValueDomain,
)
from app.services.evidence.artefacts import read_artefact, store_artefact
from app.services.evidence.builder import build_raster_layer, build_region_evidence, grid_extent
from app.services.evidence.spatial import measure_mask_on_grid
from app.services.evidence.trace import ArtefactRecord, ModelRecord
from app.services.pipeline.inputs import primary_frame, primary_input
from app.services.pipeline.node import attach_artefact_layer, current_trace_step_id, describe_trace_step, pipeline_node
from app.services.pipeline.state import AnalysisState
from app.services.pipeline.stream import emit
from app.services.rendering.figures import render_frame, render_index_map, render_mask_overlay
from app.services.segmentation.classes import class_id_of

logger = logging.getLogger(__name__)

CLASS_MAP_ARTEFACT_NAME = "landcover-classes.tif"
CONFIDENCE_ARTEFACT_NAME = "landcover-confidence.tif"
# The class map's nodata byte: no LoveDA class id, and the same byte every other categorical mask uses.
CLASS_MAP_UNOBSERVED = 255


@pipeline_node(
    PipelineStage.S13, detail="Classifying land cover with the segmenter",
    model_id=ModelId.SEGFORMER_LANDCOVER, model_version=FLEET[ModelId.SEGFORMER_LANDCOVER].version,
)
async def segment_land_cover(state: AnalysisState) -> dict[str, object]:
    """S13. A class per pixel and the probability behind it, both retained; the confidence surface drawn."""
    from app.models.manager import get_manager
    from app.services.segmentation.segmenter import segment_image

    run_id = state["run_id"]
    step_id = current_trace_step_id()
    source = await primary_input(state)
    frame = await primary_frame(state)

    shown = await render_frame(
        frame.rgb, frame.observed, run_id=run_id, trace_step_id=step_id, title=f"As shown to the segmenter - {source.scene_id}",
        stretch=frame.stretch.value, bands=list(frame.band_ids), scene_ids=[source.scene_id], crs=source.crs,
        caption="The picture the segmenter was given. Cloud, shadow and nodata are transparent: no class was assigned there.",
    )
    emit(shown.event)

    result = await segment_image(frame.for_model(), manager=await get_manager())
    class_map = result.class_map.astype(np.uint8)
    class_map[~frame.observed] = CLASS_MAP_UNOBSERVED
    confidence = result.confidence.astype(np.float32)
    confidence[~frame.observed] = np.nan

    classes = await store_artefact(
        class_map, run_id=run_id, stage=PipelineStage.S13, name=CLASS_MAP_ARTEFACT_NAME, reference=source.reference,
        nodata=CLASS_MAP_UNOBSERVED, categorical=True,
    )
    certainty = await store_artefact(confidence, run_id=run_id, stage=PipelineStage.S13, name=CONFIDENCE_ARTEFACT_NAME, reference=source.reference)

    observed = frame.observed & (class_map != SEGMENTATION_IGNORE_LABEL)
    total = int(observed.sum())
    fractions: dict[str, float] = {}
    mean_confidence: dict[str, float] = {}
    for class_id, name in enumerate(LOVEDA_CLASS_NAMES):
        if class_id == SEGMENTATION_IGNORE_LABEL:
            continue
        member = observed & (class_map == class_id)
        count = int(member.sum())
        fractions[name] = count / total if total else 0.0
        if count:
            mean_confidence[name] = float(np.nanmean(confidence[member]))

    update: dict[str, object] = {
        "class_map_path": str(classes.path), "class_map_object_key": classes.object_key, "class_map_storage_uri": classes.storage_uri,
        "class_confidence_path": str(certainty.path), "class_confidence_object_key": certainty.object_key,
        "class_confidence_storage_uri": certainty.storage_uri, "class_names": list(LOVEDA_CLASS_NAMES),
        "class_fractions": fractions, "class_mean_confidence": mean_confidence, "segmentation_confidence": result.stated_confidence,
        "frame_observed_fraction": frame.observed_fraction, "frame_figure_id": shown.event.figure_id,
        "class_confidence_layer_id": None, "figure_ids": [shown.event.figure_id], "input_files": await frame.input_records(),
        "stage_models": [ModelRecord(stage=PipelineStage.S13, model_id=result.model_id.value, model_version=result.model_version, confidence=result.stated_confidence).to_wire()],
        "layers": [],
    }

    if source.georeferenced and source.resolution_metres is not None:
        extent = await grid_extent(source.transform, source.crs or "", frame.shape, source.resolution_metres)
        layer = await build_raster_layer(
            title=f"Land-cover confidence - {source.scene_id}", kind=LayerKind.RASTER_TILES, overlay_id="landcover-confidence",
            storage_uri=certainty.storage_uri, extent=extent, color_ramp_id=ColorRampId.CONFIDENCE_MAGMA, opacity=SURFACE_LAYER_OPACITY,
            provenance=LayerProvenance(model_id=result.model_id.value, model_version=result.model_version, trace_step_id=step_id, confidence=result.stated_confidence),
            value_domain=ValueDomain(minimum=0.0, maximum=1.0),
            rendering={"rescale": "0,1", "colormap_name": MATPLOTLIB_COLORMAPS[ColorRampId.CONFIDENCE_MAGMA].lower()},
        )
        attach_artefact_layer(layer.id)
        emit(LayerReadyEvent(run_id=run_id, layer=layer, evidence=[]))
        update["class_confidence_layer_id"] = layer.id
        update["layers"] = [layer.to_wire()]

    figure = await render_index_map(
        confidence, run_id=run_id, trace_step_id=step_id, title=f"Land-cover confidence - {source.scene_id}", label="confidence",
        ramp=ColorRampId.CONFIDENCE_MAGMA, bands=list(frame.band_ids), scene_ids=[source.scene_id], crs=source.crs,
        mask_applied=bool((~frame.observed).any()),
        caption="How sure the segmenter was of its winning class at each pixel. Dark is a coin toss; bright is a confident class.",
    )
    emit(figure.event)
    update["class_confidence_figure_id"] = figure.event.figure_id
    update["figure_ids"] = [shown.event.figure_id, figure.event.figure_id]

    leading = sorted(fractions.items(), key=lambda item: -item[1])[:3]
    describe_trace_step(
        f"{frame.shape[1]}x{frame.shape[0]}, {frame.observed_fraction:.1%} observed; "
        + ", ".join(f"{name.lower()} {fraction:.1%}" for name, fraction in leading)
        + (f"; mean winning probability {result.stated_confidence:.2f}" if result.stated_confidence is not None else "")
        + f"; {result.latency_ms} ms"
    )
    return update


@pipeline_node(
    PipelineStage.S15, detail="Measuring the land-cover classes asked for",
    model_id=ModelId.SEGFORMER_LANDCOVER, model_version=FLEET[ModelId.SEGFORMER_LANDCOVER].version,
)
async def localise_classes(state: AnalysisState) -> dict[str, object]:
    """S15. Each class asked for (or every class present) as a mask: hectares, regions, polygons, claims."""
    run_id = state["run_id"]
    step_id = current_trace_step_id()
    source = await primary_input(state)
    class_map = await read_artefact(Path(state["class_map_path"]), state["class_map_object_key"])
    confidence = await read_artefact(Path(state["class_confidence_path"]), state["class_confidence_object_key"])
    observed = (class_map != CLASS_MAP_UNOBSERVED) & (class_map != SEGMENTATION_IGNORE_LABEL)
    fractions: dict[str, float] = dict(state.get("class_fractions") or {})
    mean_confidence: dict[str, float] = dict(state.get("class_mean_confidence") or {})
    version = FLEET[ModelId.SEGFORMER_LANDCOVER].version

    asked = tuple(state.get("classes") or ())
    names = asked or tuple(name for name, fraction in fractions.items() if fraction >= SEGMENTATION_MINIMUM_CLASS_FRACTION)

    layers: list[dict[str, object]] = []
    evidence_items: list[dict[str, object]] = []
    claims: list[dict[str, object]] = []
    figure_ids: list[str] = []
    retained: list[dict[str, object]] = []
    primary_figure: str | None = None
    frame = await primary_frame(state)
    base_rgba = np.dstack([frame.rgb, np.where(frame.observed, 255, 0).astype(np.uint8)])

    # The land-cover table: every class's share, one claim, so a whole-scene question has its numbers on record.
    table_item = EvidenceItem(
        id=new_identifier(IdentifierPrefix.EVIDENCE), kind=EvidenceKind.STATISTIC, title="Land-cover shares of observed ground",
        layer_id=None, feature_ids=[], area_hectares=None, magnitude=1.0, confidence=state.get("segmentation_confidence"),
        source_scene_ids=[state["scene_id"]],
    )
    ordered = sorted(fractions.items(), key=lambda item: -item[1])
    table = Claim(
        id=new_identifier(IdentifierPrefix.CLAIM), run_id=run_id,
        text="Land cover over the observed ground of " + state["scene_id"] + ": "
        + ", ".join(f"{name.lower()} {fraction:.{PERCENTAGE_PRECISION}%}" for name, fraction in ordered if fraction > 0) + ".",
        kind=ClaimKind.QUANTITATIVE, confidence=state.get("segmentation_confidence"),
        metrics=[
            ClaimMetric(label=f"{name} share", value=fraction * 100.0, unit="%", direction=MetricDirection.NEUTRAL, precision=PERCENTAGE_PRECISION)
            for name, fraction in ordered if fraction > 0
        ],
        evidence_ids=[table_item.id], model_id=ModelId.SEGFORMER_LANDCOVER, model_version=version, trace_step_id=step_id,
        is_primary=not asked,
    )
    evidence_items.append(table_item.to_wire())
    claims.append(table.to_wire())
    emit(ClaimEvent(run_id=run_id, claim=table))

    for name in names:
        detected = observed & (class_map == class_id_of(name))
        statistics = await measure_mask_on_grid(
            detected, observed, transform=source.transform, crs=source.crs, resolution_metres=source.resolution_metres,
            resolution_declared=source.resolution_declared,
        )
        encoded = np.full(detected.shape, DETECTION_MASK_NOT_DETECTED, dtype=np.uint8)
        encoded[detected] = DETECTION_MASK_DETECTED
        encoded[~observed] = DETECTION_MASK_UNOBSERVED
        mask_uri: str | None = None
        artefact = None
        if source.georeferenced:
            artefact = await store_artefact(
                encoded, run_id=run_id, stage=PipelineStage.S15, name=f"landcover-{name.lower()}.tif", reference=source.reference,
                nodata=DETECTION_MASK_UNOBSERVED, categorical=True,
            )
            mask_uri = artefact.storage_uri
        evidence = await build_region_evidence(
            detected, confidence, statistics=statistics, transform=source.transform, crs=source.crs, resolution_metres=source.resolution_metres,
            run_id=run_id, trace_step_id=step_id, scene_id=state["scene_id"], mask_storage_uri=mask_uri, index_label="confidence",
            quantity_label=f"{FLEET[ModelId.SEGFORMER_LANDCOVER].model_id.value} class", region_label=name, lower=0.0, upper=1.0,
            obscured_fraction=state.get("obscured_fraction"), unphysical_fraction=0.0, model_id=ModelId.SEGFORMER_LANDCOVER,
            model_version=version, confidence=mean_confidence.get(name), evidence_kind=EvidenceKind.INDEX_MAP, value_label="Mean confidence",
            nominal_resolution=source.resolution_declared,
        )
        if evidence.raster_layer is not None:
            emit(LayerReadyEvent(run_id=run_id, layer=evidence.raster_layer, evidence=[]))
        if evidence.vector_layer is not None:
            emit(LayerReadyEvent(run_id=run_id, layer=evidence.vector_layer, evidence=evidence.evidence))
            if primary_figure is None:
                attach_artefact_layer(evidence.vector_layer.id)
        if artefact is not None:
            retained.append(ArtefactRecord(
                stage=PipelineStage.S15, name=artefact.path.name, object_key=artefact.object_key, storage_uri=artefact.storage_uri,
                local_path=str(artefact.path), layer_id=evidence.raster_layer.id if evidence.raster_layer else None,
            ).to_wire())
        for claim in evidence.claims:
            emit(ClaimEvent(run_id=run_id, claim=claim))
        overlay = await render_mask_overlay(
            detected, base_rgba, run_id=run_id, trace_step_id=step_id, title=f"{name} - {state['scene_id']}", label=name,
            scene_ids=[state["scene_id"]], crs=source.crs, claim_ids=[claim.id for claim in evidence.claims],
            caption=f"{name} as the segmenter classified it, over the picture it was shown. Unobserved ground is not marked.",
            is_primary=primary_figure is None,
        )
        emit(overlay.event)
        primary_figure = primary_figure or overlay.event.figure_id
        figure_ids.append(overlay.event.figure_id)
        layers.extend(layer.to_wire() for layer in evidence.layers)
        evidence_items.extend(item.to_wire() for item in evidence.evidence)
        claims.extend(claim.to_wire() for claim in evidence.claims)

    describe_trace_step(
        (", ".join(f"{name.lower()} {fractions.get(name, 0.0):.1%}" for name in names) or "no class named or present")
        + f"; {len(claims)} claims, {len(figure_ids)} overlays"
        + ("" if source.georeferenced else "; no georeference, so no layers")
    )
    return {
        "primary_figure_id": primary_figure or state.get("class_confidence_figure_id"), "figure_ids": figure_ids,
        "layers": layers, "evidence_items": evidence_items, "claims": claims, "artefact_records": retained,
    }

