"""S7 - reads the scene's cloud and shadow mask onto the analysis grid and retains it, or says plainly that there is none.

what  : `handle_clouds`, the S7 node of the single-image and temporal graphs.
where : After S1 and ahead of S12 or S13, so the mask exists before any arithmetic or any model
        (`architecture-context.md` §8 rule 1). The graph's edge sends only an optical scene directory
        here; a picture has no classification layer and skips the stage rather than announcing one.
how   : The mask source is the L2A product's own scene classification layer - the only S7 source an L2A
        scene can supply, since s2cloudless needs the B10 that L2A does not carry
        (`services/preprocessing/cloud_masking.py`). The SCL is 20 m; it is brought onto the 10 m analysis
        grid with nearest neighbour before it is read, because it holds class labels (§8 rule 6).

        **The grid is the one the run will compute on**: the index's bands for an index question, the
        true-colour bands for a specialist that reads a picture. Both S7 and the stage after it derive it
        from the same roles, so they cannot disagree. A temporal run masks both dates; the earlier one
        lands under `reference_*` keys and S13 turns either date's obscured ground into unobserved.

        **A scene without an SCL is not refused, and is not silently accepted either.** The node records
        no mask, the trace says so in words, and S12 carries `maskApplied: false` into the figure's
        `renderSpec` - the honest form 1.2.1 established. Refusing would make every research subset
        unanalysable; guessing a mask from the visible bands would be inventing evidence.

        The mask is an artefact (S7 `producesArtefact: true`), so it is stored and the state carries its
        path and key. S12 reads it back through the same artefact store a resumed run would.

        **No layer, and no `artefactLayerId`, when the mask came from the SCL.** A layer must name the
        model that produced it (`layerProvenanceSchema.modelId`), and the fleet vocabulary has no entry for
        Sen2Cor - the classifier ESA ran to make the SCL. Claiming `s2cloudless` would be a false
        attribution, which is the one thing a provenance field must never carry. The artefact is still
        retained and recorded with its object key in the provenance record (S19); what is owed is a
        vocabulary entry, and `memory.md` says so. The s2cloudless path (an L1C scene) gets its layer.
"""

import logging
from pathlib import Path

from app.constants.preprocessing import MASK_UNOBSERVED
from app.constants.raster import BandRole, ProcessingLevel
from app.constants.spectral import INDEX_BAND_ROLES, SpectralIndex
from app.constants.stages import PipelineStage
from app.services.evidence.artefacts import store_artefact
from app.services.evidence.trace import InputFileRecord, hash_file
from app.services.imagery.frames import TRUE_COLOUR_ROLES
from app.services.imagery.metadata import inspect_raster
from app.services.pipeline.node import describe_trace_step, pipeline_node
from app.services.pipeline.state import AnalysisState
from app.services.preprocessing.cloud_masking import encode_mask_raster, mask_from_scene_classification
from app.services.spectral.indices import (
    analysis_grid,
    locate_bands,
    read_scene_classification,
    require_surface_reflectance,
)

logger = logging.getLogger(__name__)

CLOUD_MASK_ARTEFACT_NAME = "cloud-mask.tif"


@pipeline_node(PipelineStage.S7, detail="Reading the cloud and shadow mask")
async def handle_clouds(state: AnalysisState) -> dict[str, object]:
    """S7. The scene classification layer becomes the mask the next stage applies before it computes anything."""
    index = SpectralIndex(state["index"]) if state.get("index") else None
    roles = INDEX_BAND_ROLES[index] if index is not None else TRUE_COLOUR_ROLES
    declared = state.get("declared_level")
    what = index.value.upper() if index is not None else "the picture"

    primary, primary_line = await _mask_scene(
        Path(state["scene_directory"]), roles, run_id=state["run_id"], name=CLOUD_MASK_ARTEFACT_NAME, what=what,
        declared_level=ProcessingLevel(declared) if declared else None, reflectance_required=index is not None,
    )
    update: dict[str, object] = {
        "cloud_mask_path": primary["path"], "cloud_mask_object_key": primary["key"],
        "cloud_mask_storage_uri": primary["uri"], "obscured_fraction": primary["obscured"],
        "input_files": [primary["read"]] if primary["read"] else [],
    }
    lines = [primary_line]
    if state.get("reference_directory"):
        reference, reference_line = await _mask_scene(
            Path(state["reference_directory"]), roles, run_id=state["run_id"], name=f"reference-{CLOUD_MASK_ARTEFACT_NAME}",
            what=what, declared_level=ProcessingLevel(declared) if declared else None, reflectance_required=False,
        )
        update.update({
            "reference_cloud_mask_path": reference["path"], "reference_cloud_mask_object_key": reference["key"],
            "reference_obscured_fraction": reference["obscured"],
            "input_files": [*update["input_files"], reference["read"]] if reference["read"] else update["input_files"],  # type: ignore[misc]
        })
        lines.insert(0, f"earlier date: {reference_line}")
        lines[1] = f"later date: {lines[1]}"
    describe_trace_step("; ".join(lines))
    return update


async def _mask_scene(
    scene_directory: Path, roles: tuple[BandRole, ...], *, run_id: str, name: str, what: str,
    declared_level: ProcessingLevel | None, reflectance_required: bool,
) -> tuple[dict[str, object], str]:
    """One scene's mask, retained, or the reason there is none. Returns the state values and the trace line."""
    reference = await analysis_grid(scene_directory, roles)
    if reflectance_required:
        await require_surface_reflectance(reference, declared_level)

    scene_classification = await read_scene_classification(scene_directory, reference)
    if scene_classification is None:
        return (
            {"path": None, "key": None, "uri": None, "obscured": None, "read": None},
            f"no cloud mask: {scene_directory.name} carries no scene classification layer; {what} will be reported unmasked",
        )

    mask = await mask_from_scene_classification(scene_classification)
    encoded = await encode_mask_raster(mask)
    artefact = await store_artefact(
        encoded, run_id=run_id, stage=PipelineStage.S7, name=name, reference=reference, nodata=MASK_UNOBSERVED, categorical=True,
    )
    scl_path = (await locate_bands(scene_directory))[BandRole.SCENE_CLASSIFICATION]
    scl = await inspect_raster(scl_path)
    read = InputFileRecord(
        path=str(scl_path), band_id=BandRole.SCENE_CLASSIFICATION.value.upper(), role=BandRole.SCENE_CLASSIFICATION.value,
        sha256=await hash_file(scl_path), crs=scl.crs, processing_level=scl.processing_level.value, width=scl.width, height=scl.height,
        resolution_metres=float(scl.resolution[0]),
    )
    return (
        {"path": str(artefact.path), "key": artefact.object_key, "uri": artefact.storage_uri, "obscured": mask.obscured_fraction, "read": read.to_wire()},
        f"SCL mask on {reference.width}x{reference.height}: {mask.obscured_fraction:.1%} obscured "
        f"(cloud {mask.cloud_mask.mean():.1%}, shadow {mask.shadow_mask.mean():.1%})",
    )
