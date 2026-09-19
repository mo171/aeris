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

import os
import warnings
from pathlib import Path
from typing import Final, Literal

import ctranslate2

# Suppress Hugging Face symlink warnings for free models downloaded to Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Suppress PyTorch 3.14 deprecation warnings 
warnings.filterwarnings("ignore", category=FutureWarning, module="torch.jit._serialization")
from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, SecretStr, ValidationInfo, field_validator
from pydantic_core import Url
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.constants.voice import (
    SUPPORTED_VOICE_INPUT_SAMPLE_RATES_HERTZ,
    SUPPORTED_VOICE_OUTPUT_SAMPLE_RATES_HERTZ,
    VOICE_INPUT_SAMPLE_RATE_HERTZ,
    VOICE_OUTPUT_SAMPLE_RATE_HERTZ,
)

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
        # Unknown names are configuration errors. Silently ignoring a misspelled or aliased variable creates
        # a second, invisible configuration surface and makes the effective value impossible to audit.
        extra="forbid",
    )

    # --- Identity ---

    project_name: str = "SatQuery AI (AERIS)"
    version: str = "1.0.0"

    # --- Deployment shape ---

    environment: Literal["local", "development", "staging", "production"] = "local"
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])

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
    inngest_serve_origin: str | None = None

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

    tile_server_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8080")
    cog_working_directory: Path = Path("data/cogs")

    # --- The specialist fleet (Phase 1.6) ---

    # Where checkpoints are cached. Hugging Face Hub downloads land here rather than in the user's home
    # cache, so a machine's weights sit beside its datasets and `aeris doctor` can report them.
    model_weights_directory: Path = Path("data/models")
    # `auto` measures the device; `cpu` forces the degraded path, which is what a machine without CUDA gets
    # anyway and what a test that must not touch the GPU asks for.
    model_device: Literal["auto", "cuda", "cpu"] = "auto"
    # Overrides the measured budget, in megabytes. The 1.6 gate is an eviction, and on a card where every
    # model fits at once the only way to demonstrate one is to say how much room there is.
    model_vram_budget_megabytes: int | None = Field(default=None, ge=256)
    model_load_timeout_seconds: float = Field(default=600.0, gt=0, le=3_600)
    huggingface_token: SecretStr | None = None

    # --- The vision-language model (Phase 1.7) ---

    # Which Qwen3-VL base: `2b` fits the 4 GB profile at 4-bit; `4b` needs 8 GB. One flag per demo machine.
    vlm_size: Literal["2b", "4b"] = "2b"
    # The LoRA adapter that makes it a remote-sensing model - a Hub repository. `None` runs the base model
    # unadapted, and the fleet's version string says so.
    vlm_adapter_repository: str | None = None
    vlm_adapter_revision: str = "main"
    # NF4 weights on CUDA. Off only for measurement; a 2B model in bf16 does not fit beside anything.
    vlm_quantise: bool = True
    # `vlm`: S16 asks the model to phrase the claims (numbers injected, never generated; the template is
    # the fallback when the model is unavailable or its phrasing is rejected). `template`: the claims'
    # own sentences, no model - what a machine without weights, and the pipeline tests, get.
    # `llm` (1.9): the agent's language model phrases under the same guard, in a second instead of ten,
    # and falls back to the VLM when no provider is configured.
    answer_generator: Literal["llm", "vlm", "template"] = "llm"
    # S14 reads the evidence figure with the VLM and the answer carries the reading, labelled. Off skips
    # the node with the reason in the trace - a machine without weights still completes a run.
    vlm_reading: bool = True
    # Readings are cached in Redis by the hash of (pictures, prompt, model version). Same picture, same
    # question, same model -> same words without loading the model; 0 disables.
    vlm_reading_cache_ttl_seconds: int = Field(default=7 * 24 * 3600, ge=0)

    # --- The language model behind the agent (Phase 1.9) ---

    # `init_chat_model(llm_model, model_provider=llm_provider)` - the whole provider abstraction (ADR-002).
    # Every provider uses the single application-owned credential name `LLM_API_KEY`. `none` runs every
    # agent path without a model: the deterministic router, template plans and template answers.
    llm_provider: Literal["openai", "anthropic", "google_genai", "ollama", "none"] = "none"
    llm_model: str = "gpt-5-mini"
    # The key is passed explicitly to the provider; no provider-specific environment alias is accepted.
    llm_api_key: SecretStr | None = None
    # OpenAI reasoning models take an effort level instead of a temperature; passed only to that provider.
    llm_reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = "minimal"
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    # Who phrases the final answer and the claims: `llm` (fast, the numeral guard applies unchanged),
    # `vlm` (the 1.7 path), or the template. `answer_generator` above keeps S16's own setting; the agent's
    # synthesis follows this one.
    synthesis_generator: Literal["llm", "vlm", "template"] = "llm"
    # LangSmith tracing of every LangChain and LangGraph call. Read by LangChain from the environment;
    # `lib/llm/tracing.py` exports these there, the one place the process writes to `os.environ`.
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "aeris"

    # --- Offline voice session (Phase 1.13) ---

    # Every operational default in this section is provisional Task 3 configuration. Task 8 promotes values
    # only after retaining the target machine's real-device WER and latency measurements.

    # A selector is either the sounddevice device index or its stable display name. `None` intentionally
    # asks sounddevice to use its configured default; the session fails with remediation if it has none.
    voice_input_device: int | str | None = None
    voice_output_device: int | str | None = None
    # These settings make the model boundary explicit in `aeris doctor`; only the formats in constants/voice
    # are valid because accepting a host-native rate would silently change recognition or playback.
    voice_input_sample_rate_hertz: int = VOICE_INPUT_SAMPLE_RATE_HERTZ
    voice_output_sample_rate_hertz: int = VOICE_OUTPUT_SAMPLE_RATE_HERTZ
    # Provisional defaults pending Task 8's measured WER and latency gate. CPU/int8 starts safely on every
    # supported operator machine; a measured CUDA profile is an explicit deployment change, not a guess.
    voice_whisper_model: str = Field(default="small.en", min_length=1, max_length=200)
    voice_whisper_device: Literal["auto", "cpu", "cuda"] = "cpu"
    voice_whisper_compute_type: str = "int8"
    voice_whisper_language: str = Field(default="en", pattern=r"^[a-z]{2,3}$")
    # A turn is bounded so Ctrl+P cannot create an always-listening stream. Silero, not an RMS heuristic,
    # owns the speech decision; these values only bound its endpoint policy.
    voice_capture_max_duration_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    voice_vad_silence_duration_seconds: float = Field(default=0.8, ge=0.1, le=5.0)
    voice_vad_min_speech_duration_milliseconds: int = Field(default=250, ge=32, le=5_000)
    # Explicit local Piper assets make provisioning observable and prevent a runtime download on a turn.
    # These are provisional Task 8 candidates, not a performance claim or a model identifier shortcut.
    voice_synthesis_model_path: Path = Path("data/models/piper/en_GB-alan-medium.onnx")
    voice_synthesis_config_path: Path = Path("data/models/piper/en_GB-alan-medium.onnx.json")
    voice_synthesis_asset_repository: str = Field(
        default="rhasspy/piper-voices", pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
    )
    voice_synthesis_asset_revision: str = Field(
        default="1af0d6b01d3dbe698a426f0c3424650ef77fc131", pattern=r"^[0-9a-f]{40}$"
    )
    voice_synthesis_speaker_id: int = Field(default=0, ge=0)
    voice_synthesis_length_scale: float = Field(default=1.0, gt=0.5, le=2.0)
    # Progress speech is an AI-authored projection of the trace, throttled independently from results.
    voice_narration_enabled: bool = True
    voice_narration_minimum_interval_seconds: float = Field(default=8.0, ge=1.0, le=300.0)
    # Presentation-only proposals are bounded per scientific run; the frontend still validates each one.
    voice_ui_command_budget_per_run: int = Field(default=6, ge=1, le=20)

    @field_validator("log_level", mode="before")
    @classmethod
    def normalise_log_level(cls, raw_value: object) -> object:
        """Accept case-insensitive log levels."""
        if isinstance(raw_value, str):
            return raw_value.strip().upper()
        return raw_value

    @field_validator("voice_input_device", "voice_output_device", mode="before")
    @classmethod
    def normalise_voice_device_selector(cls, raw_value: object) -> object:
        """Accept an optional sounddevice name or index, but never an empty selector."""
        if isinstance(raw_value, str):
            selector = raw_value.strip()
            if not selector:
                raise ValueError("voice device selector must be a device index or non-empty device name")
            return int(selector) if selector.isdecimal() else selector
        return raw_value

    @field_validator("voice_input_sample_rate_hertz")
    @classmethod
    def require_supported_voice_input_sample_rate(cls, value: int) -> int:
        """Keep input PCM at the rate Silero and Whisper consume without hidden resampling."""
        if value not in SUPPORTED_VOICE_INPUT_SAMPLE_RATES_HERTZ:
            raise ValueError(f"supported input sample rates: {sorted(SUPPORTED_VOICE_INPUT_SAMPLE_RATES_HERTZ)}")
        return value

    @field_validator("voice_output_sample_rate_hertz")
    @classmethod
    def require_supported_voice_output_sample_rate(cls, value: int) -> int:
        """Keep output PCM at the rate emitted by the selected Kokoro pipeline."""
        if value not in SUPPORTED_VOICE_OUTPUT_SAMPLE_RATES_HERTZ:
            raise ValueError(f"supported output sample rates: {sorted(SUPPORTED_VOICE_OUTPUT_SAMPLE_RATES_HERTZ)}")
        return value

    @field_validator("voice_whisper_compute_type")
    @classmethod
    def require_supported_voice_whisper_compute_type(cls, value: str, info: ValidationInfo) -> str:
        """Use CTranslate2's own device capability query rather than maintaining a stale profile list."""
        normalised = value.strip().lower()
        device = info.data.get("voice_whisper_device")
        supported_compute_types = ctranslate2.get_supported_compute_types(device)
        if normalised not in supported_compute_types:
            raise ValueError(
                f"supported Whisper compute types for {device}: {sorted(supported_compute_types)}"
            )
        return normalised

    @field_validator("voice_vad_min_speech_duration_milliseconds")
    @classmethod
    def require_capture_to_fit_vad_endpointing(cls, value: int, info: ValidationInfo) -> int:
        """Ensure the bounded hotkey turn can contain minimum speech and its required silence endpoint."""
        capture_duration = info.data.get("voice_capture_max_duration_seconds")
        silence_duration = info.data.get("voice_vad_silence_duration_seconds")
        if capture_duration is not None and silence_duration is not None:
            endpoint_duration = silence_duration + value / 1_000
            if endpoint_duration >= capture_duration:
                raise ValueError(
                    "VOICE_CAPTURE_MAX_DURATION_SECONDS must exceed the minimum speech duration plus "
                    "VOICE_VAD_SILENCE_DURATION_SECONDS"
                )
        return value

    @field_validator("voice_synthesis_model_path")
    @classmethod
    def require_synthesis_onnx_model_path(cls, value: Path) -> Path:
        """Make a Piper ONNX asset explicit without requiring Task 8 provisioning during settings tests."""
        if value.suffix.lower() != ".onnx":
            raise ValueError("VOICE_SYNTHESIS_MODEL_PATH must point to an .onnx model asset")
        return value

    @field_validator("voice_synthesis_config_path")
    @classmethod
    def require_synthesis_onnx_config_path(cls, value: Path) -> Path:
        """Require Piper's separate local ONNX configuration alongside the model file."""
        if value.suffixes[-2:] != [".onnx", ".json"]:
            raise ValueError("VOICE_SYNTHESIS_CONFIG_PATH must point to an .onnx.json model configuration")
        return value

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
    def model_weights_path(self) -> Path:
        """Absolute path to the checkpoint cache, creating it if needed."""
        directory = self._absolute(self.model_weights_directory)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

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

    @property
    def is_testing(self) -> bool:
        """Whether the application is executing under an active test runner."""
        return bool(os.environ.get("PYTEST_CURRENT_TEST"))


# Instantiated at import to validate configuration immediately.
settings: Settings = Settings()
