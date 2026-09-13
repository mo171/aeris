"""S14 - the VLM reads the evidence figure the operator is shown, or answers the operator's question about the picture, labelled as its own.

what  : `read_figure`, the S14 node of every 1.10 graph, and `answer_question_node`, the S14 node of the
        SCENE_VQA and CHANGE_VQA branches.
where : `read_figure` runs after S15 in the measurement branches; `answer_question_node` is the whole
        specialist stage of a perception question (S1 -> (S7) -> S14 -> S16 -> S18 -> S19).
how   : **A reading is never a measurement, and the two nodes keep the two apart.**

        `read_figure` reads the figure the run stands behind (`primary_figure_id`, set by whichever S15
        ran) - fetched back from storage by its id, exactly the bytes the frontend draws
        (`product-truth.md` §1.5) - and says where the highlighted regions or boxes lie and what surrounds
        them (`FIGURE_READING_TEMPLATE`). The reading, the prompt and the model version go into the state
        and a `ModelRecord` into `stage_models` with `confidence=None` - a token probability is the
        model's certainty in its wording, not a confidence in a claim, so S18 does not aggregate it. It
        never fails a run: no figure, no weights, or a model refusal is a skipped reading with the reason
        in the trace step, and S16 speaks from the claims alone.

        `answer_question_node` is the perception branch: the operator asked what the picture shows, the
        frame is rendered as the figure the model was shown, and the model's words become a *categorical
        claim with no metric*, its text labelled as the model's reading, resting on an evidence record of
        the picture (`EvidenceKind.SCENE_CROP`). A two-date question (CHANGE_VQA) is asked over both
        frames in one conversation. The claim's confidence is `None` for the same reason as above; the
        wording certainty is on the record, not on the claim.
"""

import asyncio
import logging
from io import BytesIO

import numpy as np
from PIL import Image

from app.config import settings
from app.constants.evidence import ClaimKind, EvidenceKind
from app.constants.intents import Intent
from app.constants.model_ids import ModelId
from app.constants.scenes import SceneModality
from app.constants.stages import PipelineStage
from app.constants.storage import Bucket
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.lib import storage
from app.lib.exceptions import AerisError
from app.schemas.events import Claim, ClaimEvent, EvidenceItem
from app.services.evidence.trace import ModelRecord
from app.services.pipeline.inputs import primary_frame, reference_frame
from app.services.pipeline.node import current_trace_step_id, describe_trace_step, pipeline_node
from app.services.pipeline.state import AnalysisState
from app.services.pipeline.stream import emit
from app.services.prompts.vlm import SAR_IMAGE_NOTE
from app.services.rendering.figures import figure_object_key, render_frame
from app.services.rendering.math.rasterize import ImageFormat
from app.services.vlm.reading import answer_question, read_labelled_figure, read_pair

logger = logging.getLogger(__name__)

SKIPPED: dict[str, object] = {"reading_text": None, "reading_prompt": None, "reading_figure_id": None, "reading_confidence": None}


@pipeline_node(PipelineStage.S14, detail="Reading the evidence figure with the vision-language model", model_id=ModelId.REMOTE_SENSING_VLM)
async def read_figure(state: AnalysisState) -> dict[str, object]:
    """S14 after a measurement. The model's reading of the figure, or a stated reason there is none."""
    if not settings.vlm_reading:
        describe_trace_step("skipped: VLM_READING is off")
        return dict(SKIPPED)
    figure_id = state.get("primary_figure_id") or state.get("mask_figure_id") or state.get("composite_figure_id")
    if figure_id is None:
        describe_trace_step("skipped: no figure was rendered for this run")
        return dict(SKIPPED)
    if state.get("detection_figure_id") and not any((state.get("detection_counts") or {}).values()):
        describe_trace_step("skipped: the detector drew nothing, so there is nothing on the figure to read")
        return dict(SKIPPED)

    try:
        payload = await storage.get_object(Bucket.FIGURES, figure_object_key(state["run_id"], figure_id, ImageFormat.WEBP.value))
        picture = await asyncio.to_thread(_decode, payload)
        from app.models.manager import get_manager

        manager = await get_manager()
        label = _figure_label(state)
        if label:
            reading = await read_labelled_figure(picture, label.lower(), manager=manager)
        else:
            reading = await answer_question(picture, state["query"], manager=manager)
    except AerisError as error:
        describe_trace_step(f"skipped: {error}")
        return dict(SKIPPED)
    except Exception as error:  # noqa: BLE001 - a reading is optional; the run and its claims are not
        logger.exception("vlm reading failed; the run continues without it")
        describe_trace_step(f"skipped: {type(error).__name__}")
        return dict(SKIPPED)

    describe_trace_step(
        f"{reading.model_version} read figure {figure_id[:12]}... in {reading.latency_ms} ms"
        + (" (cached)" if reading.cached else "") + f"; wording certainty {reading.confidence:.2f}"
    )
    record = ModelRecord(stage=PipelineStage.S14, model_id=reading.model_id.value, model_version=reading.model_version, confidence=None)
    return {
        "reading_text": reading.text, "reading_prompt": reading.prompt, "reading_figure_id": figure_id,
        "reading_confidence": reading.confidence, "stage_models": [record.to_wire()],
    }


