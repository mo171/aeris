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

from pydantic import Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

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

    # --- Database. Phase 0.2. -----------------------------------------------------------------------------
    #
    # Postgres with PostGIS. Locally that is the `postgis` service in `docker-compose.yml`; in a deployed
    # environment it is Supabase. Nothing in `app/` distinguishes them - both are the same engine with the
    # same extension, which is why local development uses a real Postgres container rather than SQLite.
    #
    # Required with no default, like the Inngest keys above. A default pointing at localhost would let a
    # deployed process start against a database that is not there and fail later, on the first query, in a
    # worker - which is the failure `config.py` exists to convert into a startup error.
    #
    # The driver must be `postgresql+asyncpg`; `PostgresDsn` accepts the bare `postgresql://` form too, so
    # `require_async_driver` below rejects it rather than letting SQLAlchemy pick the sync driver and block
    # the event loop on every query (code-standards.md §7).

    database_url: PostgresDsn

    # Sized for one developer machine and one API process. asyncpg holds a real connection per pool slot, and
    # Supabase's session-mode pooler counts them, so this is raised deliberately rather than by default.
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=50)

    # Seconds to wait for a connection before failing. Short on purpose: a stalled connect during a run
    # should surface as an error the trace can show, not as a step that appears to hang.
    database_connect_timeout_seconds: int = Field(default=10, ge=1, le=120)

    # Echoes every statement to the logger. Useful when a query is wrong; ruinous in any environment where
    # logs are collected, because it prints parameter values.
    database_echo_sql: bool = False

    @field_validator("database_url")
    @classmethod
    def require_async_driver(cls, value: PostgresDsn) -> PostgresDsn:
        """Reject a DSN that would silently give us the blocking driver."""
        if value.scheme != "postgresql+asyncpg":
            raise ValueError(
                f"DATABASE_URL must use the postgresql+asyncpg driver, got {value.scheme!r}. "
                "Every database call in this backend is awaited (code-standards.md §7); a sync driver "
                "would block the event loop on every query."
            )
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalise_log_level(cls, raw_value: object) -> object:
        """Accept `info` and `Info` as well as `INFO`, since the value is typed by hand in a `.env`."""
        if isinstance(raw_value, str):
            return raw_value.strip().upper()
        return raw_value

    @property
    def database_url_without_password(self) -> str:
        """The DSN with the password replaced, for `aeris doctor` and for logs.

        `SecretStr` cannot be used for the URL itself because SQLAlchemy needs to parse it, so the masking
        happens here instead - once, rather than at each of the places that will eventually print it.

        SQLAlchemy's own renderer does the masking. Hand-rolling it means getting percent-encoded passwords
        and passwordless DSNs right, and getting either wrong prints a credential.
        """
        return make_url(str(self.database_url)).render_as_string(hide_password=True)

    @property
    def is_production(self) -> bool:
        """True when a mistake is visible to an operator rather than to the developer who made it."""
        return self.environment == "production"


# Instantiated at import so that configuration is validated exactly once, as early as possible. Nothing
# imports `Settings`; everything imports `settings`.
settings: Settings = Settings()
