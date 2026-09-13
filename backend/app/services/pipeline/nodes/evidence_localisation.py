"""S15 - turns the index into the region the question asked about, measures it, and binds the answer to ground the operator can click.

what  : `localise_evidence`, the S15 node of the index-query graph.
where : Third node of `graphs/index_query.py`, after S12. The `geospatial-engine` model id's stage.
how   : Reads the S12 artefact back through the store rather than holding the array - which is what a
        resumed run does too, so the two paths cannot diverge. Thresholds it with the range the question
        resolved to (`services/spectral/math/thresholds.py`), measures the mask against the *observed*
        ground (`services/evidence/spatial.py`), retains the mask as an artefact, and hands everything
        to `services/evidence/builder.py`, which produces what this stage exists to produce:

        - **both representations** of the mask - a raster-mask tile layer over the retained COG, and a
          polygon layer whose features are the regions, each with its hectares and its mean reading;
        - the **evidence items** a claim may point at;
        - the **claims** themselves, with metrics, evidence ids, model and version, and the trace step id
          of this node - so every claim resolves to pixels by construction.

        Every layer, evidence item and claim is emitted the moment it exists (`layer-ready`, `claim`),
        and the completed trace step carries the polygon layer as its `artefactLayerId`.

        **The denominator is what was observed.** Pixels the S7 mask removed are neither detected nor
        observed; a field under cloud is not "not vegetated". `measure_mask` refuses a detection over
        unobserved ground, which is the structural check that S12 masked before it computed.

        A question that named an index without a range ("show me the ndwi") gets the map and the
        distribution, and no mask, no claims - there is nothing to assert until something says which
        values count.

        Two figures, both with this node's trace step id: the true-colour composite the overlay needs, and
        the overlay itself, marked primary because it is the picture that answers the question. Its
        `claimIds` are the claims it draws (`api-contract.md` §6 rule 4). A scene without red, green and
        blue gets neither, and the trace says so.
"""

import asyncio
import logging
from pathlib import Path

import numpy as np

from app.constants.evidence import (
    DETECTION_MASK_DETECTED,
    DETECTION_MASK_NOT_DETECTED,
    DETECTION_MASK_UNOBSERVED,
)
from app.constants.model_ids import ModelId
from app.constants.raster import BandRole, ProcessingLevel
from app.constants.spectral import GEOSPATIAL_ENGINE_VERSION, INTERPRETATION_BANDS, SpectralIndex
from app.constants.stages import PipelineStage
from app.schemas.events import ClaimEvent, LayerReadyEvent
from app.services.evidence.artefacts import read_artefact, store_artefact
from app.services.evidence.builder import RegionEvidence, build_region_evidence
from app.services.evidence.spatial import MaskStatistics, measure_mask
from app.services.evidence.trace import ModelRecord
from app.services.imagery.metadata import inspect_raster
from app.services.pipeline.node import (
    attach_artefact_layer,
    current_trace_step_id,
    describe_trace_step,
    pipeline_node,
)
from app.services.pipeline.state import AnalysisState, MeasurementState
from app.services.pipeline.stream import emit
from app.services.rendering.figures import render_mask_overlay, render_rgb_composite
from app.services.spectral.indices import locate_bands, read_scene_bands
from app.services.spectral.math.thresholds import summarise, within_range

logger = logging.getLogger(__name__)

TRUE_COLOUR_ROLES = (BandRole.RED, BandRole.GREEN, BandRole.BLUE)


@pipeline_node(
    PipelineStage.S15,
    detail="Localising the region and measuring it",
    model_id=ModelId.GEOSPATIAL_ENGINE,
    model_version=GEOSPATIAL_ENGINE_VERSION,
)
async def localise_evidence(state: AnalysisState) -> dict[str, object]:
    """S15. Threshold, measure against observed ground, retain, vectorise, claim, draw."""
    index = SpectralIndex(state["index"])
    run_id = state["run_id"]
    step_id = current_trace_step_id()
    # Read before inspect: the read restores a missing local copy from storage, the inspect needs it there.
    values = await read_artefact(Path(state["index_path"]), state["index_object_key"])
    reference = await inspect_raster(Path(state["index_path"]))
    crs = reference.crs or ""

    summary = await asyncio.to_thread(summarise, values, INTERPRETATION_BANDS[index])
    model = ModelRecord(
        stage=PipelineStage.S15, model_id=ModelId.GEOSPATIAL_ENGINE.value, model_version=GEOSPATIAL_ENGINE_VERSION
    )
    update: dict[str, object] = {"band_fractions": summary.band_fractions, "stage_models": [model.to_wire()]}

    lower, upper = state.get("target_lower"), state.get("target_upper")
    if lower is None or upper is None:
        describe_trace_step(
            f"{index.value.upper()} map only: {summary.observed_fraction:.1%} of the grid observed, "
            f"median {summary.median:.2f}; no range asked for, so nothing to measure"
        )
        return {
            **update, "mask_path": None, "mask_object_key": None, "mask_storage_uri": None,
            "mask_layer_id": None, "measurement": None, "composite_figure_id": None, "mask_figure_id": None,
        }

    detected, observed, encoded = await asyncio.to_thread(_threshold, values, lower, upper)
    statistics = await measure_mask(detected, observed, transform=reference.transform, crs=crs)

    artefact = await store_artefact(
        encoded,
        run_id=run_id,
        stage=PipelineStage.S15,
        name=f"{index.value}-{_slug(state['target_label'])}.tif",
        reference=reference,
        nodata=DETECTION_MASK_UNOBSERVED,
        categorical=True,
    )

    quantity_label = f"{index.value.upper()} {lower:.2f} to {upper:.2f}"
    evidence = await build_region_evidence(
        detected,
        values,
        statistics=statistics,
        transform=reference.transform,
        crs=crs,
        resolution_metres=float(reference.resolution[0]),
        run_id=run_id,
        trace_step_id=step_id,
        scene_id=state["scene_id"],
        mask_storage_uri=artefact.storage_uri,
        index_label=index.value.upper(),
        quantity_label=quantity_label,
        region_label=state["target_label"],
        lower=lower,
        upper=upper,
        obscured_fraction=state.get("obscured_fraction") if state.get("index_mask_applied") else None,
        unphysical_fraction=state.get("index_unphysical_fraction") or 0.0,
    )
    _emit_evidence(run_id, evidence)
    attach_artefact_layer(evidence.vector_layer.id)

    claim_ids = [claim.id for claim in evidence.claims]
    composite_id, overlay_id = await _draw(state, detected, quantity_label, crs, claim_ids)

    describe_trace_step(
        f"{state['target_label']} ({quantity_label}): "
        f"{statistics.detected.hectares:,.1f} ha, {statistics.coverage_fraction:.1%} of "
        f"{statistics.observed.hectares:,.1f} ha observed, {statistics.regions.region_count} regions "
        f"({evidence.regions_drawn} drawn), {len(evidence.claims)} claims"
    )
    return {
        **update,
        "mask_path": str(artefact.path),
        "mask_object_key": artefact.object_key,
        "mask_storage_uri": artefact.storage_uri,
        "mask_layer_id": evidence.raster_layer.id,
        "measurement": _as_state(statistics),
        "composite_figure_id": composite_id,
        "mask_figure_id": overlay_id,
        "layers": [evidence.raster_layer.to_wire(), evidence.vector_layer.to_wire()],
        "evidence_items": [item.to_wire() for item in evidence.evidence],
        "claims": [claim.to_wire() for claim in evidence.claims],
    }


