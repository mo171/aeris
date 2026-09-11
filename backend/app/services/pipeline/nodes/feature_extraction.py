"""S12 - computes the index the question asked for, over masked reflectance, and shows it the moment it exists.

what  : `extract_features`, the S12 node of the index-query graph.
where : Second node of `graphs/index_query.py`, after S7 and before S15. The `index-engine` model id's
        stage. 1.10's single-image graph reuses it unchanged.
how   : Nothing is computed here. The bands are read onto one grid as surface reflectance
        (`services/spectral/indices.py` refuses L1C and unknown levels on the way), the S7 mask is read
        back and handed to `compute_index`, which applies it to the *inputs* before the formula runs, and
        the result becomes three things: a retained artefact, a tile layer over it, and a rendered figure.

        **The layer is what the trace step points at.** S12 `producesArtefact: true`, so its completed
        trace step carries `artefactLayerId` (`api-contract.md` §1 rule 10) - the operator clicks the step
        and the index map is drawn onto the scene. The figure carries the same trace step id (§6 rule 1).
        Both are read from the decorator through `current_trace_step_id()`.

        **Every band file read is hashed into the state** (PDF §21.2, reproducibility). S19 writes the
        hashes into the provenance record; a re-fetched scene with the same file names is a different
        input, and the hash is what says so.

        `unphysical_fraction` goes into the trace detail rather than being absorbed. A formula that
        refused a third of the observed ground is a formula that was the wrong choice for this ground,
        and the operator should read that beside the stage rather than discover it in a figure's holes.
"""

import asyncio
import logging
from pathlib import Path

from app.constants.color_ramps import MATPLOTLIB_COLORMAPS, ColorRampId
from app.constants.evidence import EvidenceKind
from app.constants.layers import SURFACE_LAYER_OPACITY, LayerKind
from app.constants.model_ids import ModelId
from app.constants.raster import ProcessingLevel
from app.constants.spectral import (
    INDEX_BAND_ROLES,
    INDEX_DOMAIN,
    INDEX_ENGINE_VERSION,
    INTERPRETATION_BANDS,
    SpectralIndex,
)
from app.constants.stages import PipelineStage
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.schemas.events import EvidenceItem, LayerProvenance, LayerReadyEvent, ValueDomain
from app.services.evidence.artefacts import read_artefact, store_artefact
from app.services.evidence.builder import build_raster_layer, grid_extent
from app.services.evidence.trace import InputFileRecord, ModelRecord, hash_file
from app.services.pipeline.node import (
    attach_artefact_layer,
    current_trace_step_id,
    describe_trace_step,
    pipeline_node,
)
from app.services.pipeline.state import IndexQueryState
from app.services.pipeline.stream import emit
from app.services.preprocessing.cloud_masking import OpticalMaskResult, decode_mask_raster
from app.services.rendering.figures import render_index_map
from app.services.spectral.indices import SceneBands, compute_index, read_scene_bands
from app.services.spectral.math.thresholds import summarise

logger = logging.getLogger(__name__)


