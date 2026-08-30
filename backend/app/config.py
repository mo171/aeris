"""Every value that changes between one machine and the next, declared once and validated at import.

what  : A `pydantic-settings` model, `Settings`, plus the module-level `settings` instance the rest of the
        application imports. Reads `backend/.env`, then the real process environment, which wins.
where : Imported by everything. This module is the only place in the backend permitted to touch
        `os.environ` - code-standards.md §5. A module that reads the environment directly is a bug, because
        it cannot be validated, cannot be documented in `.env.example`, and cannot be reported by
        `aeris doctor`.
how   : Instantiating `Settings()` at the bottom of this file means a missing or malformed variable raises
        `pydantic.ValidationError` at import time, naming the field, before any route is mounted or any
        pipeline stage runs. Failing at import is the point: a half-configured process that starts and then
        fails on stage S13 forty seconds into a run is far more expensive to diagnose.

        Secrets are `SecretStr`, so they are masked in `repr()`, in logs, and in `aeris doctor` output
        without every call site having to remember to mask them.

        This file grows one field at a time, added by the sub-phase that first reads it. Fields for
        infrastructure that does not exist yet (a database URL, bucket names, a model registry path) are
        deliberately absent - an unread setting is a claim about the system that nothing verifies.
"""

from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The repository's `backend/` directory - this file is `backend/app/config.py`. Resolved from `__file__`
# rather than from the working directory, so `uv run pytest`, `uvicorn` and the CLI all find the same `.env`
# no matter where they are launched from.
BACKEND_ROOT_DIRECTORY: Path = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """The validated configuration of one running backend process."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT_DIRECTORY / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # `ignore` rather than `forbid`: infrastructure is provisioned in Phase 0.2-0.5, and a `.env` will
        # legitimately carry a variable for a sub-phase before this model reads it. `forbid` would turn
        # "provisioned Postgres today, wiring it up tomorrow" into a crash on an unrelated import.
        extra="ignore",
    )

    # --- Identity. Reported by `aeris doctor` and stamped into every run journal and report. ------------

    project_name: str = "SatQuery AI (AERIS)"
    version: str = "1.0.0"

    # --- Deployment shape --------------------------------------------------------------------------------

    # Drives decisions that must not be made by inspecting `debug`: which log format to emit, whether
    # tracebacks reach the client, and whether a destructive CLI command needs confirmation.
    environment: Literal["local", "development", "staging", "production"] = "local"

    # Verbose diagnostics only. Never a gate on anything that affects correctness or safety.
    debug: bool = False

    # --- Logging. Consumed by `app/lib/logger.py`. -------------------------------------------------------

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # `json` in every deployed environment, because a run is diagnosed by filtering on `run_id` rather than
    # by reading. `console` exists for a human watching a local terminal.
    log_format: Literal["json", "console"] = "json"

    # --- Inngest. Required, and required with no default, on purpose. ------------------------------------
    #
    # These are the first two secrets the backend holds, and they demonstrate the Phase 0.1 gate: a clone
    # with an incomplete `.env` must fail at import with the variable's name in the message, not start up
    # and fail later when a run tries to enqueue. Local development uses the literal value `local`, which
    # `.env.example` documents - a documented value is not the same thing as a silent default.

    inngest_event_key: SecretStr
    inngest_signing_key: SecretStr

    @field_validator("log_level", mode="before")
    @classmethod
    def normalise_log_level(cls, raw_value: object) -> object:
        """Accept `info` and `Info` as well as `INFO`, since the value is typed by hand in a `.env`."""
        if isinstance(raw_value, str):
            return raw_value.strip().upper()
        return raw_value

    @property
    def is_production(self) -> bool:
        """True when a mistake is visible to an operator rather than to the developer who made it."""
        return self.environment == "production"


# Instantiated at import so that configuration is validated exactly once, as early as possible. Nothing
# imports `Settings`; everything imports `settings`.
settings: Settings = Settings()
