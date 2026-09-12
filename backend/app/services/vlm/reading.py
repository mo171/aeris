"""Asks the VLM about a picture: a question answered, or a scene described - the S14 reading of an image.

what  : `Reading` and `answer_question()`, `describe_image()`; `read_pair()` for two images asked together.
where : S14. `aeris ask` in Phase 1; 1.10's nodes wrap these for the single-image and pair graphs. Leases
        `rs-vlm` from `app/models/manager.py`. The figures of 1.2.1 are what a run passes in, as arrays.
how   : One lease, one generation, one record of which model and version answered and how sure it was of
        its own words. The confidence is the model's mean token probability and is labelled `model-stated`
        - S18 aggregates it like any other stated confidence; it is not accuracy. A SAR image is introduced
        with `SAR_IMAGE_NOTE` so the model is told it is not looking at a photograph.

        A reading is not a claim. It carries no metric and no evidence id; what it says about the picture
        is the model's, and the answer node labels it as such rather than letting it sit beside a measured
        hectare as if it were one.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import numpy as np

from app.constants.model_ids import ModelId
from app.constants.vlm import VLM_MAX_NEW_TOKENS, VLM_MAX_NEW_TOKENS_SHORT
from app.models.manager import ModelManager
from app.services.prompts.vlm import CAPTION_TEMPLATE, SAR_IMAGE_NOTE, VQA_TEMPLATE

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Reading:
    """What the model said about the picture(s), and the record of its saying it."""

    text: str
    prompt: str
    model_id: ModelId
    model_version: str
    # Mean token probability of the generated text: the model's certainty in its wording, stated as such.
    confidence: float
    latency_ms: int
    image_count: int


async def answer_question(
    image: np.ndarray, question: str, *, manager: ModelManager, is_sar: bool = False
) -> Reading:
    """VQA over one image. Short answers; the question is passed as the operator typed it."""
    return await _read([image], VQA_TEMPLATE.format(question=question), manager, [SAR_IMAGE_NOTE if is_sar else None], VLM_MAX_NEW_TOKENS_SHORT)


async def describe_image(image: np.ndarray, *, manager: ModelManager, is_sar: bool = False) -> Reading:
    """A caption: the land cover and major objects, in a few sentences."""
    return await _read([image], CAPTION_TEMPLATE, manager, [SAR_IMAGE_NOTE if is_sar else None], VLM_MAX_NEW_TOKENS)


async def read_pair(
    first: np.ndarray, second: np.ndarray, question: str, *, manager: ModelManager, notes: tuple[str | None, str | None] = (None, None)
) -> Reading:
    """Two images in one conversation - a bi-temporal or an optical/SAR pair - and a question about both."""
    return await _read([first, second], VQA_TEMPLATE.format(question=question), manager, list(notes), VLM_MAX_NEW_TOKENS)


async def _read(
    images: list[np.ndarray], prompt: str, manager: ModelManager, notes: list[str | None], max_new_tokens: int
) -> Reading:
    started = time.perf_counter()
    async with manager.lease(ModelId.REMOTE_SENSING_VLM) as model:
        generation = await asyncio.to_thread(model.generate, images, prompt, image_notes=notes, max_new_tokens=max_new_tokens)
        version = model.version
    latency_ms = round((time.perf_counter() - started) * 1000)
    await manager.record_latency(ModelId.REMOTE_SENSING_VLM, latency_ms)
    logger.info("vlm read", extra={"images": len(images), "latency_ms": latency_ms, "tokens": generation.generated_tokens})
    return Reading(
        text=generation.text, prompt=prompt, model_id=ModelId.REMOTE_SENSING_VLM, model_version=version,
        confidence=generation.mean_token_probability, latency_ms=latency_ms, image_count=len(images),
    )
