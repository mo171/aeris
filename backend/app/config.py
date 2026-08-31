"""Configuration settings for the backend, loaded from `.env` and validated at import.

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

# The repository's `backend/` directory, resolved statically.
BACKEND_ROOT_DIRECTORY: Path = Path(__file__).resolve().parent.parent

# Maps URL fields to their passwordless property accessors for safe logging.
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
        # 'ignore' prevents crashing on new .env variables during phased development.
        extra="ignore",
    )

    # --- Identity ---

    project_name: str = "SatQuery AI (AERIS)"
    version: str = "1.0.0"

    # --- Deployment shape ---

    environment: Literal["local", "development", "staging", "production"] = "local"
    debug: bool = False

    # --- Logging ---

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # --- Inngest ---

    inngest_event_key: SecretStr
    inngest_signing_key: SecretStr
    inngest_app_id: str = "aeris-backend"
    inngest_api_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8288")
    inngest_event_api_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8288")
    inngest_request_timeout_seconds: int = Field(default=10, ge=1, le=120)

    # --- Database ---

    database_url: PostgresDsn
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=50)
    database_connect_timeout_seconds: int = Field(default=10, ge=1, le=120)
    database_echo_sql: bool = False

    @field_validator("database_url")
    @classmethod
    def require_async_driver(cls, value: PostgresDsn) -> PostgresDsn:
        """Reject a DSN that doesn't use the asyncpg driver."""
        if value.scheme != "postgresql+asyncpg":
            raise ValueError(
                f"DATABASE_URL must use the postgresql+asyncpg driver, got {value.scheme!r}. "
            )
        return value

    # --- Redis ---

    redis_url: RedisDsn
    redis_cache_default_ttl_seconds: int = Field(default=300, ge=1, le=86_400)
    redis_lock_timeout_seconds: float = Field(default=120.0, gt=0, le=3_600)
    redis_lock_blocking_timeout_seconds: float = Field(default=30.0, ge=0, le=3_600)
    redis_connect_timeout_seconds: int = Field(default=5, ge=1, le=120)
    redis_max_connections: int = Field(default=20, ge=1, le=200)

    # --- Object storage ---

    storage_endpoint_url: AnyHttpUrl
    storage_access_key: SecretStr
    storage_secret_key: SecretStr
    storage_public_endpoint_url: AnyHttpUrl | None = None
    storage_region: str = "us-east-1"
    storage_bucket_prefix: str = Field(default="aeris", pattern=r"^[a-z0-9][a-z0-9-]{1,20}[a-z0-9]$")
    storage_addressing_style: Literal["path", "virtual", "auto"] = "path"
    storage_browser_origin: AnyHttpUrl = AnyHttpUrl("http://localhost:3000")
    storage_presigned_get_expiry_seconds: int = Field(default=3_600, ge=60, le=604_800)
    storage_presigned_put_expiry_seconds: int = Field(default=21_600, ge=60, le=604_800)
    storage_connect_timeout_seconds: int = Field(default=10, ge=1, le=120)
    storage_read_timeout_seconds: int = Field(default=60, ge=1, le=600)

    # --- Pipeline Spine ---

    pipeline_checkpoint_database_path: Path = Path("data/checkpoints.sqlite")
    pipeline_memory_database_path: Path = Path("data/memory.sqlite")
    pipeline_journal_directory: Path = Path("runs")
    pipeline_durability: Literal["sync", "async", "exit"] = "sync"
    pipeline_recursion_limit: int = Field(default=60, ge=1, le=1_000)
    pipeline_abandon_grace_seconds: float = Field(default=10.0, gt=0, le=300)

    # --- Datasets ---

    datasets_directory: Path = Path("data/datasets")
    stac_search_timeout_seconds: int = Field(default=60, ge=5, le=600)
    dataset_download_timeout_seconds: int = Field(default=1_800, ge=30, le=21_600)
    stac_api_url: AnyHttpUrl = AnyHttpUrl("https://planetarycomputer.microsoft.com/api/stac/v1")

    # --- Tiles and COGs ---

    tile_server_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8000")
    cog_working_directory: Path = Path("data/cogs")

    @field_validator("log_level", mode="before")
    @classmethod
    def normalise_log_level(cls, raw_value: object) -> object:
        """Accept case-insensitive log levels."""
        if isinstance(raw_value, str):
            return raw_value.strip().upper()
        return raw_value

    @property
    def database_url_without_password(self) -> str:
        """Returns the DSN with the password hidden for safe logging."""
        return make_url(str(self.database_url)).render_as_string(hide_password=True)

    @property
    def redis_url_without_password(self) -> str:
        """Returns the Redis URL with the password hidden for safe logging."""
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
        """Returns the storage endpoint without a trailing slash."""
        return str(self.storage_endpoint_url).rstrip("/")

    @property
    def storage_signing_endpoint(self) -> str:
        """Returns the public endpoint used for presigned URLs."""
        return str(self.storage_public_endpoint_url or self.storage_endpoint_url).rstrip("/")

    @property
    def storage_browser_origin_header(self) -> str:
        """Returns the browser origin formatted for CORS headers (no trailing slash)."""
        return str(self.storage_browser_origin).rstrip("/")

    @property
    def checkpoint_database_path(self) -> Path:
        """Absolute path to the checkpoint database, creating parent directories if needed."""
        return self._resolved_directory_for(self.pipeline_checkpoint_database_path)

    @property
    def memory_database_path(self) -> Path:
        """Absolute path to the memory database, creating parent directories if needed."""
        return self._resolved_directory_for(self.pipeline_memory_database_path)

    @property
    def journal_directory(self) -> Path:
        """Absolute path to the runs journal directory, creating it if needed."""
        directory = self._absolute(self.pipeline_journal_directory)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _absolute(self, path: Path) -> Path:
        """Interpret a configured path relative to `backend/`."""
        return path if path.is_absolute() else BACKEND_ROOT_DIRECTORY / path

    def _resolved_directory_for(self, path: Path) -> Path:
        """Return absolute path to a file, creating its parent directories."""
        resolved = self._absolute(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    @property
    def dataset_root(self) -> Path:
        """Absolute path to datasets directory, creating it if needed."""
        directory = self._absolute(self.datasets_directory)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @property
    def cog_working_directory_path(self) -> Path:
        """Absolute path to the COG build directory, creating it if needed."""
        return self._resolved_directory_for(self.cog_working_directory / ".keep")

    @property
    def tile_server(self) -> str:
        """Returns the tile server URL without a trailing slash."""
        return str(self.tile_server_url).rstrip("/")

    @property
    def inngest_is_production(self) -> bool:
        """Whether the Inngest SDK should operate in production mode."""
        return self.environment in {"staging", "production"}

    @property
    def is_production(self) -> bool:
        """Whether the environment is production."""
        return self.environment == "production"


# Instantiated at import to validate configuration immediately.
settings: Settings = Settings()
