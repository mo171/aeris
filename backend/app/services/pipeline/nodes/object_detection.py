"""S13 and S15 for objects - the detector's boxes over the picture the run was handed, then bound to ground and counted.

what  : `detect_objects_node` (S13) and `localise_detections` (S15) of the single-image graph.
where : The DETECT and GROUND branch: S1 -> (S7) -> S13 -> S15 -> S14 -> S16 -> S18 -> S19. The
        `dota-detector` model id's stage.
how   : **S13 runs the model and keeps what it said; S15 turns that into evidence.** The split is the
        same one S12/S15 make for an index: the model's output is an artefact (the boxes, as JSON,
        retained and addressable) and a figure of what the model *saw* - the frame with cloud and nodata
        transparent - so an operator can judge the count against the picture it was made from. S15 reads
        the boxes back from the state, mints the layer (georeferenced input only), the evidence records
        and the claims through `services/evidence/builder.py`, and draws the overlay with the claims'
        ids on it (`api-contract.md` §6 rule 4). Every number the answer will speak - the count, the mean
        score, the threshold - is on a claim by construction.

        **A count is the number of boxes kept at or above the detector's threshold**, never a model's
        opinion (PDF p.24; 1.7 measured the VLM at 0.23 on counting). The S13 confidence is the mean
        score of the boxes kept: the model's own certainty, stated as such, `None` when it kept nothing.

        Ground the S7 mask hid or the file marks nodata reaches the model as NaN, which the adapter feeds
        as black and refuses to place a box on; the frame's observed share is on every negative claim so
        "none found" is read against how much was searched.

        **The resolution gate is applied to the output as well as the question.** The router refuses a
        count of cars over a 10 m scene before anything runs; the detector, asked for bridges over that
        scene, still emits boxes for planes and storage tanks it cannot possibly have seen at three pixels
        a side. Those boxes are kept in the S13 artefact (they are what the model said) and excluded from
        the claims (they are not what the picture can show), with the exclusion on the trace and in the
        record. Measured on the Mumbai subset: "6 planes" and "2 storage tanks" would otherwise have been
        claimed beside the bridges.
"""

import logging

import numpy as np

from app.constants.detection import DETECTION_CONFIDENCE_THRESHOLD, DOTA_CLASS_NAMES
from app.constants.fleet import FLEET
from app.constants.licences import COPERNICUS_ATTRIBUTION
from app.constants.model_ids import ModelId
from app.constants.stages import PipelineStage
from app.schemas.events import ClaimEvent, LayerReadyEvent
from app.services.detection.detector import detect_objects
from app.services.detection.math.oriented_boxes import OrientedBox
from app.services.evidence.artefacts import store_json_artefact
from app.services.evidence.builder import build_detection_evidence, plural_of
from app.services.evidence.trace import ModelRecord
from app.services.imagery.frames import InputKind
from app.services.pipeline.inputs import primary_frame
from app.services.pipeline.node import attach_artefact_layer, current_trace_step_id, describe_trace_step, pipeline_node
from app.services.pipeline.state import AnalysisState
from app.services.pipeline.stream import emit
from app.services.query.entities import required_ground_sample_distance
from app.services.rendering.figures import render_detection_overlay, render_frame

logger = logging.getLogger(__name__)

DETECTIONS_ARTEFACT_NAME = "detections.json"


@pipeline_node(
    PipelineStage.S13, detail="Detecting objects with the oriented-box detector",
    model_id=ModelId.DOTA_DETECTOR, model_version=FLEET[ModelId.DOTA_DETECTOR].version,
)
async def detect_objects_node(state: AnalysisState) -> dict[str, object]:
    """S13. The frame the model saw, the boxes it kept, both retained."""
    from app.models.manager import get_manager

    run_id = state["run_id"]
    step_id = current_trace_step_id()
    frame = await primary_frame(state)

    shown = await render_frame(
        frame.rgb, frame.observed, run_id=run_id, trace_step_id=step_id, title=f"As shown to the detector - {frame.source.scene_id}",
        stretch=frame.stretch.value, bands=list(frame.band_ids), scene_ids=[frame.source.scene_id], crs=frame.source.crs,
        caption="The picture the detector was given. Cloud, shadow and nodata are transparent: nothing was detected there.",
    )
    emit(shown.event)

    result = await detect_objects(frame.for_model(), manager=await get_manager())
    detections = [
        {"class": result.class_names[box.class_index], "score": round(float(box.confidence), 4), "corners": np.round(box.corners, 1).tolist()}
        for box in result.boxes
    ]
    artefact = await store_json_artefact(
        {"model": result.model_id.value, "version": result.model_version, "scoreThreshold": DETECTION_CONFIDENCE_THRESHOLD,
         "classes": list(result.class_names), "boxes": detections},
        run_id=run_id, stage=PipelineStage.S13, name=DETECTIONS_ARTEFACT_NAME,
    )

    counts: dict[str, int] = {}
    for detection in detections:
        counts[detection["class"]] = counts.get(detection["class"], 0) + 1
    listed = ", ".join(f"{count} {plural_of(name, count)}" for name, count in sorted(counts.items(), key=lambda item: -item[1])) or "nothing"
    describe_trace_step(
        f"{len(result.boxes)} boxes kept at score >= {DETECTION_CONFIDENCE_THRESHOLD:.2f}"
        + (f" (mean {result.confidence:.2f})" if result.confidence is not None else "")
        + f": {listed}; {frame.shape[1]}x{frame.shape[0]}, {frame.observed_fraction:.1%} observed, {result.latency_ms} ms"
    )
    record = ModelRecord(stage=PipelineStage.S13, model_id=result.model_id.value, model_version=result.model_version, confidence=result.confidence)
    return {
        "detections": detections,
        "detections_path": str(artefact.path), "detections_object_key": artefact.object_key, "detections_storage_uri": artefact.storage_uri,
        "detection_counts": counts, "detection_score_threshold": DETECTION_CONFIDENCE_THRESHOLD,
        "frame_observed_fraction": frame.observed_fraction, "frame_figure_id": shown.event.figure_id,
        "figure_ids": [shown.event.figure_id], "stage_models": [record.to_wire()], "input_files": await frame.input_records(),
    }


