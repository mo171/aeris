"""Keeps the fleet resident within the VRAM there actually is - loading lazily, evicting the least recently used, and telling the truth about each model's state.

what  : `ModelManager`, with `lease()` (the way a stage gets a model), `status()` (the fleet strip's
        payload), `evict()` and `unload_all()`; `get_manager()` for the process-wide one.
where : Every S13 service leases its model from here; `aeris models` reads `status()`; Phase 2.1's
        `GET /models/status` serves it. Loaders are registered by `app/models/registry.py`.
how   : **A lease, not a handle.** `async with manager.lease(model_id) as model:` marks the model in use for
        the block, and an in-use model is never evicted - the alternative is a tensor freed under an
        inference running in a thread, which is a crash on the next kernel launch. Eviction chooses among
        idle models only, least recently used first, until the requested footprint fits the budget.

        **Health is what the manager knows, not what it hopes.** `offline` until a load starts; `warming`
        while the weights are read and moved - which is visible to `status()` from another task, and is
        the half of the 1.6 gate about observability; `online` once resident on the accelerator;
        `degraded` when resident on the CPU because there is no accelerator or the model would not fit
        even with everything else evicted. A deterministic engine is `online` while the process is.

        **The load is serialised twice.** An `asyncio.Lock` orders decisions in this process, so two tasks
        asking for the same model produce one load and one waiter (`queueDepth` counts that waiter). The
        Redis lock from Phase 0.3 orders loads *across* processes, so a Phase 2 worker fleet does not put
        two copies of a 1.2 GB model on one card. The lock factory is injected so a unit test of the
        eviction arithmetic needs no Redis.

        **Footprints are declared, not measured at load.** `constants/fleet.py` states what each model
        costs, measured once; the manager sums declarations against the budget. Measuring at load time
        would make admission depend on the allocator's caching state, which is not a property of the model.
"""

import asyncio
import logging
import statistics
import time
from collections import Counter, OrderedDict, deque
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.constants.fleet import FLEET, LATENCY_WINDOW, UNAVAILABLE_VERSION, FleetRecord
from app.constants.model_ids import ModelId
from app.constants.statuses import ModelHealth
from app.lib.exceptions import ConflictError, ResourceNotFoundError
from app.lib.redis import held_lock
from app.models.loader import Device, detect_device, release_device_memory
from app.schemas.responses.model_status import ModelStatus, ModelStatusCollection

logger = logging.getLogger(__name__)

# A loader turns a device string into a resident adapter. Registered per model by `registry.py`.
type Loader = Callable[[str], Awaitable[Any]]
type LockFactory = Callable[[str], AbstractAsyncContextManager[Any]]


@dataclass(slots=True)
class Resident:
    """One loaded model and what the manager knows about it."""

    record: FleetRecord
    adapter: Any
    device_kind: str
    loaded_at: float
    last_used: float
    in_use: int = 0


@dataclass(slots=True)
class _Telemetry:
    health: ModelHealth = ModelHealth.OFFLINE
    latencies_ms: deque[int] = field(default_factory=lambda: deque(maxlen=LATENCY_WINDOW))


