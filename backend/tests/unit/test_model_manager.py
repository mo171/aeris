"""Tests the fleet manager's residency arithmetic with models that cost nothing to load, so the eviction rule is checked on its own.

what  : Lazy loading, the four health states in order, LRU eviction within a budget, the in-use guard, the
        CPU fallback, queue depth, latency, the refusals for engines and unregistered ids, and the
        status payload against the frontend's schema.
where : Unit suite for `app/models/manager.py`. No GPU, no Redis (the cross-process lock is injected as a
        no-op), no weights: the loaders are coroutines that return a marker after a short pause.
how   : The 1.6 gate's second half is "two models requested back-to-back: the first evicts, the second
        loads, neither crashes, and `warming` is observable". Footprints are declared in `FLEET`, so a
        budget that holds one of the two learned models and not both makes the eviction deterministic,
        and a loader that pauses is what lets another task observe `warming` mid-load.
"""

import asyncio
import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.constants.fleet import FLEET, VramProfile
from app.constants.model_ids import ModelId
from app.constants.statuses import ModelHealth
from app.lib.exceptions import ConflictError
from app.models.loader import Device
from app.models.manager import ModelManager, no_cross_process_lock

CHANGE = ModelId.CHANGEFORMER
SEGMENT = ModelId.SEGFORMER_LANDCOVER
CHANGE_MB = FLEET[CHANGE].vram_megabytes
SEGMENT_MB = FLEET[SEGMENT].vram_megabytes

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
STATUS_SCHEMA = CONTRACTS["features/missionCommand/schemas/model.schema.ts"]["modelStatusCollectionSchema"]


def cuda_device(budget: int) -> Device:
    return Device("cuda", "test card", 4096, VramProfile.VRAM_4GB, budget)


def fake_loaders(load_seconds: float = 0.0, log: list[tuple[ModelId, str]] | None = None):
    def make(model_id: ModelId):
        async def loader(device: str) -> dict[str, Any]:
            if log is not None:
                log.append((model_id, device))
            await asyncio.sleep(load_seconds)
            return {"model": model_id.value, "device": device}

        return loader

    return {CHANGE: make(CHANGE), SEGMENT: make(SEGMENT)}


def manager_with(budget: int, load_seconds: float = 0.0, log: list[tuple[ModelId, str]] | None = None) -> ModelManager:
    return ModelManager(device=cuda_device(budget), loaders=fake_loaders(load_seconds, log), lock_factory=no_cross_process_lock)


async def test_a_model_is_loaded_once_on_first_lease_and_reused_after() -> None:
    log: list[tuple[ModelId, str]] = []
    manager = manager_with(budget=CHANGE_MB + SEGMENT_MB, log=log)

    async with manager.lease(CHANGE) as first:
        pass
    async with manager.lease(CHANGE) as second:
        pass

    assert first is second
    assert log == [(CHANGE, "cuda")]
    assert manager.health_of(CHANGE) is ModelHealth.ONLINE
    assert manager.resident_ids == (CHANGE,)


async def test_the_gate_the_first_model_evicts_and_the_second_loads() -> None:
    """A budget that holds either model but not both. Back to back: the first is evicted for the second."""
    manager = manager_with(budget=max(CHANGE_MB, SEGMENT_MB))

    async with manager.lease(CHANGE):
        pass
    assert manager.resident_ids == (CHANGE,)

    async with manager.lease(SEGMENT):
        pass

    assert manager.resident_ids == (SEGMENT,)
    assert manager.health_of(CHANGE) is ModelHealth.OFFLINE
    assert manager.health_of(SEGMENT) is ModelHealth.ONLINE
    assert manager.used_megabytes == SEGMENT_MB <= manager.device.budget_megabytes


async def test_warming_is_observable_from_another_task_while_the_load_runs() -> None:
    manager = manager_with(budget=CHANGE_MB, load_seconds=0.3)
    observed: list[ModelHealth] = []

    async def watch() -> None:
        for _ in range(20):
            collection = await manager.status()
            observed.append(next(row.health for row in collection.models if row.id is CHANGE))
            await asyncio.sleep(0.03)

    watcher = asyncio.create_task(watch())
    async with manager.lease(CHANGE):
        pass
    await watcher

    assert ModelHealth.WARMING in observed
    assert observed[-1] is ModelHealth.ONLINE
    assert observed.index(ModelHealth.WARMING) < len(observed) - 1 - observed[::-1].index(ModelHealth.ONLINE)


async def test_a_model_in_use_is_never_evicted_so_the_newcomer_degrades_to_cpu() -> None:
    manager = manager_with(budget=max(CHANGE_MB, SEGMENT_MB))

    async with manager.lease(CHANGE):
        async with manager.lease(SEGMENT) as segment:
            assert segment["device"] == "cpu"
            assert manager.health_of(CHANGE) is ModelHealth.ONLINE, "the in-use model stayed"
            assert manager.health_of(SEGMENT) is ModelHealth.DEGRADED

    with pytest.raises(ConflictError, match="in use"):
        async with manager.lease(CHANGE):
            await manager.evict(CHANGE)


