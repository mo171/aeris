"""S9, S13 and S15 for a pair of dates - the alignment measured and gated, the change model run, the change bound to ground.

what  : `coregister_pair` (S9), `detect_change_node` (S13) and `localise_change` (S15) of the temporal graph.
where : S1 -> (S7) -> S9 -> S13 -> S15 -> S14 -> S16 -> S18 -> S19. The `co-registration` and
        `changeformer` model ids' stages.
how   : **S9 is the gate and it is its own trace step**, so an operator sees the residual beside the
        stage that measured it (`architecture-context.md` §8 rule 2, verbatim: *above tolerance the
        pipeline refuses to run change detection*). The measurement is the 1.3 phase correlation on the
        sharpest band the pair shares - near-infrared for Sentinel-2, luminance for a picture - and the
        refusal is the 1.3 `InvalidRequestError` with the residual in it, which ends the run with
        `run-error` naming the number. The measurement is the S9 artefact, retained as JSON.

        **S13 runs the model only against S9's admission.** It reads `registration.accepted` from the
        state and refuses to start without it - the same gate `services/change_detection/comparison.py`
        puts in front of the detector, split across two stages so the trace shows both. Ground either
        date could not see (cloud, shadow, nodata) reaches the model as NaN and comes back NaN: change is
        only ever asserted where both dates were observed. The probability and the mask are retained as
        COGs, the probability is the S13 layer and figure, and the model's mean winning probability is
        its stated confidence.

        **S15 measures the mask as regions** through the same builder as an index or a land-cover class:
        hectares of observed ground (geodetic, nominal at a declared pixel size, or pixels), regions,
        polygons on a georeferenced pair, and the comparison figure - before | after | change - with the
        claims' ids on it, which is the figure the run stands behind.

        **The radar pair is 1.11's.** `CHANGE_DETECTORS_BY_MODALITY` names it `None` with the phase, the
        same convention as the intent table (`constants/routing.py`): a refusal by name, never a stub.
"""

import logging
from pathlib import Path
from typing import Final

import numpy as np

from app.constants.change import CHANGE_PROBABILITY_THRESHOLD
from app.constants.color_ramps import MATPLOTLIB_COLORMAPS, ColorRampId
from app.constants.evidence import (
    DETECTION_MASK_DETECTED,
    DETECTION_MASK_NOT_DETECTED,
    DETECTION_MASK_UNOBSERVED,
    SCORE_PRECISION,
    EvidenceKind,
)
from app.constants.fleet import FLEET
from app.constants.layers import SURFACE_LAYER_OPACITY, LayerKind
from app.constants.model_ids import ModelId
from app.constants.raster import BandRole, ProcessingLevel
from app.constants.scenes import SceneModality
from app.constants.stages import PipelineStage
from app.lib.exceptions import InvalidRequestError
from app.schemas.events import ClaimEvent, LayerProvenance, LayerReadyEvent, ValueDomain
from app.services.change_detection.detector import detect_change
from app.services.evidence.artefacts import read_artefact, store_artefact, store_json_artefact
from app.services.evidence.builder import build_raster_layer, build_region_evidence, grid_extent
from app.services.evidence.spatial import measure_mask_on_grid
from app.services.evidence.trace import ModelRecord
from app.services.imagery.frames import AnalysisInput, InputKind, RgbFrame
from app.services.pipeline.inputs import primary_frame, primary_input, reference_frame, reference_input
from app.services.pipeline.node import attach_artefact_layer, current_trace_step_id, describe_trace_step, pipeline_node
from app.services.pipeline.state import AnalysisState
from app.services.pipeline.stream import emit
from app.services.preprocessing.coregistration import measure_coregistration, require_comparison_ready
from app.services.rendering.figures import render_comparison, render_frame, render_index_map
from app.services.spectral.indices import locate_bands, read_scene_bands

logger = logging.getLogger(__name__)

REGISTRATION_ARTEFACT_NAME = "registration.json"
CHANGE_PROBABILITY_ARTEFACT_NAME = "change-probability.tif"
CHANGE_MASK_ARTEFACT_NAME = "change-mask.tif"

# Which specialist compares two dates of one sensor. `None` names the phase, as the intent table does.
CHANGE_DETECTORS_BY_MODALITY: Final[dict[SceneModality, ModelId | None]] = {
    SceneModality.OPTICAL: ModelId.CHANGEFORMER,
    SceneModality.SAR: None,
}
UNBUILT_CHANGE_DETECTOR_PHASE: Final[dict[SceneModality, str]] = {SceneModality.SAR: "1.11 (the radar branch: log-ratio change over preprocessed backscatter)"}