class ModelManager:
    """The fleet's residency, in one process."""

    def __init__(
        self,
        *,
        device: Device,
        loaders: Mapping[ModelId, Loader],
        lock_factory: LockFactory | None = None,
        records: Mapping[ModelId, FleetRecord] = FLEET,
    ) -> None:
        self.device = device
        self._loaders = dict(loaders)
        # The fleet this process serves. `FLEET` by default; `registry.resolved_fleet()` swaps in the
        # configured VLM variant, whose base and footprint are a setting rather than a constant.
        self._records = dict(records)
        self._lock_factory = lock_factory or _redis_lock
        self._decisions = asyncio.Lock()
        self._resident: OrderedDict[ModelId, Resident] = OrderedDict()
        self._telemetry: dict[ModelId, _Telemetry] = {model_id: _Telemetry() for model_id in self._records}
        self._waiting: Counter[ModelId] = Counter()
        for model_id, record in self._records.items():
            if record.weights is None and record.version != UNAVAILABLE_VERSION:
                self._telemetry[model_id].health = ModelHealth.ONLINE

    @classmethod
    async def create(
        cls,
        loaders: Mapping[ModelId, Loader],
        lock_factory: LockFactory | None = None,
        records: Mapping[ModelId, FleetRecord] = FLEET,
    ) -> ModelManager:
        return cls(device=await detect_device(), loaders=loaders, lock_factory=lock_factory, records=records)

    # --- Leasing -------------------------------------------------------------------------------------

    @asynccontextmanager
    async def lease(self, model_id: ModelId) -> AsyncIterator[Any]:
        """Hold a model for the block. Loads it first if it is not resident, evicting idle models to fit."""
        self._waiting[model_id] += 1
        try:
            resident = await self._ensure_resident(model_id)
        finally:
            self._waiting[model_id] -= 1
        resident.in_use += 1
        try:
            yield resident.adapter
        finally:
            resident.in_use -= 1
            resident.last_used = time.monotonic()
            self._resident.move_to_end(model_id)

    async def _ensure_resident(self, model_id: ModelId) -> Resident:
        record = self._records.get(model_id)
        if record is None:
            raise ResourceNotFoundError(f"No fleet record for {model_id}.", details={"modelId": model_id})
        if record.weights is None:
            raise ConflictError(
                f"{model_id.value} has no weights to load"
                + (" - it is a deterministic engine, not a resident model." if record.version != UNAVAILABLE_VERSION
                   else " - no pretrained checkpoint is registered for it yet (constants/fleet.py)."),
                details={"modelId": model_id.value, "version": record.version},
            )
        loader = self._loaders.get(model_id)
        if loader is None:
            raise ConflictError(
                f"{model_id.value} has weights but no loader registered in this process.",
                details={"modelId": model_id.value},
            )

        async with self._decisions:
            resident = self._resident.get(model_id)
            if resident is not None:
                resident.last_used = time.monotonic()
                self._resident.move_to_end(model_id)
                return resident

            device_kind = await self._make_room(record)
            self._telemetry[model_id].health = ModelHealth.WARMING
            started = time.perf_counter()
            try:
                async with self._lock_factory(f"model:{model_id.value}"):
                    adapter = await loader(device_kind)
            except BaseException:
                self._telemetry[model_id].health = ModelHealth.OFFLINE
                raise
            now = time.monotonic()
            resident = Resident(record=record, adapter=adapter, device_kind=device_kind, loaded_at=now, last_used=now)
            self._resident[model_id] = resident
            self._telemetry[model_id].health = (
                ModelHealth.ONLINE if device_kind == "cuda" else ModelHealth.DEGRADED
            )
            logger.info(
                "model loaded",
                extra={
                    "model_id": model_id.value, "version": record.version, "device": device_kind,
                    "load_ms": round((time.perf_counter() - started) * 1000),
                    "resident_megabytes": self.used_megabytes, "budget_megabytes": self.device.budget_megabytes,
                },
            )
            return resident

    async def _make_room(self, record: FleetRecord) -> str:
        """Evict idle models, least recently used first, until `record` fits. Returns the device to load on."""
        if not self.device.has_accelerator:
            await self._evict_until(record.vram_megabytes)
            return "cpu"
        if record.vram_megabytes > self.device.budget_megabytes:
            logger.warning(
                "model exceeds the whole budget; loading on the CPU",
                extra={"model_id": record.model_id.value, "vram_megabytes": record.vram_megabytes,
                       "budget_megabytes": self.device.budget_megabytes},
            )
            return "cpu"
        fitted = await self._evict_until(record.vram_megabytes)
        return "cuda" if fitted else "cpu"

    async def _evict_until(self, needed_megabytes: int) -> bool:
        """Evict idle residents until `needed_megabytes` fits. False when in-use models leave no room."""
        while self.used_megabytes + needed_megabytes > self.device.budget_megabytes:
            victim = next((m for m, r in self._resident.items() if r.in_use == 0), None)
            if victim is None:
                return False
            await self._drop(victim)
        return True

    async def _drop(self, model_id: ModelId) -> None:
        resident = self._resident.pop(model_id)
        del resident.adapter
        self._telemetry[model_id].health = ModelHealth.OFFLINE
        await release_device_memory()
        logger.info("model evicted", extra={"model_id": model_id.value, "resident_megabytes": self.used_megabytes})

    async def evict(self, model_id: ModelId) -> None:
        """Unload one model now. Refused while it is in use."""
        async with self._decisions:
            resident = self._resident.get(model_id)
            if resident is None:
                return
            if resident.in_use:
                raise ConflictError(f"{model_id.value} is in use and cannot be evicted.", details={"modelId": model_id.value})
            await self._drop(model_id)

    async def unload_all(self) -> None:
        async with self._decisions:
            for model_id in list(self._resident):
                if self._resident[model_id].in_use == 0:
                    await self._drop(model_id)

    # --- Telemetry -----------------------------------------------------------------------------------

    async def record_latency(self, model_id: ModelId, milliseconds: int) -> None:
        self._telemetry[model_id].latencies_ms.append(max(0, milliseconds))

    async def status(self) -> ModelStatusCollection:
        """The fleet as the frontend's strip draws it: one row per model id, engines included."""
        rows = []
        for model_id, record in self._records.items():
            telemetry = self._telemetry[model_id]
            latencies = telemetry.latencies_ms
            rows.append(
                ModelStatus(
                    id=model_id,
                    version=record.version,
                    health=telemetry.health,
                    median_latency_ms=int(statistics.median(latencies)) if latencies else 0,
                    queue_depth=self._waiting[model_id],
                )
            )
        return ModelStatusCollection(models=rows, checked_at=datetime.now(UTC))

    @property
    def resident_ids(self) -> tuple[ModelId, ...]:
        return tuple(self._resident)

    @property
    def used_megabytes(self) -> int:
        return sum(resident.record.vram_megabytes for resident in self._resident.values())

    def health_of(self, model_id: ModelId) -> ModelHealth:
        return self._telemetry[model_id].health


def _redis_lock(name: str) -> AbstractAsyncContextManager[Any]:
    # Both timeouts are the load timeout: the lock must outlive a slow load, and a second process waiting
    # for the same model should wait for that load rather than be refused after the default 30 s.
    return held_lock(
        name,
        timeout_seconds=settings.model_load_timeout_seconds,
        blocking_timeout_seconds=settings.model_load_timeout_seconds,
    )


def no_cross_process_lock(name: str) -> AbstractAsyncContextManager[Any]:
    """For a test of the residency arithmetic, which must not need Redis."""
    return nullcontext()


_manager: ModelManager | None = None


async def get_manager() -> ModelManager:
    """The process-wide manager, built on first use with the fleet's loaders."""
    global _manager
    if _manager is None:
        from app.models.registry import LOADERS, resolved_fleet

        _manager = await ModelManager.create(LOADERS, records=resolved_fleet())
    return _manager


async def reset_manager() -> None:
    """Unload everything and forget the manager. For the CLI's exit and for tests."""
    global _manager
    if _manager is not None:
        await _manager.unload_all()
        _manager = None
