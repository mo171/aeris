"""LangSmith tracing, switched on from config - the one place this process writes to its own environment.

what  : `enable_tracing_if_configured()`.
where : `agents/run.py` before the graph is compiled; idempotent, so any later caller is harmless.
how   : LangChain and LangGraph read `LANGSMITH_TRACING`, `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT`
        from `os.environ` themselves - there is no client to pass a key to. `config.py` reads `.env`
        without exporting it (`code-standards.md` §5), so the values are copied across here, from the
        typed settings, and nowhere else. Off by default: tracing sends every prompt and answer to a
        third party, which is the operator's decision to make per deployment, not this file's.
"""

import logging
import os

from app.config import settings

logger = logging.getLogger(__name__)


def enable_tracing_if_configured() -> bool:
    if not settings.langsmith_tracing or settings.langsmith_api_key is None:
        return False
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.get_secret_value()
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    logger.info("langsmith tracing enabled", extra={"project": settings.langsmith_project})
    return True
