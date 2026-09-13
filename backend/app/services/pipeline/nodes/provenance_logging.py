"""S19 - writes the record that lets any claim be walked back to pixels, parameters and versions, and the evidence graph the frontend will fetch.

what  : `log_provenance`, the S19 node of every graph.
where : Last node of the single-image and temporal graphs. Writes `runs/<run_id>/provenance.json` and
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

        The parameters and artefacts are whatever the run's branch left in the state (1.10): an index's
        range and coefficients, a detector's classes and threshold, a segmenter's classes, a pair's
        registration and change threshold. A key absent from the state is absent from the record - the
        record describes the run that happened, not the union of runs that could have.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from app.services.pipeline.state import AnalysisState


@pipeline_node(PipelineStage.S19, detail="Recording provenance and the evidence graph")
async def log_provenance(state: AnalysisState) -> dict[str, object]:
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
        parameters=_parameters(state),
        models=[ModelRecord.model_validate(item) for item in state.get("stage_models", [])],
        reading={
            "figureId": state.get("reading_figure_id"), "prompt": state.get("reading_prompt"),
            "text": state.get("reading_text"), "wordingCertainty": state.get("reading_confidence"),
            "spokenInAnswer": state.get("reading_spoken", False),
        } if state.get("reading_text") else None,
        artefacts=_artefacts(state),
        trace_step_ids=list(state.get("trace_step_ids", [])),
        claim_ids=[claim.id for claim in claims],
        figure_ids=_figure_ids(state),
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


def _parameters(state: AnalysisState) -> dict[str, Any]:
    """What the run was asked and how it was configured - only the keys this run's branch set."""
    parameters: dict[str, Any] = {
        "declaredLevel": state.get("declared_level"),
        "declaredResolutionMetres": state.get("declared_resolution_metres"),
        "inputs": list(state.get("input_records", [])),
        "georeferenced": state.get("georeferenced"),
        "resolutionMetres": state.get("resolution_metres"),
        "obscuredFraction": state.get("obscured_fraction"),
    }
    if state.get("index"):
        parameters.update({
            "index": state["index"], "targetLower": state.get("target_lower"), "targetUpper": state.get("target_upper"),
            "targetLabel": state.get("target_label"), "targetPhrase": state.get("target_phrase"), "indexEngineVersion": INDEX_ENGINE_VERSION,
            "eviCoefficients": {"gain": EVI_GAIN, "red": EVI_RED_COEFFICIENT, "blue": EVI_BLUE_COEFFICIENT, "canopyBackground": EVI_CANOPY_BACKGROUND},
            "saviSoilBrightness": SAVI_SOIL_BRIGHTNESS, "maskApplied": state.get("index_mask_applied", False),
            "unphysicalFraction": state.get("index_unphysical_fraction"),
        })
    if "detections" in state:
        parameters.update({
            "objects": list(state.get("objects", [])), "wantsLocation": bool(state.get("wants_location")),
            "detectionScoreThreshold": state.get("detection_score_threshold"), "detectionCounts": dict(state.get("detection_counts", {})),
            "detectionsBelowResolution": dict(state.get("detections_below_resolution", {})),
            "frameObservedFraction": state.get("frame_observed_fraction"),
        })
    if "class_map_path" in state:
        parameters.update({
            "classes": list(state.get("classes", [])), "classNames": list(state.get("class_names", [])),
            "classFractions": dict(state.get("class_fractions", {})), "classMeanConfidence": dict(state.get("class_mean_confidence", {})),
        })
    if "registration" in state:
        parameters["registration"] = dict(state["registration"])
    if "change_threshold" in state:
        parameters.update({
            "changeThreshold": state.get("change_threshold"), "changedFraction": state.get("changed_fraction"),
            "changeModel": state.get("change_model_id"), "changeModelVersion": state.get("change_model_version"),
            "referenceObscuredFraction": state.get("reference_obscured_fraction"),
        })
    return parameters


def _figure_ids(state: AnalysisState) -> list[str]:
    """Every figure the run drew, in order, each once; the index path's three keys first for old records."""
    ordered: list[str] = []
    for figure_id in (
        state.get("index_figure_id"), state.get("composite_figure_id"), state.get("mask_figure_id"), *state.get("figure_ids", []),
    ):
        if figure_id and figure_id not in ordered:
            ordered.append(figure_id)
    return ordered


def _artefacts(state: AnalysisState) -> list[ArtefactRecord]:
    """Every retained intermediate, with the layer that draws it where the stage emitted one."""
    records = []
    for stage, path_key, object_key, uri_key, layer_key in (
        (PipelineStage.S7, "cloud_mask_path", "cloud_mask_object_key", "cloud_mask_storage_uri", None),
        (PipelineStage.S12, "index_path", "index_object_key", "index_storage_uri", "index_layer_id"),
        (PipelineStage.S13, "detections_path", "detections_object_key", "detections_storage_uri", None),
        (PipelineStage.S13, "class_map_path", "class_map_object_key", "class_map_storage_uri", None),
        (PipelineStage.S13, "class_confidence_path", "class_confidence_object_key", "class_confidence_storage_uri", "class_confidence_layer_id"),
        (PipelineStage.S13, "change_probability_path", "change_probability_object_key", "change_probability_storage_uri", "change_layer_id"),
        (PipelineStage.S13, "change_mask_path", "change_mask_object_key", "change_mask_storage_uri", None),
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
    # What a stage retained beyond the named keys (a mask per land-cover class), already in wire form.
    records.extend(ArtefactRecord.model_validate(item) for item in state.get("artefact_records", []))
    return records