@pipeline_node(PipelineStage.S15, detail="Binding the detections to ground and counting them", model_id=ModelId.DOTA_DETECTOR, model_version=FLEET[ModelId.DOTA_DETECTOR].version)
async def localise_detections(state: AnalysisState) -> dict[str, object]:
    """S15. Boxes -> features on a layer (when there is ground), evidence per class, a claim per class asked."""
    run_id = state["run_id"]
    step_id = current_trace_step_id()
    class_names = DOTA_CLASS_NAMES
    boxes = [
        OrientedBox(class_names.index(item["class"]), float(item["score"]), np.asarray(item["corners"], dtype=np.float32))
        for item in state.get("detections") or []
    ]
    transform = tuple(state["transform"])
    resolution = state.get("resolution_metres")
    credible = [box for box in boxes if resolution is None or resolution <= required_ground_sample_distance(class_names[box.class_index])]
    below_gate: dict[str, int] = {}
    for box in boxes:
        name = class_names[box.class_index]
        if resolution is not None and resolution > required_ground_sample_distance(name):
            below_gate[name] = below_gate.get(name, 0) + 1
    boxes = credible
    evidence = await build_detection_evidence(
        boxes, class_names, asked=tuple(state.get("objects") or ()), shape=_shape(state), transform=transform,  # type: ignore[arg-type]
        crs=state.get("crs"), resolution_metres=state.get("resolution_metres"), run_id=run_id, trace_step_id=step_id,
        scene_id=state["scene_id"], model_id=ModelId.DOTA_DETECTOR, model_version=FLEET[ModelId.DOTA_DETECTOR].version,
        score_threshold=float(state.get("detection_score_threshold", DETECTION_CONFIDENCE_THRESHOLD)),
        observed_fraction=float(state.get("frame_observed_fraction", 1.0)), wants_location=bool(state.get("wants_location")),
        attribution=COPERNICUS_ATTRIBUTION if state.get("input_kind") == InputKind.SCENE_DIRECTORY.value else None,
    )
    if evidence.layer is not None:
        emit(LayerReadyEvent(run_id=run_id, layer=evidence.layer, evidence=evidence.evidence))
        attach_artefact_layer(evidence.layer.id)
    for claim in evidence.claims:
        emit(ClaimEvent(run_id=run_id, claim=claim))

    # The overlay, drawn now so it carries the claims it illustrates, over the frame S13 showed the model.
    frame = await primary_frame(state)
    shown_rgba = np.dstack([frame.rgb, np.where(frame.observed, 255, 0).astype(np.uint8)])
    overlay = await render_detection_overlay(
        boxes, class_names, shown_rgba, run_id=run_id, trace_step_id=step_id, title=f"Detections - {state['scene_id']}",
        scene_ids=[state["scene_id"]], crs=state.get("crs"), claim_ids=[claim.id for claim in evidence.claims], is_primary=True,
        caption="Every box the detector kept, outlined and labelled by class. The count is the number of boxes.",
    )
    emit(overlay.event)

    asked = ", ".join(f"{evidence.counts.get(name, 0)} {plural_of(name, evidence.counts.get(name, 0))}" for name in state.get("objects") or []) or "every class found"
    describe_trace_step(
        f"{asked}; {len(evidence.claims)} claims"
        + (f", {len(evidence.layer.features)} features on one layer" if evidence.layer else "; no georeference, so no layer")
        + (
            "; not claimed, below the resolution gate at " + f"{resolution:g} m: "
            + ", ".join(f"{count} {plural_of(name, count)}" for name, count in sorted(below_gate.items()))
            if below_gate else ""
        )
    )
    return {
        "detections_below_resolution": below_gate,
        "detection_figure_id": overlay.event.figure_id, "detection_layer_id": evidence.layer.id if evidence.layer else None,
        "primary_figure_id": overlay.event.figure_id, "figure_ids": [overlay.event.figure_id],
        "layers": [evidence.layer.to_wire()] if evidence.layer else [],
        "evidence_items": [item.to_wire() for item in evidence.evidence], "claims": [claim.to_wire() for claim in evidence.claims],
    }


def _shape(state: AnalysisState) -> tuple[int, int]:
    record = (state.get("input_records") or [{}])[-1]
    return (int(record.get("height", 0)), int(record.get("width", 0)))

