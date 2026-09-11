"""S7 - reads the scene's cloud and shadow mask onto the analysis grid and retains it, or says plainly that there is none.

what  : `handle_clouds`, the S7 node of the index-query graph.
where : First node of `graphs/index_query.py`, ahead of S12 so the mask exists before any arithmetic
        (`architecture-context.md` §8 rule 1). 1.10's single-image graph reuses it unchanged.
how   : The mask source is the L2A product's own scene classification layer - the only S7 source an L2A
        scene can supply, since s2cloudless needs the B10 that L2A does not carry
        (`services/preprocessing/cloud_masking.py`). The SCL is 20 m; it is brought onto the 10 m analysis
        grid with nearest neighbour before it is read, because it holds class labels (§8 rule 6).

        **A scene without an SCL is not refused, and is not silently accepted either.** The node records
        no mask, the trace says so in words, and S12 carries `maskApplied: false` into the figure's
        `renderSpec` - the honest form 1.2.1 established. Refusing would make every research subset
        unanalysable; guessing a mask from the visible bands would be inventing evidence.

        The mask is an artefact (S7 `producesArtefact: true`), so it is stored and the state carries its
        path and key. S12 reads it back through the same artefact store a resumed run would.
"""

import logging
from pathlib import Path

from app.constants.preprocessing import MASK_UNOBSERVED
from app.constants.raster import ProcessingLevel
from app.constants.spectral import INDEX_BAND_ROLES, SpectralIndex
from app.constants.stages import PipelineStage
from app.services.evidence.artefacts import store_artefact
from app.services.pipeline.node import describe_trace_step, pipeline_node
from app.services.pipeline.state import IndexQueryState
from app.services.preprocessing.cloud_masking import encode_mask_raster, mask_from_scene_classification
from app.services.spectral.indices import analysis_grid, read_scene_classification, require_surface_reflectance

logger = logging.getLogger(__name__)

CLOUD_MASK_ARTEFACT_NAME = "cloud-mask.tif"


@pipeline_node(PipelineStage.S7, detail="Reading the cloud and shadow mask")
async def handle_clouds(state: IndexQueryState) -> dict[str, object]:
    """S7. The scene classification layer becomes the mask S12 applies before it computes anything."""
    scene_directory = Path(state["scene_directory"])
    index = SpectralIndex(state["index"])
    declared = state.get("declared_level")

    reference = await analysis_grid(scene_directory, INDEX_BAND_ROLES[index])
    await require_surface_reflectance(reference, ProcessingLevel(declared) if declared else None)

    scene_classification = await read_scene_classification(scene_directory, reference)
    if scene_classification is None:
        describe_trace_step(
            f"no cloud mask: {scene_directory.name} carries no scene classification layer; "
            f"{index.value.upper()} will be reported unmasked"
        )
        return {"cloud_mask_path": None, "cloud_mask_object_key": None, "obscured_fraction": None}

    mask = await mask_from_scene_classification(scene_classification)
    encoded = await encode_mask_raster(mask)
    artefact = await store_artefact(
        encoded,
        run_id=state["run_id"],
        stage=PipelineStage.S7,
        name=CLOUD_MASK_ARTEFACT_NAME,
        reference=reference,
        nodata=MASK_UNOBSERVED,
        categorical=True,
    )

    describe_trace_step(
        f"SCL mask on {reference.width}x{reference.height}: {mask.obscured_fraction:.1%} obscured "
        f"(cloud {mask.cloud_mask.mean():.1%}, shadow {mask.shadow_mask.mean():.1%})"
    )
    return {
        "cloud_mask_path": str(artefact.path),
        "cloud_mask_object_key": artefact.object_key,
        "obscured_fraction": mask.obscured_fraction,
    }
