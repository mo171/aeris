"""S15 - turns the index into the region the question asked about, and measures that region in hectares.

what  : `localise_evidence`, the S15 node of the index-query graph.
where : Third node of `graphs/index_query.py`, after S12. The `geospatial-engine` model id's stage. From
        1.5 its measurement becomes claim metrics and its mask becomes evidence polygons.
how   : Reads the S12 artefact back through the store rather than holding the array - which is what a
        resumed run does too, so the two paths cannot diverge. Thresholds it with the range the question
        resolved to (`services/spectral/math/thresholds.py`), measures the mask against the *observed*
        ground (`services/evidence/spatial.py`), retains the mask as an artefact, and draws it over the
        true-colour scene as the run's primary figure.

        **The denominator is what was observed.** Pixels the S7 mask removed are neither detected nor
        observed; a field under cloud is not "not vegetated". `measure_mask` refuses a detection over
        unobserved ground, which is the structural check that S12 masked before it computed.

        A question that named an index without a range ("show me the ndwi") gets the map and the
        distribution, and no mask - there is nothing to measure until something says which values count.

        Two figures, both with this node's trace step id: the true-colour composite the overlay needs, and
        the overlay itself, marked primary because it is the picture that answers the question. A scene
        without red, green and blue gets neither, and the trace says so.
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
from app.services.evidence.artefacts import read_artefact, store_artefact
from app.services.evidence.spatial import MaskStatistics, measure_mask
from app.services.imagery.metadata import inspect_raster
from app.services.pipeline.node import current_trace_step_id, describe_trace_step, pipeline_node
from app.services.pipeline.state import IndexQueryState, MeasurementState
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
async def localise_evidence(state: IndexQueryState) -> dict[str, object]:
    """S15. Threshold, measure against observed ground, retain the mask, draw it."""
    index = SpectralIndex(state["index"])
    # Read before inspect: the read restores a missing local copy from storage, the inspect needs it there.
    values = await read_artefact(Path(state["index_path"]), state["index_object_key"])
    reference = await inspect_raster(Path(state["index_path"]))
    crs = reference.crs or ""

    summary = await asyncio.to_thread(summarise, values, INTERPRETATION_BANDS[index])
    update: dict[str, object] = {"band_fractions": summary.band_fractions}

    lower, upper = state.get("target_lower"), state.get("target_upper")
    if lower is None or upper is None:
        describe_trace_step(
            f"{index.value.upper()} map only: {summary.observed_fraction:.1%} of the grid observed, "
            f"median {summary.median:.2f}; no range asked for, so nothing to measure"
        )
        return {**update, "mask_path": None, "mask_object_key": None, "measurement": None,
                "composite_figure_id": None, "mask_figure_id": None}

    detected, observed, encoded = await asyncio.to_thread(_threshold, values, lower, upper)
    statistics = await measure_mask(detected, observed, transform=reference.transform, crs=crs)

    artefact = await store_artefact(
        encoded,
        run_id=state["run_id"],
        stage=PipelineStage.S15,
        name=f"{index.value}-{_slug(state['target_label'])}.tif",
        reference=reference,
        nodata=DETECTION_MASK_UNOBSERVED,
        categorical=True,
    )

    composite_id, overlay_id = await _draw(state, index, detected, lower, upper, crs)

    describe_trace_step(
        f"{state['target_label']} ({index.value.upper()} {lower:.2f} to {upper:.2f}): "
        f"{statistics.detected.hectares:,.1f} ha, {statistics.coverage_fraction:.1%} of "
        f"{statistics.observed.hectares:,.1f} ha observed, {statistics.regions.region_count} regions"
    )
    return {
        **update,
        "mask_path": str(artefact.path),
        "mask_object_key": artefact.object_key,
        "measurement": _as_state(statistics),
        "composite_figure_id": composite_id,
        "mask_figure_id": overlay_id,
    }


async def _draw(
    state: IndexQueryState,
    index: SpectralIndex,
    detected: np.ndarray,
    lower: float,
    upper: float,
    crs: str,
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
    label = f"{state['target_label']} ({index.value.upper()} {lower:.2f} to {upper:.2f})"
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