def _figure_label(state: AnalysisState) -> str | None:
    """What the highlighted regions on the primary figure are, for the reading prompt."""
    if state.get("target_label") and state.get("mask_figure_id"):
        return str(state["target_label"])
    if state.get("detection_figure_id"):
        # What is *drawn*, not what was asked for: a label for a class the detector did not find would
        # invite the model to describe boxes that are not there (measured: "the tennis courts are in the
        # top-middle" over a figure with none).
        drawn = [name for name, count in (state.get("detection_counts") or {}).items() if count]
        return ", ".join(sorted(drawn)) if drawn else None
    if state.get("comparison_figure_id"):
        return "change"
    if state.get("classes") or state.get("class_map_path"):
        classes = state.get("classes") or []
        return ", ".join(classes).lower() if classes else "land cover"
    return None


@pipeline_node(PipelineStage.S14, detail="Asking the vision-language model the operator's question", model_id=ModelId.REMOTE_SENSING_VLM)
async def answer_question_node(state: AnalysisState) -> dict[str, object]:
    """S14 as the specialist. The picture(s) as shown, the question, the model's words as a labelled claim."""
    from app.models.manager import get_manager

    run_id = state["run_id"]
    step_id = current_trace_step_id()
    intent = Intent(state["intent"])
    frames = [await primary_frame(state)]
    if intent is Intent.CHANGE_VQA and state.get("reference_directory"):
        frames.insert(0, await reference_frame(state))

    figure_ids: list[str] = []
    for frame in frames:
        shown = await render_frame(
            frame.rgb, frame.observed, run_id=run_id, trace_step_id=step_id, title=f"As shown to the model - {frame.source.scene_id}",
            stretch=frame.stretch.value, bands=list(frame.band_ids), scene_ids=[frame.source.scene_id], crs=frame.source.crs,
            caption="The picture the vision-language model was asked about.", is_primary=frame is frames[-1],
        )
        emit(shown.event)
        figure_ids.append(shown.event.figure_id)

    question = state["query"].strip()
    question = question if question.endswith("?") else f"{question}?"
    manager = await get_manager()
    sar = [frame.source.modality is SceneModality.SAR for frame in frames]
    if len(frames) == 2:
        notes = (SAR_IMAGE_NOTE if sar[0] else None, SAR_IMAGE_NOTE if sar[1] else None)
        reading = await read_pair(frames[0].rgb, frames[1].rgb, question, manager=manager, notes=notes)
    else:
        reading = await answer_question(frames[0].rgb, question, manager=manager, is_sar=sar[0])

    evidence = EvidenceItem(
        id=new_identifier(IdentifierPrefix.EVIDENCE), kind=EvidenceKind.SCENE_CROP,
        title="The picture the model read" if len(frames) == 1 else "The two pictures the model read", layer_id=None, feature_ids=[],
        area_hectares=None, magnitude=1.0, confidence=None, source_scene_ids=[frame.source.scene_id for frame in frames],
    )
    claim = Claim(
        id=new_identifier(IdentifierPrefix.CLAIM), run_id=run_id,
        text=f"Asked \"{question}\", the vision-language model's reading (not a measurement) is: {reading.text.strip().rstrip('.')}.",
        kind=ClaimKind.CATEGORICAL, confidence=None, metrics=[], evidence_ids=[evidence.id], model_id=reading.model_id,
        model_version=reading.model_version, trace_step_id=step_id, is_primary=True,
    )
    emit(ClaimEvent(run_id=run_id, claim=claim))
    describe_trace_step(
        f"{reading.model_version} answered over {len(frames)} picture{'s' if len(frames) > 1 else ''} in {reading.latency_ms} ms"
        + (" (cached)" if reading.cached else "") + f"; wording certainty {reading.confidence:.2f}"
    )
    record = ModelRecord(stage=PipelineStage.S14, model_id=reading.model_id.value, model_version=reading.model_version, confidence=None)
    return {
        "reading_text": reading.text, "reading_prompt": reading.prompt, "reading_figure_id": figure_ids[-1], "reading_confidence": reading.confidence,
        "reading_spoken": True, "primary_figure_id": figure_ids[-1], "frame_figure_id": figure_ids[-1], "figure_ids": figure_ids,
        "evidence_items": [evidence.to_wire()], "claims": [claim.to_wire()], "stage_models": [record.to_wire()],
        "input_files": [item for frame in frames for item in await frame.input_records()],
    }


def _decode(payload: bytes) -> np.ndarray:
    return np.asarray(Image.open(BytesIO(payload)).convert("RGB"))
