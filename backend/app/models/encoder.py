"""The sentence encoder behind intent classification: short English in, one unit vector out, on the CPU.

what  : `SentenceEncoder` with `encode(texts) -> (n, 384) float32`, and `load_encoder()`.
where : `services/query/bank.py` embeds the labelled bank once; `services/query/classifier.py` embeds each
        question. Not in the fleet (`constants/routing.py` says why): a 33M-parameter encoder on the CPU
        holds no device budget and appears in no claim, so it is a cached process singleton rather than a
        `ModelManager` lease.
how   : BGE's published recipe: CLS-token pooling, L2-normalised. (MiniLM-style models mean-pool instead;
        the two are not interchangeable, and using the wrong pooling silently costs accuracy rather than
        raising.) Weights are fetched through `loader.fetch_repository` at the pinned commit, safetensors
        only - the repository also ships the same weights as `.bin` and ONNX, which would triple the
        download for nothing. torch is imported inside the functions that need it, as everywhere in
        `app/models/`.
"""

import asyncio
import logging

import numpy as np

from app.constants.routing import INTENT_ENCODER, INTENT_ENCODER_MAX_TOKENS, INTENT_ENCODER_VERSION
from app.models.loader import fetch_repository

logger = logging.getLogger(__name__)

_ENCODER_FILES = ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "vocab.txt")


class SentenceEncoder:
    version = INTENT_ENCODER_VERSION

    def __init__(self, module: object, tokenizer: object) -> None:
        self._module = module
        self._tokenizer = tokenizer

    def encode(self, texts: list[str]) -> np.ndarray:
        """Unit vectors, one row per text, in the order given. Empty input gives a (0, d) array."""
        import torch

        if not texts:
            return np.zeros((0, int(self._module.config.hidden_size)), dtype=np.float32)  # type: ignore[attr-defined]
        batch = self._tokenizer(  # type: ignore[operator]
            texts, padding=True, truncation=True, max_length=INTENT_ENCODER_MAX_TOKENS, return_tensors="pt"
        )
        with torch.inference_mode():
            hidden = self._module(**batch).last_hidden_state  # type: ignore[operator]
        pooled = torch.nn.functional.normalize(hidden[:, 0], dim=-1)
        return pooled.float().cpu().numpy()


_encoder: SentenceEncoder | None = None
_encoder_lock = asyncio.Lock()


async def load_encoder() -> SentenceEncoder:
    """The process's one encoder, built on first use. Raises `UpstreamUnavailableError` with no weights and no network."""
    global _encoder
    async with _encoder_lock:
        if _encoder is None:
            path = await fetch_repository(INTENT_ENCODER, allow_patterns=_ENCODER_FILES)
            _encoder = await asyncio.to_thread(_build, str(path))
            logger.info("intent encoder loaded", extra={"version": INTENT_ENCODER_VERSION})
        return _encoder


def _build(path: str) -> SentenceEncoder:
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(path)
    module = AutoModel.from_pretrained(path).eval()
    return SentenceEncoder(module, tokenizer)
