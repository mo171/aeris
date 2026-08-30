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

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_core import Url
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

    # --- Inngest endpoints and identity. Phase 0.5. -------------------------------------------------------
    #
    # Passed to the SDK **explicitly**, never left to it. The Inngest client reads `INNGEST_EVENT_KEY`,
    # `INNGEST_SIGNING_KEY`, `INNGEST_DEV` and `INNGEST_BASE_URL` from the process environment when they are
    # not supplied - which would make the environment a second source of configuration that `aeris doctor`
    # cannot report and `.env.example` does not document. code-standards.md §4: this file, or nowhere.

    # Identifies this deployment in the Inngest dashboard and namespaces its functions. Changing it in a
    # deployed environment orphans in-flight runs, which is why it is configuration rather than a constant.
    inngest_app_id: str = "aeris-backend"

    # The Inngest API - function state, replays, the dashboard's own queries. Locally the `inngest` dev
    # server in docker-compose.yml; in production, Inngest Cloud.
    inngest_api_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8288")

    # Where events are POSTed. The same host as the API on the dev server, a different one on Cloud, which
    # is why the SDK takes two and why they are two settings here rather than one.
    inngest_event_api_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8288")

    inngest_request_timeout_seconds: int = Field(default=10, ge=1, le=120)

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

    # --- Redis. Phase 0.3. --------------------------------------------------------------------------------
    #
    # One server, two unrelated uses kept apart by key prefix (`constants/redis_keys.py`): distributed locks
    # around the GPU, and a short-lived cache. Locally that is the `redis` service in docker-compose.yml.
    #
    # Required with no default, for the same reason as `database_url`. There is deliberately no driver
    # validator to match `require_async_driver`: redis-py is a single package exposing both a sync and an
    # async surface from the same `redis://` URL, so there is no wrong-driver form here to reject.

    redis_url: RedisDsn

    # How long a cache entry lives when the call site does not name a TTL. Every cache write has one - see
    # `app/lib/redis.py`. Five minutes is sized against the first things that will be cached (STAC search
    # results, model status): long enough to absorb a burst of identical queries, short enough that a stale
    # answer cannot outlive an operator's attention on it.
    redis_cache_default_ttl_seconds: int = Field(default=300, ge=1, le=86_400)

    # How long a lock is held before Redis expires it. This one number answers two questions that pull in
    # opposite directions: how long a *crashed* holder blocks everyone else, and how long a *live* holder may
    # safely work. No value is right for both. It is sized for the second - loading a quantised model onto an
    # 8 GB card - and a holder needing longer must call `extend()` rather than have this raised, because
    # raising it also lengthens every crash recovery.
    redis_lock_timeout_seconds: float = Field(default=120.0, gt=0, le=3_600)

    # How long an acquirer waits before giving up. Running out raises; it never proceeds unlocked.
    redis_lock_blocking_timeout_seconds: float = Field(default=30.0, ge=0, le=3_600)

    # Short, like the database's. A stalled connect during a run must surface as an error the trace can show
    # rather than as a stage that appears to hang.
    redis_connect_timeout_seconds: int = Field(default=5, ge=1, le=120)

    redis_max_connections: int = Field(default=20, ge=1, le=200)

    # --- Object storage. Phase 0.4. -----------------------------------------------------------------------
    #
    # Written against the **S3 API**, not against MinIO. Locally that is the `minio` service in
    # docker-compose.yml; deployed it is S3, R2 or Supabase Storage with no code change. The one place the
    # difference shows is `storage_addressing_style` below.

    storage_endpoint_url: AnyHttpUrl
    storage_access_key: SecretStr
    storage_secret_key: SecretStr

    # The endpoint a **browser** can reach, which is not always the one this process uses. A presigned URL's
    # signature covers the host, so a URL signed for `http://minio:9000` cannot be repaired by substituting
    # the hostname afterwards - it has to be signed against the public endpoint in the first place. Today the
    # two are the same and this is a no-op; the moment the backend moves into the compose network it is the
    # difference between working upload tickets and a signature error the browser reports as CORS.
    storage_public_endpoint_url: AnyHttpUrl | None = None

    # Signed into every request even though MinIO ignores it: SigV4 has no valid empty region.
    storage_region: str = "us-east-1"

    # Bucket names are `{prefix}-{role}` over the five roles in `constants/storage.py`, so one S3 account can
    # host several deployments. Constrained to what S3 accepts in a bucket name - lower case, digits and
    # hyphens - because the failure otherwise arrives as a signature error rather than a naming one.
    storage_bucket_prefix: str = Field(default="aeris", pattern=r"^[a-z0-9][a-z0-9-]{1,20}[a-z0-9]$")

    # `path` for MinIO, which has no wildcard DNS and cannot serve `bucket.host/key`. Real S3 prefers
    # `virtual`; `auto` lets botocore decide. Wrong here, every request 404s or fails to resolve.
    storage_addressing_style: Literal["path", "virtual", "auto"] = "path"

    # The origin the browser loads the interface from. Read twice: `docker-compose.yml` passes it to MinIO as
    # `MINIO_API_CORS_ALLOW_ORIGIN`, and `app/lib/storage.py` probes with it to prove CORS actually works.
    # Phase 2.0's FastAPI CORS middleware will read the same value, so the answer to "which origin is
    # allowed" is given once.
    storage_browser_origin: AnyHttpUrl = AnyHttpUrl("http://localhost:3000")

    # A download link an operator may sit on before clicking. An hour, not a day: the URL grants access to
    # the object to anyone holding it, and it cannot be revoked before it expires.
    storage_presigned_get_expiry_seconds: int = Field(default=3_600, ge=60, le=604_800)

    # Longer, because this one has to cover the upload itself. A multi-gigabyte scene on a domestic
    # connection takes real time, and an expiry that lapses mid-transfer fails at the end of the upload -
    # the most expensive moment to fail.
    storage_presigned_put_expiry_seconds: int = Field(default=21_600, ge=60, le=604_800)

    storage_connect_timeout_seconds: int = Field(default=10, ge=1, le=120)
    # Generous: this bounds a single read against object storage, and scene reads are large.
    storage_read_timeout_seconds: int = Field(default=60, ge=1, le=600)

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
    def redis_url_without_password(self) -> str:
        """The Redis URL with the password replaced, for `aeris doctor` and for logs.

        Rebuilt from the parsed components rather than by substituting the password out of the string. The
        `.password` Pydantic exposes is the *encoded* form as it appears in the URL, but a hand-rolled
        replacement still has to get a passwordless URL and a password containing `@` or `:` right, and
        getting either wrong prints a credential. `Url.build` is the parser's own inverse.
        """
        url = self.redis_url
        if url.password is None:
            return str(url)
        return str(
            Url.build(
                scheme=url.scheme,
                username=url.username,
                password="***",
                host=url.host or "",
                port=url.port,
                path=(url.path or "").lstrip("/") or None,
            )
        )

    @property
    def storage_endpoint(self) -> str:
        """The endpoint this process talks to, without the trailing slash `AnyHttpUrl` adds.

        `AnyHttpUrl` normalises `http://localhost:9000` to `http://localhost:9000/`, and handing that to
        botocore produces request paths with a doubled slash - which S3 treats as a key beginning with `/`
        and MinIO signs differently from what the client signed. Stripped once, here, rather than at each of
        the three places that pass an endpoint to a client.
        """
        return str(self.storage_endpoint_url).rstrip("/")

    @property
    def storage_signing_endpoint(self) -> str:
        """The endpoint presigned URLs are signed against - the browser-facing one when it differs.

        A single property rather than a branch at each call site, because getting it wrong produces a URL
        that is valid, well-formed, correctly signed, and unreachable from the only place it is ever used.
        """
        return str(self.storage_public_endpoint_url or self.storage_endpoint_url).rstrip("/")

    @property
    def storage_browser_origin_header(self) -> str:
        """The browser origin in the form a browser actually sends it: **no trailing slash.**

        `AnyHttpUrl` stores `http://localhost:3000/`; the `Origin` header is `http://localhost:3000`, and an
        `Access-Control-Allow-Origin` response is compared against it as an exact string. Without this the
        CORS check fails on a deployment whose CORS is configured perfectly, which is a long afternoon.
        """
        return str(self.storage_browser_origin).rstrip("/")

    @property
    def inngest_is_production(self) -> bool:
        """Whether the Inngest SDK should behave as production rather than as a dev-server client.

        Derived from `environment` rather than configured separately. Two independent switches would
        eventually disagree, and the failure mode is a deployed process quietly sending its events to a dev
        server that is not there - or worse, a local run writing into the production event history.
        """
        return self.environment in {"staging", "production"}

    @property
    def is_production(self) -> bool:
        """True when a mistake is visible to an operator rather than to the developer who made it."""
        return self.environment == "production"


# Instantiated at import so that configuration is validated exactly once, as early as possible. Nothing
# imports `Settings`; everything imports `settings`.
settings: Settings = Settings()
