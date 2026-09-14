"""The one place a language model is constructed: `init_chat_model` with the provider and model from config.

what  : `build_chat_model()`, `chat_model_record()`, `probe_chat_model()` for `aeris doctor`.
where : `agents/` (arbitration, plan prose, synthesis) and `services/answer/constrained.py` when the LLM
        phrases. Nothing else imports a provider package.
how  : ADR-002 cancelled the `LLMProvider` protocol: LangChain's `init_chat_model` *is* the provider
    abstraction, so a second provider is `LLM_PROVIDER` and `LLM_MODEL` in `.env`; every provider
    receives the single application-owned `LLM_API_KEY`. The one
        provider-specific line is `reasoning_effort`, an OpenAI reasoning-model parameter that replaces
        temperature; it is passed to that provider only and documented here rather than hidden.

        `LLM_PROVIDER=none` returns `None`, and every caller has a template path for it: the router,
        the plan and the answer all work without a model, which is what the pipeline tests run.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from app.config import settings
from app.lib.exceptions import UpstreamUnavailableError

logger = logging.getLogger(__name__)

# The version string the provenance record carries for anything the LLM phrased.
LLM_VERSION_PREFIX = "llm"


@dataclass(frozen=True, slots=True)
class ChatModelRecord:
    provider: str
    model: str

    @property
    def version(self) -> str:
        return f"{LLM_VERSION_PREFIX}:{self.provider}:{self.model}"


def chat_model_record() -> ChatModelRecord | None:
    if settings.llm_provider == "none":
        return None
    return ChatModelRecord(settings.llm_provider, settings.llm_model)


def build_chat_model():  # noqa: ANN201 - the return type is LangChain's BaseChatModel; kept untyped so importing this module costs nothing
    """The configured chat model, or `None` when no provider is configured."""
    if settings.llm_provider == "none":
        return None
    from langchain.chat_models import init_chat_model

    extra: dict[str, object] = {}
    if settings.llm_api_key is not None:
        extra["api_key"] = settings.llm_api_key.get_secret_value()
    if settings.llm_provider == "openai" and settings.llm_reasoning_effort:
        extra["reasoning_effort"] = settings.llm_reasoning_effort
    return init_chat_model(settings.llm_model, model_provider=settings.llm_provider, timeout=settings.llm_timeout_seconds, **extra)


@dataclass(frozen=True, slots=True)
class ChatModelHealth:
    configured: bool
    reachable: bool
    version: str | None
    latency_ms: int | None
    detail: str


async def probe_chat_model() -> ChatModelHealth:
    """One short round trip, for `aeris doctor`: the key works, the model exists, and how long it takes."""
    record = chat_model_record()
    if record is None:
        return ChatModelHealth(False, False, None, None, "LLM_PROVIDER=none: the agent runs without a model")
    model = build_chat_model()
    started = time.perf_counter()
    try:
        reply = await asyncio.wait_for(model.ainvoke("Reply with the single word: ready"), timeout=settings.llm_timeout_seconds)
    except Exception as error:  # noqa: BLE001 - a doctor row reports whatever the provider raised
        return ChatModelHealth(True, False, record.version, None, f"{type(error).__name__}: {error}")
    latency_ms = round((time.perf_counter() - started) * 1000)
    text = reply.content if isinstance(reply.content, str) else str(reply.content)
    return ChatModelHealth(True, True, record.version, latency_ms, f"replied {text.strip()[:40]!r}")


async def require_chat_model():  # noqa: ANN201
    """The model, or the error a caller that cannot fall back should raise."""
    model = build_chat_model()
    if model is None:
        raise UpstreamUnavailableError("No language model is configured (LLM_PROVIDER=none).", details={"upstream": "llm"})
    return model