# The band a pair is aligned on: the sharpest one both Sentinel-2 dates carry at 10 m, in preference order.
ALIGNMENT_ROLES: Final[tuple[BandRole, ...]] = (BandRole.NEAR_INFRARED, BandRole.RED, BandRole.GREEN)


@pipeline_node(PipelineStage.S9, detail="Measuring the co-registration residual of the pair", model_id=ModelId.CO_REGISTRATION, model_version=FLEET[ModelId.CO_REGISTRATION].version)
async def coregister_pair(state: AnalysisState) -> dict[str, object]:
    """S9. Measure, record, refuse above tolerance. The detector never runs on an unmeasured pair."""
    reference = await reference_input(state)
    primary = await primary_input(state)
    declared = state.get("declared_level")
    level = ProcessingLevel(declared) if declared else None
    before, band = await _alignment_band(reference, level)
    after, _ = await _alignment_band(primary, level)
    result = await measure_coregistration(
        before, after, resolution_metres=primary.resolution_metres, declared_registered=bool(state.get("declared_registered")),
    )
    measurement = result.measurement
    record = {
        "band": band, "residualPixels": measurement.residual_pixels, "shiftPixels": measurement.shift_magnitude_pixels,
        "tolerancePixels": result.tolerance_pixels, "toleranceMetres": result.tolerance_metres, "tileSize": result.tile_size,
        "rowShiftPixels": measurement.row_shift_pixels, "columnShiftPixels": measurement.column_shift_pixels,
        "validTileCount": measurement.valid_tile_count, "agreeingFraction": result.agreeing_fraction,
        "globalShiftPixels": result.global_shift_magnitude_pixels, "globalAgreeingFraction": result.global_agreeing_fraction,
        "declaredRegistered": result.declared_registered, "verdict": result.verdict.value, "accepted": result.is_accepted,
    }
    artefact = await store_json_artefact(record, run_id=state["run_id"], stage=PipelineStage.S9, name=REGISTRATION_ARTEFACT_NAME)
    record.update({"artefactPath": str(artefact.path), "artefactObjectKey": artefact.object_key, "artefactStorageUri": artefact.storage_uri})
    describe_trace_step(f"on {band}: {result.describe()}")
    # Refuse after recording: the run's record says what was measured and why it stopped.
    await require_comparison_ready(result)
    model = ModelRecord(stage=PipelineStage.S9, model_id=ModelId.CO_REGISTRATION.value, model_version=FLEET[ModelId.CO_REGISTRATION].version)
    return {"registration": record, "stage_models": [model.to_wire()]}


async def _alignment_band(source: AnalysisInput, level: ProcessingLevel | None) -> tuple[np.ndarray, str]:
    """The sharpest band the input carries, as float32 with NaN nodata; luminance for a picture."""
    if source.kind is InputKind.SCENE_DIRECTORY and source.modality is SceneModality.OPTICAL:
        located = await locate_bands(source.path)
        for role in ALIGNMENT_ROLES:
            if role in located:
                bands = await read_scene_bands(source.path, (role,), declared_level=level)
                band = bands.bands[role]
                return band.reflectance.astype(np.float32), band.band_id
    from app.services.imagery.frames import read_rgb_frame

    frame = await read_rgb_frame(source, declared_level=level)
    luminance = frame.rgb.astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    luminance[~frame.observed] = np.nan
    return luminance, "luminance"


