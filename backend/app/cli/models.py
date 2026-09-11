"""Everything `aeris models` does - show the fleet, warm models into VRAM and watch them evict, score the change detector.

what  : `render_status()`, `execute_warm()` and `execute_evaluate()`.
where : Called from `cli/main.py`. Phase 2.1 serves `render_status`'s payload from `GET /models/status`;
        1.14 turns `execute_evaluate` into the committed scorecard.
how   : The 1.6 gate, exactly: *"change mask plus area statistics computed for a LEVIR-CD test pair,
        scored against ground truth. Two models requested back-to-back on the 8 GB profile: the first
        evicts, the second loads, neither crashes, and `warming` is observable in the status output."*

        `execute_warm` is the second half made watchable. It leases each model in turn as a background
        task and polls `status()` while the load runs, printing every health transition it sees - so
        `warming` is *observed*, from another task, not asserted. On a card where both models fit, the
        eviction is demonstrated by stating a budget (`--budget`), which is what the roadmap's "on the
        8 GB profile" means on a laptop with four.

        This is an adapter and nothing more: the fleet is `app/models/`, the score is
        `services/evaluation/`, and both are what a Phase 2 route calls unchanged.
"""

import asyncio
import logging

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from app.constants.datasets import DATASET_CATALOGUE, DatasetId, DatasetSplit
from app.constants.fleet import FLEET
from app.constants.model_ids import ModelId
from app.constants.statuses import ModelHealth
from app.models.loader import Device, detect_device
from app.models.manager import ModelManager, get_manager
from app.models.registry import LOADERS
from app.services.evaluation.change_detection import evaluate_change_detection

logger = logging.getLogger(__name__)

HEALTH_STYLE = {
    ModelHealth.ONLINE: "green",
    ModelHealth.WARMING: "yellow",
    ModelHealth.DEGRADED: "magenta",
    ModelHealth.OFFLINE: "dim",
}
STATUS_POLL_SECONDS = 0.1


async def render_status(console: Console, manager: ModelManager | None = None) -> None:
    """The fleet strip, as a table: one row per model id, engines included."""
    manager = manager or await get_manager()
    device = manager.device
    console.print(
        f"\n  device {escape(device.name)}  profile {device.profile.value}  "
        f"budget {device.budget_megabytes} MB  resident {manager.used_megabytes} MB"
    )
    collection = await manager.status()
    table = Table(box=None, padding=(0, 2, 0, 0))
    for column in ("model", "version", "health", "median ms", "queue", "vram MB", "weights"):
        table.add_column(column, overflow="fold")
    for status in collection.models:
        record = FLEET[status.id]
        table.add_row(
            status.id.value,
            escape(status.version),
            f"[{HEALTH_STYLE[status.health]}]{status.health.value}[/{HEALTH_STYLE[status.health]}]",
            str(status.median_latency_ms),
            str(status.queue_depth),
            str(record.vram_megabytes) if record.weights else "-",
            escape(record.weights.repository) if record.weights else "engine" if record.version != "0.0.0" else "none registered",
        )
    console.print(table)


async def execute_warm(model_ids: list[ModelId], *, budget_megabytes: int | None, console: Console) -> bool:
    """Load the named models one after another, watching the fleet's health as each comes up."""
    device = await detect_device()
    if budget_megabytes is not None:
        device = Device(device.kind, device.name, device.total_megabytes, device.profile, budget_megabytes)
    manager = ModelManager(device=device, loaders=LOADERS)
    await render_status(console, manager)

    healthy = True
    for model_id in model_ids:
        console.print(f"\n  leasing {escape(model_id.value)} ({FLEET[model_id].vram_megabytes} MB) ...")
        before = set(manager.resident_ids)
        seen = await _lease_while_watching(manager, model_id, console)
        after = set(manager.resident_ids)
        evicted = before - after
        health = manager.health_of(model_id)
        console.print(
            f"  {escape(model_id.value)} is [{HEALTH_STYLE[health]}]{health.value}[/{HEALTH_STYLE[health]}]"
            + (f"; evicted {', '.join(sorted(m.value for m in evicted))}" if evicted else "")
            + f"; resident {manager.used_megabytes} of {device.budget_megabytes} MB"
        )
        healthy &= ModelHealth.WARMING in seen and health in (ModelHealth.ONLINE, ModelHealth.DEGRADED)

    await render_status(console, manager)
    await manager.unload_all()
    return healthy


async def _lease_while_watching(manager: ModelManager, model_id: ModelId, console: Console) -> list[ModelHealth]:
    """Lease in a task; poll `status()` from this one and print each health transition as it happens."""
    seen: list[ModelHealth] = []

    async def lease() -> None:
        async with manager.lease(model_id):
            pass

    task = asyncio.create_task(lease())
    while not task.done():
        collection = await manager.status()
        health = next(row.health for row in collection.models if row.id is model_id)
        queue = next(row.queue_depth for row in collection.models if row.id is model_id)
        if not seen or seen[-1] is not health:
            seen.append(health)
            console.print(f"    status: [{HEALTH_STYLE[health]}]{health.value}[/{HEALTH_STYLE[health]}]  queue {queue}")
        await asyncio.sleep(STATUS_POLL_SECONDS)
    await task
    final = manager.health_of(model_id)
    if seen[-1] is not final:
        seen.append(final)
        console.print(f"    status: [{HEALTH_STYLE[final]}]{final.value}[/{HEALTH_STYLE[final]}]")
    return seen


async def execute_evaluate(
    *, dataset_id: DatasetId, split: DatasetSplit, limit: int | None, console: Console
) -> bool:
    """Score the change detector on a benchmark split and print the change-class metrics and areas."""
    manager = await get_manager()
    console.print(f"\n  scoring changeformer on {escape(dataset_id.value)} {split.value}" + (f" (first {limit})" if limit else ""))
    report = await evaluate_change_detection(manager=manager, dataset_id=dataset_id, split=split, limit=limit)
    score = report.score
    console.print(
        f"\n  {report.samples} samples  model {escape(report.model_version)}  "
        f"mean latency {report.mean_latency_ms:.0f} ms"
        + (f"  mean stated confidence {report.mean_confidence:.3f}" if report.mean_confidence is not None else "")
    )
    console.print(
        f"  change class   precision {score.precision:.4f}   recall {score.recall:.4f}   "
        f"[bold]F1 {score.f1:.4f}[/bold]   IoU {score.iou:.4f}"
    )
    console.print(
        f"  pixels         TP {score.true_positives:,}  FP {score.false_positives:,}  "
        f"FN {score.false_negatives:,}  TN {score.true_negatives:,}"
    )
    console.print(
        f"  area           predicted {report.predicted_hectares:,.2f} ha   truth {report.truth_hectares:,.2f} ha   "
        f"(nominal {DATASET_CATALOGUE[dataset_id].pixel_size_metres:g} m pixels)"
    )
    await render_status(console, manager)
    return True
