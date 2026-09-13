"""Gives a node back the inputs S1 inspected and the picture S13 reads - from the state, so a resumed run sees the same.

what  : `primary_input()`, `reference_input()`, `primary_frame()`, `reference_frame()`, and
        `restore_mask()` - the S7 mask read back through the artefact store.
where : The S13 and S14 nodes (`nodes/object_detection.py`, `nodes/segmentation.py`,
        `nodes/change_detection.py`, `nodes/vlm_reading.py`).
how   : The state carries paths and flags, never the `AnalysisInput` (it holds a `RasterMetadata`; a
        checkpoint holds data). Re-inspecting a path costs a header read and guarantees that a node in a
        new process reads what S1 read. The frame is masked by S7's artefact, fetched from storage when
        the local copy is gone - the same rule S12 follows for its index.
"""

from pathlib import Path

from app.constants.raster import ProcessingLevel
from app.services.evidence.artefacts import read_artefact
from app.services.imagery.frames import AnalysisInput, RgbFrame, inspect_input, read_rgb_frame
from app.services.pipeline.state import AnalysisState
from app.services.preprocessing.cloud_masking import OpticalMaskResult, decode_mask_raster


async def primary_input(state: AnalysisState) -> AnalysisInput:
    return await inspect_input(
        Path(state["scene_directory"]), declared_resolution_metres=state.get("declared_resolution_metres"), is_sar=bool(state.get("is_sar")),
    )


async def reference_input(state: AnalysisState) -> AnalysisInput:
    return await inspect_input(
        Path(state["reference_directory"]), declared_resolution_metres=state.get("declared_resolution_metres"),
        is_sar=bool(state.get("reference_is_sar")),
    )


async def restore_mask(path: str | None, object_key: str | None) -> OpticalMaskResult | None:
    """The S7 artefact, or `None` when S7 recorded no mask source."""
    if path is None or object_key is None:
        return None
    return await decode_mask_raster(await read_artefact(Path(path), object_key))


async def primary_frame(state: AnalysisState) -> RgbFrame:
    """The later (or only) date's picture, with S7's mask applied where one was retained."""
    declared = state.get("declared_level")
    mask = await restore_mask(state.get("cloud_mask_path"), state.get("cloud_mask_object_key"))
    return await read_rgb_frame(await primary_input(state), declared_level=ProcessingLevel(declared) if declared else None, mask=mask)


async def reference_frame(state: AnalysisState) -> RgbFrame:
    """The earlier date's picture (temporal graph), with its own S7 mask applied."""
    declared = state.get("declared_level")
    mask = await restore_mask(state.get("reference_cloud_mask_path"), state.get("reference_cloud_mask_object_key"))
    return await read_rgb_frame(await reference_input(state), declared_level=ProcessingLevel(declared) if declared else None, mask=mask)