def _emit_evidence(run_id: str, evidence: RegionEvidence) -> None:
    """Layers with their evidence first, claims after: nothing a claim points at arrives after the claim."""
    emit(LayerReadyEvent(run_id=run_id, layer=evidence.raster_layer, evidence=[]))
    emit(LayerReadyEvent(run_id=run_id, layer=evidence.vector_layer, evidence=evidence.evidence))
    for claim in evidence.claims:
        emit(ClaimEvent(run_id=run_id, claim=claim))


async def _draw(
    state: AnalysisState,
    detected: np.ndarray,
    quantity_label: str,
    crs: str,
    claim_ids: list[str],
) -> tuple[str | None, str | None]:
    """The composite and the overlay, or neither when the scene has no true-colour bands."""
    scene_directory = Path(state["scene_directory"])
    declared = state.get("declared_level")
    located = await locate_bands(scene_directory)
    if any(role not in located for role in TRUE_COLOUR_ROLES):
        logger.info("no true-colour bands for an overlay", extra={"scene": scene_directory.name})
        return None, None
    bands = await read_scene_bands(
        scene_directory, TRUE_COLOUR_ROLES, declared_level=ProcessingLevel(declared) if declared else None
    )

    scene_ids = [state["scene_id"]]
    label = f"{state['target_label']} ({quantity_label})"
    composite = await render_rgb_composite(
        bands.bands[BandRole.RED].reflectance,
        bands.bands[BandRole.GREEN].reflectance,
        bands.bands[BandRole.BLUE].reflectance,
        run_id=state["run_id"],
        trace_step_id=current_trace_step_id(),
        title=f"True colour - {state['scene_id']}",
        bands=[bands.bands[role].band_id for role in TRUE_COLOUR_ROLES],
        scene_ids=scene_ids,
        crs=crs,
    )
    emit(composite.event)

    overlay = await render_mask_overlay(
        detected,
        composite.rgba,
        run_id=state["run_id"],
        trace_step_id=current_trace_step_id(),
        title=f"{state['target_label']} - {state['scene_id']}",
        label=label,
        scene_ids=scene_ids,
        crs=crs,
        caption=f"{label} over the true-colour scene. Unobserved ground is not marked.",
        claim_ids=claim_ids,
        is_primary=True,
    )
    emit(overlay.event)
    return composite.event.figure_id, overlay.event.figure_id


def _threshold(
    values: np.ndarray, lower: float, upper: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The mask, the observed extent, and the mask as the byte raster S15 retains. Sync, for `to_thread`."""
    detected = within_range(values, lower, upper)
    observed = np.isfinite(values)
    encoded = np.full(detected.shape, DETECTION_MASK_NOT_DETECTED, dtype=np.uint8)
    encoded[detected] = DETECTION_MASK_DETECTED
    encoded[~observed] = DETECTION_MASK_UNOBSERVED
    return detected, observed, encoded


def _as_state(statistics: MaskStatistics) -> MeasurementState:
    return MeasurementState(
        areaHectares=statistics.detected.hectares,
        observedHectares=statistics.observed.hectares,
        coverageFraction=statistics.coverage_fraction,
        pixelCount=statistics.detected.pixel_count,
        regionCount=statistics.regions.region_count,
        regionDensityPerSquareKilometre=statistics.region_density_per_square_kilometre,
        largestRegionPixels=statistics.regions.largest_region_pixels,
        equalAreaCrs=statistics.equal_area_crs,
    )


def _slug(label: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in label.lower()).strip("-")
