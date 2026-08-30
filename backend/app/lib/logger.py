"""Configures logging once per process, so that a run can be reconstructed by filtering on `run_id`.

what  : `configure_logging()`, and nothing else. There is no `get_logger` helper here: every module calls
        `logging.getLogger(__name__)` from the standard library.
where : Called exactly once at each entry point - `cli/main.py` before the first command runs, and the FastAPI
        lifespan in Phase 2 - before anything else logs.
how   : `LOG_FORMAT=json` emits one JSON object per line through `python-json-logger`, with anything passed as
        `extra=` merged in. That is the whole point: `logger.info("stage complete", extra={"run_id": run_id,
        "stage": "S13"})` is greppable months later, and a formatted English sentence is not.

        `LOG_FORMAT=console` hands the same records to rich, which is strictly better than a hand-rolled
        colour scheme, and which is why there is no colour code in this file. Note the trade: rich prints the
        message, **not** the `extra=` fields, so `json` is the diagnostic format and `console` is the readable
        one. That is acceptable because in Phase 1 the human surface is the CLI's rich trace of S1-S20, not the
        log; anyone debugging a run switches to `json` and filters on `run_id`.

        Why no `get_logger` wrapper: `logging.getLogger(__name__)` already gives per-module loggers, hierarchy
        and configurability. A wrapper around it would add an import and a name to learn, and would take the
        module name from the wrong frame the first time someone called it from a decorator. Do not build what
        the standard library already does.

        Why `async def` for work that never awaits: code-standards.md §7 makes every function above `math/` a
        coroutine, so no call site has to remember which entry points are awaited. The cost is one `await`;
        the benefit is that adding an awaited handler here later is not a signature change that ripples out.
"""

import logging
import sys
from typing import Final

from app.config import settings
from app.constants.logs import (
    CONSOLE_LOG_FORMAT,
    JSON_FIELD_RENAMES,
    JSON_LOG_FORMAT,
    THIRD_PARTY_LOG_LEVELS,
)

_ROOT_LOGGER_NAME: Final[str] = "aeris"

# Guards against a second entry point reconfiguring the root logger and producing every line twice.
_logging_is_configured: bool = False


async def configure_logging() -> None:
    """Install the process-wide log handler. Safe to call more than once; the second call does nothing."""
    global _logging_is_configured
    if _logging_is_configured:
        return

    handler = await _build_handler()

    root_logger = logging.getLogger()
    # Replace rather than append. uvicorn and Jupyter both install their own handler, and leaving it in place
    # is how one log line becomes three.
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level)

    for logger_name, level in THIRD_PARTY_LOG_LEVELS.items():
        logging.getLogger(logger_name).setLevel(level)

    _logging_is_configured = True

    logging.getLogger(_ROOT_LOGGER_NAME).info(
        "logging configured",
        extra={
            "project_name": settings.project_name,
            "version": settings.version,
            "environment": settings.environment,
            "log_level": settings.log_level,
            "log_format": settings.log_format,
        },
    )


async def _build_handler() -> logging.Handler:
    """One handler on stdout, formatted according to `LOG_FORMAT`."""
    if settings.log_format == "console":
        from rich.logging import RichHandler

        # Imported here rather than at module scope so that a deployed process running `json` never loads
        # rich's console machinery, and so this module stays importable if rich is ever dropped to a dev
        # dependency.
        console_handler = RichHandler(rich_tracebacks=True, show_path=settings.debug)
        console_handler.setFormatter(logging.Formatter(CONSOLE_LOG_FORMAT))
        return console_handler

    from pythonjsonlogger.json import JsonFormatter

    json_handler = logging.StreamHandler(sys.stdout)
    json_handler.setFormatter(
        JsonFormatter(
            fmt=JSON_LOG_FORMAT,
            rename_fields=JSON_FIELD_RENAMES,
            # An ISO-8601 `timestamp` field. The standard library's `asctime` is local time with no offset,
            # which is unusable for correlating a run against a satellite acquisition time.
            timestamp=True,
        )
    )
    return json_handler
