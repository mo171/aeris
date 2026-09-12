"""S19 - writes the record that lets any claim be walked back to pixels, parameters and versions, and the evidence graph the frontend will fetch.

what  : `log_provenance`, the S19 node of the index-query graph.
where : Last node of `graphs/index_query.py`. Writes `runs/<run_id>/provenance.json` and
        `runs/<run_id>/evidence-graph.json` through `services/evidence/trace.py`.
how   : Assembles both records from the state and nothing else - the same rule the completion event
        follows for confidence: the checkpoint is what a resumed run sees, and a record built from
        anything a node held in memory would differ from one built after a resume.

        The provenance record carries what PDF §21.2 asks for and the wire does not: the input files with
        their SHA-256 hashes, CRS and level; the parameters (which index, which range, which coefficients
        version); every stage's engine and version; every retained artefact's object key and storage URI
        with the layer that draws it; the trace step, claim and figure ids; and the confidence rule and
        result. The evidence graph is the frontend's `evidenceGraphSchema`, flat and keyed by id, written
        wire-shaped so the Phase 2 endpoint serves it unchanged.

        Append-only in effect: a run id is minted once, the directory is the run's, and nothing rewrites a
        record after the run completes.
"""

from datetime import UTC, datetime
from pathlib import Path

from app.constants.evidence import CONFIDENCE_AGGREGATION_RULE
from app.constants.spectral import (
    EVI_BLUE_COEFFICIENT,
    EVI_CANOPY_BACKGROUND,
    EVI_GAIN,
    EVI_RED_COEFFICIENT,
    INDEX_ENGINE_VERSION,
    SAVI_SOIL_BRIGHTNESS,
)
from app.constants.stages import PipelineStage
from app.schemas.events import Claim, EvidenceItem, EvidenceLayer
from app.services.evidence.trace import (
    ArtefactRecord,
    EvidenceGraph,
    InputFileRecord,
    ModelRecord,
    ProvenanceRecord,
    write_evidence_graph,
    write_provenance,
)
from app.services.pipeline.node import describe_trace_step, pipeline_node
from app.services.pipeline.state import IndexQueryState


@pipeline_node(PipelineStage.S19, detail="Recording provenance and the evidence graph")
async def log_provenance(state: IndexQueryState) -> dict[str, object]:
    """S19. Two files beside the journal, both built from the checkpoint alone."""
    run_id = state["run_id"]
    layers = [EvidenceLayer.model_validate(layer) for layer in state.get("layers", [])]
    evidence = [EvidenceItem.model_validate(item) for item in state.get("evidence_items", [])]
    claims = [Claim.model_validate(claim) for claim in state.get("claims", [])]

    record = ProvenanceRecord(
        run_id=run_id,
        query=state["query"],
        intent=state["intent"],
        scene_id=state["scene_id"],
        generated_at=datetime.now(UTC),
        inputs=[InputFileRecord.model_validate(item) for item in state.get("input_files", [])],
        parameters={
            "index": state["index"],
            "targetLower": state.get("target_lower"),
            "targetUpper": state.get("target_upper"),
            "targetLabel": state.get("target_label"),
            "targetPhrase": state.get("target_phrase"),
            "declaredLevel": state.get("declared_level"),
            "indexEngineVersion": INDEX_ENGINE_VERSION,
            "eviCoefficients": {
                "gain": EVI_GAIN, "red": EVI_RED_COEFFICIENT, "blue": EVI_BLUE_COEFFICIENT,
                "canopyBackground": EVI_CANOPY_BACKGROUND,
            },
            "saviSoilBrightness": SAVI_SOIL_BRIGHTNESS,
            "maskApplied": state.get("index_mask_applied", False),
            "obscuredFraction": state.get("obscured_fraction"),
            "unphysicalFraction": state.get("index_unphysical_fraction"),
        },
        models=[ModelRecord.model_validate(item) for item in state.get("stage_models", [])],
        reading={
            "figureId": state.get("reading_figure_id"), "prompt": state.get("reading_prompt"),
            "text": state.get("reading_text"), "wordingCertainty": state.get("reading_confidence"),
            "spokenInAnswer": state.get("reading_spoken", False),
        } if state.get("reading_text") else None,
        artefacts=_artefacts(state),
        trace_step_ids=list(state.get("trace_step_ids", [])),
        claim_ids=[claim.id for claim in claims],
        figure_ids=[
            figure_id
            for figure_id in (
                state.get("index_figure_id"), state.get("composite_figure_id"), state.get("mask_figure_id")
            )
            if figure_id
        ],
        confidence_aggregation_rule=state.get("confidence_aggregation_rule", CONFIDENCE_AGGREGATION_RULE),
        confidence=state.get("confidence"),
    )
    provenance = await write_provenance(record)
    graph = await write_evidence_graph(run_id, EvidenceGraph(claims=claims, evidence=evidence, layers=layers))

    describe_trace_step(
        f"{len(record.inputs)} inputs hashed, {len(record.artefacts)} artefacts, {len(record.models)} "
        f"engines, {len(claims)} claims, {len(layers)} layers -> {provenance.name}, {graph.name}"
    )
    return {"provenance_path": str(provenance), "evidence_graph_path": str(graph)}


def _artefacts(state: IndexQueryState) -> list[ArtefactRecord]:
    """Every retained intermediate, with the layer that draws it where the stage emitted one."""
    records = []
    for stage, path_key, object_key, uri_key, layer_key in (
        (PipelineStage.S7, "cloud_mask_path", "cloud_mask_object_key", "cloud_mask_storage_uri", None),
        (PipelineStage.S12, "index_path", "index_object_key", "index_storage_uri", "index_layer_id"),
        (PipelineStage.S15, "mask_path", "mask_object_key", "mask_storage_uri", "mask_layer_id"),
    ):
        path = state.get(path_key)
        if not path:
            continue
        records.append(
            ArtefactRecord(
                stage=stage,
                name=Path(path).name,
                object_key=state[object_key],  # type: ignore[literal-required]
                storage_uri=state[uri_key],  # type: ignore[literal-required]
                local_path=path,
                layer_id=state.get(layer_key) if layer_key else None,  # type: ignore[arg-type]
            )
        )
    return records
