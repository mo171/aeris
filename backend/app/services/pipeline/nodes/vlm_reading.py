"""S14 - the VLM reads the evidence figure the operator is shown, and says what it sees, labelled as its own.

what  : `read_figure`, the S14 node of the index-query graph.
where : After S15 in `graphs/index_query.py`, before S16. 1.10's single-image and pair graphs reuse it
        over their own figures.
how   : The picture is the figure S15 rendered and stored - fetched back from storage by its id, exactly
        the bytes the frontend draws (`product-truth.md` §1.5: the VLM reads the same image the operator
        sees, which is why renders are deterministic and carry a `renderSpec`). The model is asked the
        operator's question over the overlay figure when there is one, the true-colour composite
        otherwise. Over the overlay it is asked where the highlighted regions lie and what surrounds them
        (`FIGURE_READING_TEMPLATE`) - the operator's query is a phrase like "unhealthy vegetation", not a
        question, and asked as one the model just says "yes". The reading, the prompt and the model version go into the state and a `ModelRecord`
        into `stage_models` with `confidence=None` - a token probability is the model's certainty in its
        wording, not a confidence in a claim, so S18 does not aggregate it.

        The node never fails a run: no figure, no weights, or a model refusal is recorded as a skipped
        reading with the reason in the trace step, and S16 speaks from the claims alone.
"""

import asyncio
import logging
from io import BytesIO

import numpy as np
from PIL import Image

from app.config import settings
from app.constants.model_ids import ModelId
from app.constants.stages import PipelineStage
from app.constants.storage import Bucket
from app.lib import storage
from app.lib.exceptions import AerisError
from app.services.evidence.trace import ModelRecord
from app.services.pipeline.node import describe_trace_step, pipeline_node
from app.services.pipeline.state import IndexQueryState
from app.services.rendering.figures import figure_object_key
from app.services.rendering.math.rasterize import ImageFormat
from app.services.vlm.reading import answer_question, read_labelled_figure

logger = logging.getLogger(__name__)


@pipeline_node(PipelineStage.S14, detail="Reading the evidence figure with the vision-language model", model_id=ModelId.REMOTE_SENSING_VLM)
async def read_figure(state: IndexQueryState) -> dict[str, object]:
    """S14. The model's reading of the figure, or a stated reason there is none."""
    skipped: dict[str, object] = {"reading_text": None, "reading_prompt": None, "reading_figure_id": None, "reading_confidence": None}
    if not settings.vlm_reading:
        describe_trace_step("skipped: VLM_READING is off")
        return skipped
    figure_id = state.get("mask_figure_id") or state.get("composite_figure_id")
    if figure_id is None:
        describe_trace_step("skipped: no figure was rendered for this run")
        return skipped

    try:
        payload = await storage.get_object(Bucket.FIGURES, figure_object_key(state["run_id"], figure_id, ImageFormat.WEBP.value))
        picture = await asyncio.to_thread(_decode, payload)
        from app.models.manager import get_manager

        manager = await get_manager()
        label = state.get("target_label")
        if label and state.get("mask_figure_id"):
            reading = await read_labelled_figure(picture, label.lower(), manager=manager)
        else:
            reading = await answer_question(picture, state["query"], manager=manager)
    except AerisError as error:
        describe_trace_step(f"skipped: {error}")
        return skipped
    except Exception as error:  # noqa: BLE001 - a reading is optional; the run and its claims are not
        logger.exception("vlm reading failed; the run continues without it")
        describe_trace_step(f"skipped: {type(error).__name__}")
        return skipped

    describe_trace_step(
        f"{reading.model_version} read figure {figure_id[:12]}... in {reading.latency_ms} ms"
        + (" (cached)" if reading.cached else "") + f"; wording certainty {reading.confidence:.2f}"
    )
    record = ModelRecord(stage=PipelineStage.S14, model_id=reading.model_id.value, model_version=reading.model_version, confidence=None)
    return {
        "reading_text": reading.text, "reading_prompt": reading.prompt, "reading_figure_id": figure_id,
        "reading_confidence": reading.confidence, "stage_models": [record.to_wire()],
    }


def _decode(payload: bytes) -> np.ndarray:
    return np.asarray(Image.open(BytesIO(payload)).convert("RGB"))
