"""Finds out what device this process has, fetches a model's weights, and gives memory back - the three things every adapter needs and none should do itself.

what  : `Device` and `detect_device()`; `fetch_weights()` and `fetch_repository()`; `release_device_memory()`;
        `check_health()` for the `aeris doctor` row.
where : Called by `app/models/manager.py` (device, memory) and by each adapter in `app/models/` (weights).
        The only place `torch.cuda` is asked about memory, so the answer is one answer.
how   : **The profile is measured, not read from a product name.** `torch.cuda.mem_get_info()` reports the
        device's total and free bytes; the profile tier (`constants/fleet.py`) follows from the total, and
        the budget from the total and `VRAM_BUDGET_FRACTION` unless configuration overrides it. A 4 GB
        laptop card - the machine this was built on - is a real tier, not a degraded 8 GB.

        **torch is imported inside the functions, not at module level.** Importing it costs seconds and
        loads the CUDA runtime; `aeris doctor`, the contract tests and every graph that runs no model
        must not pay that. Callers that want torch have already decided to.

        Weights come from the Hugging Face Hub into `settings.model_weights_path`, pinned to the revision
        the fleet record names, so two machines that ran the same version ran the same bytes.
"""

import asyncio
import gc
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.constants.fleet import VRAM_BUDGET_FRACTION, VRAM_PROFILE_THRESHOLDS_MEGABYTES, VramProfile, WeightsSource
from app.lib.exceptions import UpstreamUnavailableError

logger = logging.getLogger(__name__)

MEGABYTE = 1 << 20


@dataclass(frozen=True, slots=True)
class Device:
    """What the fleet runs on, measured once per process."""

    kind: str
    name: str
    total_megabytes: int | None
    profile: VramProfile
    budget_megabytes: int

    @property
    def has_accelerator(self) -> bool:
        return self.kind == "cuda"


async def detect_device() -> Device:
    """Measure the device `settings.model_device` points at, or the CPU when there is none."""
    return await asyncio.to_thread(_detect_device, settings.model_device, settings.model_vram_budget_megabytes)


def _detect_device(preference: str, budget_override: int | None) -> Device:
    import torch

    if preference != "cpu" and torch.cuda.is_available():
        free_bytes, total_bytes = torch.cuda.mem_get_info(0)
        total = total_bytes // MEGABYTE
        profile = next(
            (tier for threshold, tier in VRAM_PROFILE_THRESHOLDS_MEGABYTES if total >= threshold), VramProfile.CPU
        )
        budget = budget_override or int(total * VRAM_BUDGET_FRACTION)
        logger.info(
            "device measured",
            extra={
                "device": torch.cuda.get_device_name(0), "total_megabytes": total,
                "free_megabytes": free_bytes // MEGABYTE, "profile": profile.value, "budget_megabytes": budget,
            },
        )
        return Device("cuda", torch.cuda.get_device_name(0), total, profile, budget)

    if preference == "cuda":
        raise UpstreamUnavailableError(
            "MODEL_DEVICE=cuda but torch reports no CUDA device.", details={"upstream": "cuda"}
        )
    # No accelerator: models still load, on the CPU, and report `degraded`. The budget bounds how many are
    # held at once by their declared footprints, exactly as on a card, so the manager's behaviour is the
    # same shape on a laptop without a GPU as with one.
    budget = budget_override or 4_096
    return Device("cpu", "cpu", None, VramProfile.CPU, budget)


async def fetch_weights(source: WeightsSource) -> Path:
    """One file from the Hub, at the pinned revision, cached under the weights directory."""
    if source.filename is None:
        return await fetch_repository(source)
    return await asyncio.to_thread(_download_file, source)


async def fetch_repository(source: WeightsSource) -> Path:
    """A whole repository snapshot - what `transformers.from_pretrained` wants - at the pinned revision."""
    return await asyncio.to_thread(_download_repository, source)


def _download_file(source: WeightsSource) -> Path:
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import HfHubHTTPError

    try:
        path = hf_hub_download(
            repo_id=source.repository,
            filename=source.filename,
            revision=source.revision,
            cache_dir=settings.model_weights_path,
            token=settings.huggingface_token.get_secret_value() if settings.huggingface_token else None,
        )
    except (HfHubHTTPError, OSError) as error:
        raise UpstreamUnavailableError(
            f"Could not fetch {source.filename} from {source.repository}@{source.revision}: {error}",
            details={"upstream": "huggingface-hub", "repository": source.repository},
        ) from error
    return Path(path)


def _download_repository(source: WeightsSource) -> Path:
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import HfHubHTTPError

    try:
        path = snapshot_download(
            repo_id=source.repository,
            revision=source.revision,
            cache_dir=settings.model_weights_path,
            token=settings.huggingface_token.get_secret_value() if settings.huggingface_token else None,
        )
    except (HfHubHTTPError, OSError) as error:
        raise UpstreamUnavailableError(
            f"Could not fetch {source.repository}@{source.revision}: {error}",
            details={"upstream": "huggingface-hub", "repository": source.repository},
        ) from error
    return Path(path)


async def release_device_memory() -> None:
    """Give evicted tensors back to the device. Python must drop its references first; this returns the
    freed blocks from torch's caching allocator to CUDA, which `del` alone does not."""
    await asyncio.to_thread(_release_device_memory)


def _release_device_memory() -> None:
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


@dataclass(frozen=True, slots=True)
class FleetHealth:
    """What `aeris doctor` reports about the fleet's device and weights cache. Never raises."""

    torch_version: str | None
    device: Device | None
    cached_checkpoints: int
    latency_ms: float | None
    failure_reason: str | None


async def check_health() -> FleetHealth:
    """Import torch, measure the device, count the cached checkpoints. A diagnostic, so it never raises."""
    started = time.perf_counter()
    try:
        device = await detect_device()
        import torch

        version = torch.__version__
    except Exception as error:  # noqa: BLE001 - a diagnostic reports the failure rather than raising it
        return FleetHealth(None, None, 0, None, f"{type(error).__name__}: {error}")
    cached = await asyncio.to_thread(lambda: sum(1 for _ in settings.model_weights_path.glob("models--*")))
    return FleetHealth(version, device, cached, (time.perf_counter() - started) * 1000, None)


async def resident_megabytes() -> int | None:
    """What torch currently holds on the device, or `None` on a CPU. The number a footprint is measured from."""
    return await asyncio.to_thread(_resident_megabytes)


def _resident_megabytes() -> int | None:
    import torch

    if not torch.cuda.is_available():
        return None
    torch.cuda.synchronize()
    return int(torch.cuda.memory_allocated(0) // MEGABYTE)
