"""Serves the remote-sensing VLM: Qwen3-VL at the configured size, 4-bit on the card, with the LoRA adapter that makes it ours.

what  : `VlmAdapter` - `generate()` for one or more images and a prompt, returning the text and the mean
        token probability - `vlm_record()` (the fleet record the configuration resolves to) and
        `load_vlm()`, the loader the manager calls.
where : Leased from `app/models/manager.py` by `services/vlm/` (VQA, captioning) and by
        `services/answer/constrained.py` (S16). The training notebooks produce the adapter it attaches.
how   : Qwen3-VL-Instruct through `transformers`, NF4-quantised with bitsandbytes on CUDA (a 2B model in
        bf16 is 4 GB of weights and would be the whole card), bf16 on a CPU as `degraded`. The adapter is
        a PEFT LoRA fetched from the Hub like any other checkpoint; without one the model is served
        unadapted and its version says so - a judge reading `aeris models status` sees `-unadapted`.

        Every image is resized to `VLM_IMAGE_PIXELS` on its longer side *here*, not by the processor's
        defaults, so the visual token count is the same at inference as in training and on a 4 GB card.
        Decoding is greedy. Confidence is the geometric-mean probability of the generated tokens, which is
        the model's certainty in its own wording and not the truth of it; the service that states it
        names it as such.
"""

import asyncio
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.config import settings
from app.constants.fleet import FLEET, FleetRecord, WeightsSource
from app.constants.model_ids import ModelId
from app.constants.vlm import UNADAPTED_SUFFIX, VLM_IMAGE_PIXELS, VLM_MAX_NEW_TOKENS, VLM_VARIANTS, VlmSize
from app.models.loader import fetch_repository
from app.services.prompts.vlm import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Generation:
    """What the model wrote, and how sure it was of each word on average."""

    text: str
    mean_token_probability: float
    generated_tokens: int


class VlmAdapter:
    """One resident VLM on one device."""

    def __init__(self, module: object, processor: object, device: str, version: str) -> None:
        self._module = module
        self._processor = processor
        self.device = device
        self.version = version

    def generate(
        self,
        images: list[np.ndarray],
        prompt: str,
        *,
        image_notes: list[str | None] | None = None,
        max_new_tokens: int = VLM_MAX_NEW_TOKENS,
    ) -> Generation:
        """Greedy generation for a conversation of `images` (each optionally introduced by a note) and `prompt`."""
        import torch

        notes = image_notes or [None] * len(images)
        content: list[dict[str, object]] = []
        for image, note in zip(images, notes, strict=True):
            if note:
                content.append({"type": "text", "text": note})
            content.append({"type": "image", "image": fit_image(image)})
        content.append({"type": "text", "text": prompt})
        messages = [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {"role": "user", "content": content},
        ]
        inputs = self._processor.apply_chat_template(  # type: ignore[attr-defined]
            messages, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt"
        ).to(self._module.device)  # type: ignore[attr-defined]
        with torch.inference_mode():
            output = self._module.generate(  # type: ignore[attr-defined]
                **inputs, max_new_tokens=max_new_tokens, do_sample=False,
                output_scores=True, return_dict_in_generate=True,
            )
        prompt_length = inputs["input_ids"].shape[1]
        generated = output.sequences[0, prompt_length:]
        text = self._processor.batch_decode(  # type: ignore[attr-defined]
            generated[None], skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0].strip()
        log_probabilities = self._module.compute_transition_scores(  # type: ignore[attr-defined]
            output.sequences, output.scores, normalize_logits=True
        )[0, : len(generated)]
        kept = log_probabilities[torch.isfinite(log_probabilities)]
        mean_probability = float(math.exp(kept.mean().item())) if len(kept) else 0.0
        return Generation(text=text, mean_token_probability=mean_probability, generated_tokens=int(len(generated)))


def fit_image(image: np.ndarray | Image.Image) -> Image.Image:
    """RGB, longer side at `VLM_IMAGE_PIXELS`. Small patches are upscaled (bicubic); big ones downscaled (area)."""
    picture = image if isinstance(image, Image.Image) else Image.fromarray(np.nan_to_num(image).clip(0, 255).astype(np.uint8))
    picture = picture.convert("RGB")
    longer = max(picture.size)
    if longer == VLM_IMAGE_PIXELS:
        return picture
    scale = VLM_IMAGE_PIXELS / longer
    size = (max(1, round(picture.width * scale)), max(1, round(picture.height * scale)))
    return picture.resize(size, Image.Resampling.BICUBIC if scale > 1 else Image.Resampling.BOX)


def vlm_record() -> FleetRecord:
    """The fleet record for the configured variant and adapter - what the manager admits and reports."""
    variant = VLM_VARIANTS[VlmSize(settings.vlm_size)]
    base = FLEET[ModelId.REMOTE_SENSING_VLM]
    adapted = settings.vlm_adapter_repository is not None
    version = variant.version + ("" if adapted else UNADAPTED_SUFFIX)
    if adapted:
        version += "+" + settings.vlm_adapter_repository.rsplit("/", 1)[-1]  # type: ignore[union-attr]
    return base._replace(
        version=version,
        weights=WeightsSource(variant.repository, None, variant.revision),
        vram_megabytes=variant.vram_megabytes,
    )


async def load_vlm(device: str) -> VlmAdapter:
    """Fetch the base (and the adapter, if configured), build on the device, attach the adapter."""
    record = vlm_record()
    assert record.weights is not None
    base = await fetch_repository(record.weights)
    adapter: Path | None = None
    if settings.vlm_adapter_repository is not None:
        adapter = await fetch_repository(WeightsSource(settings.vlm_adapter_repository, None, settings.vlm_adapter_revision))
    module, processor = await asyncio.to_thread(_build, base, adapter, device)
    return VlmAdapter(module, processor, device, record.version)


def _build(base: Path, adapter: Path | None, device: str) -> tuple[object, object]:
    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    quantise = settings.vlm_quantise and device.startswith("cuda")
    if quantise:
        from transformers import BitsAndBytesConfig

        quantisation = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True
        )
        module = Qwen3VLForConditionalGeneration.from_pretrained(
            base, dtype=torch.bfloat16, quantization_config=quantisation, device_map={"": torch.device(device)}
        )
    else:
        module = Qwen3VLForConditionalGeneration.from_pretrained(base, dtype=torch.bfloat16 if device.startswith("cuda") else torch.float32)
        module.to(torch.device(device))
    if adapter is not None:
        from peft import PeftModel

        module = PeftModel.from_pretrained(module, adapter)
    module.eval()
    processor = AutoProcessor.from_pretrained(base)
    logger.info(
        "vlm built",
        extra={"base": str(base), "adapter": str(adapter) if adapter else None, "device": device, "quantised": quantise},
    )
    return module, processor
