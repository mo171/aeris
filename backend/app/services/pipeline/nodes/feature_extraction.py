"""S12 - computes the index the question asked for, over masked reflectance, and shows it the moment it exists.

what  : `extract_features`, the S12 node of the index-query graph.
where : Second node of `graphs/index_query.py`, after S7 and before S15. The `index-engine` model id's
        stage. 1.10's single-image graph reuses it unchanged.
how   : Three things happen here and nothing is computed: the bands are read onto one grid as surface
        reflectance (`services/spectral/indices.py` refuses L1C and unknown levels on the way), the S7
        mask is read back and handed to `compute_index`, which applies it to the *inputs* before the
        formula runs, and the result becomes two things - a retained artefact and a rendered figure.

        **The figure carries this node's own trace step id** (`api-contract.md` §6 rule 1), read from the
        decorator through `current_trace_step_id()`. Its caption states whether the mask was applied and
        carries no number: numbers arrive on figures with the claims that back them, in 1.5.

        `unphysical_fraction` goes into the trace detail rather than being absorbed. A formula that
        refused a third of the observed ground is a formula that was the wrong choice for this ground,
        and the operator should read that beside the stage rather than discover it in a figure's holes.
"""

import logging
from pathlib import Path

from app.constants.model_ids import ModelId
from app.constants.raster import ProcessingLevel
from app.constants.spectral import INDEX_BAND_ROLES, INDEX_ENGINE_VERSION, SpectralIndex
from app.constants.stages import PipelineStage
from app.services.evidence.artefacts import read_artefact, store_artefact
from app.services.pipeline.node import current_trace_step_id, describe_trace_step, pipeline_node
from app.services.pipeline.state import IndexQueryState
from app.services.pipeline.stream import emit
from app.services.preprocessing.cloud_masking import OpticalMaskResult, decode_mask_raster
from app.services.rendering.figures import render_index_map
from app.services.spectral.indices import compute_index, read_scene_bands

logger = logging.getLogger(__name__)


@pipeline_node(
    PipelineStage.S12,
    detail="Computing the spectral index over masked reflectance",
    model_id=ModelId.INDEX_ENGINE,
    model_version=INDEX_ENGINE_VERSION,
)
async def extract_features(state: IndexQueryState) -> dict[str, object]:
    """S12. Mask first, formula second, artefact and figure third."""
    scene_directory = Path(state["scene_directory"])
    index = SpectralIndex(state["index"])
    declared = state.get("declared_level")

    bands = await read_scene_bands(
        scene_directory,
        INDEX_BAND_ROLES[index],
        declared_level=ProcessingLevel(declared) if declared else None,
    )
    mask = await _mask_from_state(state)
    result = await compute_index(bands, index, mask=mask)

    artefact = await store_artefact(
        result.values,
        run_id=state["run_id"],
        stage=PipelineStage.S12,
        name=f"{index.value}.tif",
        reference=result.reference,
    )

    figure = await render_index_map(
        result.values,
        run_id=state["run_id"],
        trace_step_id=current_trace_step_id(),
        title=f"{index.value.upper()} - {result.scene_id}",
        label=index.value.upper(),
        bands=result.band_ids,
        scene_ids=[result.scene_id],
        crs=result.crs,
        mask_applied=result.mask_applied,
        caption=_caption(index, result.mask_applied),
    )
    emit(figure.event)

    describe_trace_step(
        f"{index.value.upper()} from {', '.join(result.band_ids)} over "
        f"{result.reference.width}x{result.reference.height}"
        + (f", {', '.join(result.resampled_band_ids)} resampled" if result.resampled_band_ids else "")
        + (
            f"; mask applied, {result.obscured_fraction:.1%} obscured"
            if result.mask_applied and result.obscured_fraction is not None
            else "; no mask applied"
        )
        + (f"; {result.unphysical_fraction:.1%} refused by the formula" if result.unphysical_fraction else "")
    )
    return {
        "index_path": str(artefact.path),
        "index_object_key": artefact.object_key,
        "index_band_ids": result.band_ids,
        "index_mask_applied": result.mask_applied,
        "index_unphysical_fraction": result.unphysical_fraction,
        "index_figure_id": figure.event.figure_id,
    }


async def _mask_from_state(state: IndexQueryState) -> OpticalMaskResult | None:
    """The S7 artefact, read back through the store - the same path a resumed run takes."""
    path = state.get("cloud_mask_path")
    key = state.get("cloud_mask_object_key")
    if path is None or key is None:
        return None
    return await decode_mask_raster(await read_artefact(Path(path), key))


def _caption(index: SpectralIndex, mask_applied: bool) -> str:
    """No number in a caption until a claim carries it (`api-contract.md` §6 rule 4)."""
    if mask_applied:
        return (
            f"{index.value.upper()} over the scene. Cloud and shadow were masked before the arithmetic and "
            "are transparent."
        )
    return f"{index.value.upper()} over the scene. No cloud mask was available; values over cloud are included."