@pipeline_node(
    PipelineStage.S12,
    detail="Computing the spectral index over masked reflectance",
    model_id=ModelId.INDEX_ENGINE,
    model_version=INDEX_ENGINE_VERSION,
)
async def extract_features(state: IndexQueryState) -> dict[str, object]:
    """S12. Mask first, formula second; then artefact, layer and figure."""
    scene_directory = Path(state["scene_directory"])
    index = SpectralIndex(state["index"])
    declared = state.get("declared_level")
    run_id = state["run_id"]
    step_id = current_trace_step_id()

    bands = await read_scene_bands(
        scene_directory, INDEX_BAND_ROLES[index], declared_level=ProcessingLevel(declared) if declared else None
    )
    mask = await _mask_from_state(state)
    result = await compute_index(bands, index, mask=mask)

    artefact = await store_artefact(
        result.values, run_id=run_id, stage=PipelineStage.S12, name=f"{index.value}.tif", reference=result.reference
    )

    summary = await asyncio.to_thread(summarise, result.values, INTERPRETATION_BANDS[index])
    extent = await grid_extent(
        result.transform, result.crs, result.values.shape, float(result.reference.resolution[0])
    )
    layer = await build_raster_layer(
        title=f"{index.value.upper()} - {result.scene_id}",
        kind=LayerKind.RASTER_TILES,
        overlay_id=index.value,
        storage_uri=artefact.storage_uri,
        extent=extent,
        color_ramp_id=ColorRampId.INDEX_VEGETATION,
        opacity=SURFACE_LAYER_OPACITY,
        provenance=LayerProvenance(
            model_id=ModelId.INDEX_ENGINE.value,
            model_version=INDEX_ENGINE_VERSION,
            trace_step_id=step_id,
            confidence=None,
        ),
        value_domain=(
            ValueDomain(minimum=summary.percentile_2, maximum=summary.percentile_98)
            if summary.observed_count
            else None
        ),
        # Server-side stretch and ramp (`api-contract.md` §8 rule 5): the browser never does band math.
        rendering={
            "rescale": f"{INDEX_DOMAIN[0]},{INDEX_DOMAIN[1]}",
            "colormap_name": MATPLOTLIB_COLORMAPS[ColorRampId.INDEX_VEGETATION].lower(),
        },
    )
    evidence = EvidenceItem(
        id=new_identifier(IdentifierPrefix.EVIDENCE),
        kind=EvidenceKind.INDEX_MAP,
        title=f"{index.value.upper()} map",
        layer_id=layer.id,
        feature_ids=[],
        area_hectares=None,
        magnitude=summary.observed_fraction,
        confidence=None,
        source_scene_ids=[result.scene_id],
    )
    attach_artefact_layer(layer.id)
    emit(LayerReadyEvent(run_id=run_id, layer=layer, evidence=[evidence]))

    figure = await render_index_map(
        result.values,
        run_id=run_id,
        trace_step_id=step_id,
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
    model = ModelRecord(
        stage=PipelineStage.S12, model_id=ModelId.INDEX_ENGINE.value, model_version=INDEX_ENGINE_VERSION
    )
    return {
        "index_path": str(artefact.path),
        "index_object_key": artefact.object_key,
        "index_storage_uri": artefact.storage_uri,
        "index_band_ids": result.band_ids,
        "index_mask_applied": result.mask_applied,
        "index_unphysical_fraction": result.unphysical_fraction,
        "index_figure_id": figure.event.figure_id,
        "index_layer_id": layer.id,
        "input_files": [record.to_wire() for record in await _input_records(bands)],
        "layers": [layer.to_wire()],
        "evidence_items": [evidence.to_wire()],
        "stage_models": [model.to_wire()],
    }


async def _mask_from_state(state: IndexQueryState) -> OpticalMaskResult | None:
    """The S7 artefact, read back through the store - the same path a resumed run takes."""
    path = state.get("cloud_mask_path")
    key = state.get("cloud_mask_object_key")
    if path is None or key is None:
        return None
    return await decode_mask_raster(await read_artefact(Path(path), key))


async def _input_records(bands: SceneBands) -> list[InputFileRecord]:
    """One hashed record per band file read."""
    records = []
    for band in bands.bands.values():
        source = band.source
        records.append(
            InputFileRecord(
                path=str(source.path),
                band_id=band.band_id,
                role=band.role.value,
                sha256=await hash_file(source.path),
                crs=source.crs,
                processing_level=bands.processing_level.value,
                width=source.width,
                height=source.height,
                resolution_metres=float(source.resolution[0]),
            )
        )
    return records


def _caption(index: SpectralIndex, mask_applied: bool) -> str:
    """No number in a caption until a claim carries it (`api-contract.md` §6 rule 4)."""
    if mask_applied:
        return (
            f"{index.value.upper()} over the scene. Cloud and shadow were masked before the arithmetic and "
            "are transparent."
        )
    return f"{index.value.upper()} over the scene. No cloud mask was available; values over cloud are included."