@pipeline_node(PipelineStage.S13, detail="Detecting change between the two dates", model_id=ModelId.CHANGEFORMER, model_version=FLEET[ModelId.CHANGEFORMER].version)
async def detect_change_node(state: AnalysisState) -> dict[str, object]:
    """S13. Both frames as the model saw them, the probability it returned, the mask cut from it."""
    from app.models.manager import get_manager

    registration = state.get("registration") or {}
    if not registration.get("accepted"):
        raise InvalidRequestError(
            "Change detection needs a pair S9 admitted; this run has no accepted co-registration record.",
            details={"registration": registration},
        )
    modality = SceneModality(state.get("modality") or SceneModality.OPTICAL.value)
    detector = CHANGE_DETECTORS_BY_MODALITY.get(modality)
    if detector is None:
        raise InvalidRequestError(
            f"Change detection over {modality.value} is not built: {UNBUILT_CHANGE_DETECTOR_PHASE.get(modality, 'unplanned')}.",
            details={"modality": modality.value},
        )

    run_id = state["run_id"]
    step_id = current_trace_step_id()
    source = await primary_input(state)
    before = await reference_frame(state)
    after = await primary_frame(state)
    figures: list[str] = []
    for frame, when in ((before, "earlier"), (after, "later")):
        shown = await render_frame(
            frame.rgb, frame.observed, run_id=run_id, trace_step_id=step_id, title=f"As shown to the change model ({when}) - {frame.source.scene_id}",
            stretch=frame.stretch.value, bands=list(frame.band_ids), scene_ids=[frame.source.scene_id], crs=frame.source.crs,
            caption=f"The {when} date as the change model was given it. Cloud, shadow and nodata are transparent.",
        )
        emit(shown.event)
        figures.append(shown.event.figure_id)

    result = await detect_change(before.for_model(), after.for_model(), manager=await get_manager())
    probability = result.probability.astype(np.float32)
    encoded = np.full(result.mask.shape, DETECTION_MASK_NOT_DETECTED, dtype=np.uint8)
    encoded[result.mask] = DETECTION_MASK_DETECTED
    encoded[~result.observed] = DETECTION_MASK_UNOBSERVED
    probability_artefact = await store_artefact(probability, run_id=run_id, stage=PipelineStage.S13, name=CHANGE_PROBABILITY_ARTEFACT_NAME, reference=source.reference)
    mask_artefact = await store_artefact(
        encoded, run_id=run_id, stage=PipelineStage.S13, name=CHANGE_MASK_ARTEFACT_NAME, reference=source.reference,
        nodata=DETECTION_MASK_UNOBSERVED, categorical=True,
    )

    update: dict[str, object] = {
        "change_probability_path": str(probability_artefact.path), "change_probability_object_key": probability_artefact.object_key,
        "change_probability_storage_uri": probability_artefact.storage_uri, "change_mask_path": str(mask_artefact.path),
        "change_mask_object_key": mask_artefact.object_key, "change_mask_storage_uri": mask_artefact.storage_uri,
        "change_threshold": CHANGE_PROBABILITY_THRESHOLD, "change_confidence": result.confidence,
        "change_model_id": result.model_id.value, "change_model_version": result.model_version, "changed_fraction": result.changed_fraction,
        "frame_observed_fraction": float(result.observed.mean()), "change_layer_id": None, "layers": [],
        "input_files": await before.input_records() + await after.input_records(),
        "stage_models": [ModelRecord(stage=PipelineStage.S13, model_id=result.model_id.value, model_version=result.model_version, confidence=result.confidence).to_wire()],
    }
    if source.georeferenced and source.resolution_metres is not None:
        extent = await grid_extent(source.transform, source.crs or "", probability.shape, source.resolution_metres)
        layer = await build_raster_layer(
            title=f"Change probability - {source.scene_id}", kind=LayerKind.RASTER_TILES, overlay_id="change-probability",
            storage_uri=probability_artefact.storage_uri, extent=extent, color_ramp_id=ColorRampId.CONFIDENCE_MAGMA, opacity=SURFACE_LAYER_OPACITY,
            provenance=LayerProvenance(model_id=result.model_id.value, model_version=result.model_version, trace_step_id=step_id, confidence=result.confidence),
            value_domain=ValueDomain(minimum=0.0, maximum=1.0),
            rendering={"rescale": "0,1", "colormap_name": MATPLOTLIB_COLORMAPS[ColorRampId.CONFIDENCE_MAGMA].lower()},
        )
        attach_artefact_layer(layer.id)
        emit(LayerReadyEvent(run_id=run_id, layer=layer, evidence=[]))
        update["change_layer_id"] = layer.id
        update["layers"] = [layer.to_wire()]

    figure = await render_index_map(
        probability, run_id=run_id, trace_step_id=step_id, title=f"Change probability - {source.scene_id}", label="change probability",
        ramp=ColorRampId.CONFIDENCE_MAGMA, scene_ids=[before.source.scene_id, after.source.scene_id], crs=source.crs,
        mask_applied=bool((~result.observed).any()),
        caption="The change model's probability that each pixel changed between the two dates. Unobserved ground on either date is transparent.",
    )
    emit(figure.event)
    figures.append(figure.event.figure_id)
    update["change_probability_figure_id"] = figure.event.figure_id
    update["figure_ids"] = figures

    describe_trace_step(
        f"{result.changed_fraction:.1%} of observed ground changed at p >= {CHANGE_PROBABILITY_THRESHOLD:.{SCORE_PRECISION}f}"
        + (f"; mean winning probability {result.confidence:.{SCORE_PRECISION}f}" if result.confidence is not None else "")
        + f"; {float(result.observed.mean()):.1%} observed on both dates; {result.latency_ms} ms"
    )
    return update


