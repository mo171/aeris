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
from typing import Final, Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_core import Url
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

# The repository's `backend/` directory - this file is `backend/app/config.py`. Resolved from `__file__`
# rather than from the working directory, so `uv run pytest`, `uvicorn` and the CLI all find the same `.env`
# no matter where they are launched from.
BACKEND_ROOT_DIRECTORY: Path = Path(__file__).resolve().parent.parent


# Fields whose *value* carries a credential even though the field itself is not a `SecretStr`. A DSN has to
# stay parseable by SQLAlchemy and redis-py, so it cannot be wrapped - the masking happens on the way out
# instead, through the property named here. Read by `aeris doctor` when it prints the configuration in force.
#
# Adding a URL field with credentials in it and forgetting this map is the mistake this exists to make
# survivable: `tests/integration/test_doctor.py` runs the command with distinctive passwords in every
# credential-bearing setting and fails if any of them reaches the output.
MASKED_URL_PROPERTIES: Final[dict[str, str]] = {
    "database_url": "database_url_without_password",
    "redis_url": "redis_url_without_password",
}


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
    inngest_api_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8288")

    # Where events are POSTed. The same host as the API on the dev server, a different one on Cloud, which
    # is why the SDK takes two and why they are two settings here rather than one.
    inngest_event_api_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8288")

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

    # --- The pipeline spine. Phase 1.0. --------------------------------------------------------------------
    #
    # Two SQLite files, deliberately not one. LangGraph's checkpointer and its long-term store each own
    # their own schema, and their lifetimes are opposite: checkpoints are per-run scratch that is safe to
    # delete once a run is finished, while long-term memory is the thing that must never be deleted by
    # accident (`product-truth.md` §1.6). Sharing a file makes "clear the checkpoints" a command that can
    # destroy the operator's memories, and no amount of care at the call site makes that safe again.
    #
    # Relative paths are resolved against `BACKEND_ROOT_DIRECTORY`, not the working directory, so a run
    # started from `backend/` and one started from the repository root write to the same database. Both
    # defaults are under `data/`, which `.gitignore` already excludes.

    pipeline_checkpoint_database_path: Path = Path("data/checkpoints.sqlite")
    pipeline_memory_database_path: Path = Path("data/memory.sqlite")

    # Where `runs/<run_id>.jsonl` is written. One file per run, appended as events are emitted, so a run
    # that is killed halfway still leaves a readable and replayable journal.
    pipeline_journal_directory: Path = Path("runs")

    # When LangGraph persists a checkpoint. Measured rather than assumed - see the recorded run in
    # `tests/integration/test_pipeline_durability.py`:
    #
    #   exit   -> a hard-killed process leaves ZERO checkpoints. Everything is recomputed.
    #   async  -> the checkpoint is written in the background, so a kill inside the write window loses it.
    #   sync   -> the checkpoint is committed before the next node starts.
    #
    # `sync` because of what a node costs here. A pipeline stage is model inference measured in minutes; a
    # SQLite commit is sub-millisecond. Trading a microsecond of latency per stage against re-running S13 is
    # not a close decision, and `async` only narrows that window rather than closing it.
    pipeline_durability: Literal["sync", "async", "exit"] = "sync"

    # LangGraph raises `GraphRecursionError` past this many supersteps. It is the guard against a cyclic
    # graph that never terminates - a real risk once 1.9 lets an agent route back into planning. The default
    # of 25 is LangGraph's; 60 is sized for the 20-stage pipeline plus the branching a cross-modal run adds.
    pipeline_recursion_limit: int = Field(default=60, ge=1, le=1_000)

    # How long a run is given after it is asked to stop before it is cancelled outright. An abandoned run
    # stops at its next node boundary (`product-truth.md` §1.3); this bounds the case where the current node
    # never reaches one - a stalled network read, a model that hangs. Short, because the operator has
    # already said stop.
    pipeline_abandon_grace_seconds: float = Field(default=10.0, gt=0, le=300)

    # --- Datasets. Phase 1.1. ------------------------------------------------------------------------------
    #
    # Where the benchmark datasets and the acquired Sentinel scenes live. One directory per `DatasetId`,
    # which is what lets `aeris dataset list` report presence and size without a manifest that could
    # disagree with the disk.
    #
    # Configurable rather than fixed because these are large - SEN12MS alone is ~430 GB - and the machine
    # that has room for them is often not the machine the repository is checked out on. An external drive
    # or a network mount is the normal answer, and it is a `.env` line rather than a symlink nobody
    # remembers making.

    datasets_directory: Path = Path("data/datasets")

    # How long to wait for a STAC search before giving up. The catalogue is a remote service and Phase 1.2
    # onwards calls it during a run, so a stall has to surface as an error the trace can show rather than
    # as a stage that appears to hang.
    stac_search_timeout_seconds: int = Field(default=60, ge=5, le=600)

    # Sentinel scenes are hundreds of megabytes per band. Generous, and separate from the STAC search
    # timeout because they fail for different reasons and want different answers.
    dataset_download_timeout_seconds: int = Field(default=1_800, ge=30, le=21_600)

    # The Planetary Computer STAC endpoint. Configurable because the same code works against any STAC API -
    # Element84's Earth Search, a self-hosted catalogue - and swapping is a URL, not a code change.
    stac_api_url: AnyHttpUrl = AnyHttpUrl("https://planetarycomputer.microsoft.com/api/stac/v1")

    # --- Tiles and COGs. Phase 1.2. ------------------------------------------------------------------------
    #
    # TiTiler serves the COGs this pipeline writes into MinIO as EPSG:3857 XYZ tiles - which is what the
    # frontend's globe consumes. Locally that is the `titiler` service in docker-compose.yml.
    #
    # A URL rather than a host and port because the deployed form is a path on a CDN, not a port on a host,
    # and reassembling it from parts at each call site is how one of them ends up with a doubled slash.
    tile_server_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8000")

    # Where COGs are built before they are uploaded. Local first, then uploaded: `cog_translate` seeks while
    # building overviews and a multipart upload cannot be seeked, so a direct-to-storage write would mean
    # buffering a whole band in memory (~240 MB) or producing wrong overviews.
    cog_working_directory: Path = Path("data/cogs")

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
    def checkpoint_database_path(self) -> Path:
        """The checkpoint database as an absolute path, with its parent directory guaranteed to exist.

        Resolved here rather than at the call site because three things open it - the CLI, the tests, and
        Phase 2's Inngest functions - and a relative path means they disagree the moment one of them is
        launched from a different directory. Creating the parent is done here for the same reason: the
        alternative is every caller remembering, and the one that forgets fails with `unable to open
        database file`, which names neither the path nor the reason.
        """
        return self._resolved_directory_for(self.pipeline_checkpoint_database_path)

    @property
    def memory_database_path(self) -> Path:
        """The long-term memory database, resolved and with its parent created. Never the same file as the
        checkpoints - see the reasoning on the settings above."""
        return self._resolved_directory_for(self.pipeline_memory_database_path)

    @property
    def journal_directory(self) -> Path:
        """Where run journals are written, resolved and created."""
        directory = self._absolute(self.pipeline_journal_directory)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _absolute(self, path: Path) -> Path:
        """Interpret a configured path relative to `backend/`, never to the working directory."""
        return path if path.is_absolute() else BACKEND_ROOT_DIRECTORY / path

    def _resolved_directory_for(self, path: Path) -> Path:
        """Absolute path to a file, with its parent directory created."""
        resolved = self._absolute(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    @property
    def dataset_root(self) -> Path:
        """The datasets directory as an absolute path, created if it does not exist.

        Resolved from `BACKEND_ROOT_DIRECTORY` like every other configured path, so `aeris dataset list`
        reports the same location whichever directory it was launched from - which matters more here than
        elsewhere, because the answer it gives is "is this 430 GB download already on the machine".
        """
        directory = self._absolute(self.datasets_directory)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @property
    def cog_working_directory_path(self) -> Path:
        """The COG build directory, absolute and created."""
        return self._resolved_directory_for(self.cog_working_directory / ".keep")

    @property
    def tile_server(self) -> str:
        """The tile server without the trailing slash `AnyHttpUrl` adds.

        Same reasoning as `storage_endpoint`: a doubled slash in a tile URL is a 404 from a server that is
        working perfectly, and it is stripped once here rather than at each of the places that build one.
        """
        return str(self.tile_server_url).rstrip("/")

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