async def test_least_recently_used_is_the_one_evicted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three models, room for two. The one touched longest ago goes, not the one loaded first."""
    from app.constants.fleet import FleetRecord, WeightsSource
    third = ModelId.GROUNDING_DINO_SAM
    fleet = dict(FLEET)
    fleet[third] = FleetRecord(third, "test", FLEET[third].capability, FLEET[third].stages,
                               WeightsSource("test/repo", None, "main"), 500, None)
    loaders = fake_loaders()

    async def third_loader(device: str) -> dict[str, Any]:
        return {"model": third.value, "device": device}

    loaders[third] = third_loader
    manager = ModelManager(
        device=cuda_device(CHANGE_MB + SEGMENT_MB), loaders=loaders, lock_factory=no_cross_process_lock, records=fleet
    )

    async with manager.lease(CHANGE):
        pass
    async with manager.lease(SEGMENT):
        pass
    async with manager.lease(CHANGE):  # CHANGE was loaded first but is now the more recently used
        pass
    async with manager.lease(third):
        pass

    assert set(manager.resident_ids) == {CHANGE, third}
    assert manager.health_of(SEGMENT) is ModelHealth.OFFLINE, "the least recently used, not the oldest, was evicted"


async def test_no_accelerator_loads_on_the_cpu_and_reports_degraded() -> None:
    manager = ModelManager(
        device=Device("cpu", "cpu", None, VramProfile.CPU, 4096), loaders=fake_loaders(), lock_factory=no_cross_process_lock
    )

    async with manager.lease(CHANGE) as model:
        assert model["device"] == "cpu"
    assert manager.health_of(CHANGE) is ModelHealth.DEGRADED


async def test_queue_depth_counts_the_waiters_and_returns_to_zero() -> None:
    manager = manager_with(budget=CHANGE_MB, load_seconds=0.2)
    depths: list[int] = []

    async def lease() -> None:
        async with manager.lease(CHANGE):
            pass

    tasks = [asyncio.create_task(lease()) for _ in range(3)]
    await asyncio.sleep(0.05)
    collection = await manager.status()
    depths.append(next(row.queue_depth for row in collection.models if row.id is CHANGE))
    await asyncio.gather(*tasks)
    collection = await manager.status()
    depths.append(next(row.queue_depth for row in collection.models if row.id is CHANGE))

    assert depths[0] == 3 and depths[1] == 0


async def test_engines_are_online_without_loading_and_cannot_be_leased() -> None:
    manager = manager_with(budget=CHANGE_MB)

    assert manager.health_of(ModelId.INDEX_ENGINE) is ModelHealth.ONLINE
    assert manager.health_of(ModelId.GEOSPATIAL_ENGINE) is ModelHealth.ONLINE
    with pytest.raises(ConflictError, match="deterministic engine"):
        async with manager.lease(ModelId.INDEX_ENGINE):
            pass


async def test_a_model_with_no_checkpoint_registered_is_offline_and_refuses() -> None:
    manager = manager_with(budget=CHANGE_MB)

    assert manager.health_of(ModelId.GROUNDING_DINO_SAM) is ModelHealth.OFFLINE
    with pytest.raises(ConflictError, match="no pretrained checkpoint"):
        async with manager.lease(ModelId.GROUNDING_DINO_SAM):
            pass


async def test_a_failed_load_leaves_the_model_offline_not_warming() -> None:
    async def broken(device: str) -> None:
        raise RuntimeError("weights corrupt")

    manager = ModelManager(device=cuda_device(CHANGE_MB), loaders={CHANGE: broken}, lock_factory=no_cross_process_lock)

    with pytest.raises(RuntimeError):
        async with manager.lease(CHANGE):
            pass
    assert manager.health_of(CHANGE) is ModelHealth.OFFLINE
    assert manager.resident_ids == ()


async def test_the_status_payload_validates_against_the_frontend_schema() -> None:
    manager = manager_with(budget=CHANGE_MB)
    async with manager.lease(CHANGE):
        pass
    await manager.record_latency(CHANGE, 120)
    await manager.record_latency(CHANGE, 80)

    payload = (await manager.status()).to_wire()

    Draft202012Validator(STATUS_SCHEMA, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(payload)
    assert {row["id"] for row in payload["models"]} == {model_id.value for model_id in ModelId}
    row = next(row for row in payload["models"] if row["id"] == CHANGE.value)
    assert row["medianLatencyMs"] == 100 and row["health"] == "online" and row["version"] == FLEET[CHANGE].version