@pipeline_node(PipelineStage.S15, detail="Measuring the change as regions", model_id=ModelId.CHANGEFORMER, model_version=FLEET[ModelId.CHANGEFORMER].version)
async def localise_change(state: AnalysisState) -> dict[str, object]:
    """S15. The mask as hectares, regions and polygons; the comparison figure the run stands behind."""
    run_id = state["run_id"]
    step_id = current_trace_step_id()
    source = await primary_input(state)
    mask = await read_artefact(Path(state["change_mask_path"]), state["change_mask_object_key"])
    probability = await read_artefact(Path(state["change_probability_path"]), state["change_probability_object_key"])
    observed = mask != DETECTION_MASK_UNOBSERVED
    detected = mask == DETECTION_MASK_DETECTED
    threshold = float(state.get("change_threshold", CHANGE_PROBABILITY_THRESHOLD))
    model_id = ModelId(state.get("change_model_id") or ModelId.CHANGEFORMER.value)
    version = str(state.get("change_model_version") or FLEET[model_id].version)

    statistics = await measure_mask_on_grid(
        detected, observed, transform=source.transform, crs=source.crs, resolution_metres=source.resolution_metres,
        resolution_declared=source.resolution_declared,
    )
    evidence = await build_region_evidence(
        detected, probability, statistics=statistics, transform=source.transform, crs=source.crs, resolution_metres=source.resolution_metres,
        run_id=run_id, trace_step_id=step_id, scene_id=source.scene_id, mask_storage_uri=state.get("change_mask_storage_uri") if source.georeferenced else None,
        index_label="change probability", quantity_label=f"{model_id.value} probability >= {threshold:.{SCORE_PRECISION}f}", region_label="Change",
        lower=threshold, upper=1.0, obscured_fraction=None, unphysical_fraction=0.0, model_id=model_id, model_version=version,
        confidence=state.get("change_confidence"), evidence_kind=EvidenceKind.CHANGE_MASK, value_label="Mean change probability",
        nominal_resolution=source.resolution_declared,
    )
    if evidence.raster_layer is not None:
        emit(LayerReadyEvent(run_id=run_id, layer=evidence.raster_layer, evidence=[]))
    if evidence.vector_layer is not None:
        emit(LayerReadyEvent(run_id=run_id, layer=evidence.vector_layer, evidence=evidence.evidence))
        attach_artefact_layer(evidence.vector_layer.id)
    for claim in evidence.claims:
        emit(ClaimEvent(run_id=run_id, claim=claim))

    before = await reference_frame(state)
    after = await primary_frame(state)
    comparison = await render_comparison(
        _rgba(before), _rgba(after), detected, run_id=run_id, trace_step_id=step_id,
        title=f"Change - {before.source.scene_id} to {after.source.scene_id}", label="Change",
        scene_ids=[before.source.scene_id, after.source.scene_id], crs=source.crs, claim_ids=[claim.id for claim in evidence.claims], is_primary=True,
        caption="The earlier date, the later date, and the later date with the change mask over it. Unobserved ground on either date is not marked.",
    )
    emit(comparison.event)

    describe_trace_step(
        f"change: {statistics.detected.pixel_count:,} px"
        + (f", {statistics.detected.hectares:,.1f} ha" if statistics.has_area else "")
        + f", {statistics.coverage_fraction:.1%} of observed ground, {statistics.regions.region_count} regions ({evidence.regions_drawn} drawn), "
        f"{len(evidence.claims)} claims" + ("" if source.georeferenced else "; no georeference, so no layers")
    )
    return {
        "comparison_figure_id": comparison.event.figure_id, "primary_figure_id": comparison.event.figure_id,
        "figure_ids": [comparison.event.figure_id], "layers": [layer.to_wire() for layer in evidence.layers],
        "evidence_items": [item.to_wire() for item in evidence.evidence], "claims": [claim.to_wire() for claim in evidence.claims],
        "measurement": {
            "areaHectares": statistics.detected.hectares if statistics.has_area else None, "observedHectares": statistics.observed.hectares if statistics.has_area else None,
            "coverageFraction": statistics.coverage_fraction, "pixelCount": statistics.detected.pixel_count, "regionCount": statistics.regions.region_count,
            "regionDensityPerSquareKilometre": statistics.region_density_per_square_kilometre if statistics.has_area else 0.0,
            "largestRegionPixels": statistics.regions.largest_region_pixels, "equalAreaCrs": statistics.equal_area_crs,
        },
    }


def _rgba(frame: RgbFrame) -> np.ndarray:
    return np.dstack([frame.rgb, np.where(frame.observed, 255, 0).astype(np.uint8)])
