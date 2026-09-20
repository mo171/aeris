"""The `aeris demo` command: offline verification, database seeding, and rehearsed demo execution.

what  : Typer command handler for executing the 4 canonical demonstration scenarios and verifying Phase 2.9 gates.
where : Registered under `demo_app` in `backend/app/cli/main.py`.
how   : Connects to `app/services/demo/` to execute real pipeline workflows, reporting results with Rich tables.
"""

import asyncio
import logging
from typing import Any

from rich.console import Console
from rich.table import Table

from app.schemas.demo import DemoRunRequest, DemoSuiteResult
from app.services.demo import bundle as demo_bundle
from app.services.demo import runner as demo_runner

logger = logging.getLogger(__name__)


async def execute_demo_run(
    console: Console,
    scenario_id: str | None = None,
    runs: int = 1,
) -> bool:
    """Execute demonstration run(s) and print scorecard table to console."""
    console.print(f"[bold cyan]AERIS Demonstration Suite[/bold cyan] (SIH 2026 Canonical) - {runs} iteration(s)")

    try:
        # 1. Ensure bundle is ready and seeded
        with console.status("[yellow]Verifying offline rasters and seeding demonstration environment...[/yellow]"):
            await demo_bundle.ensure_demo_rasters()
            await demo_bundle.seed_demo_environment()

        # 2. Run demo suite
        with console.status(f"[green]Executing demonstration scenarios ({runs} pass(es))...[/green]"):
            req = DemoRunRequest(scenario_id=scenario_id, iterations=runs)
            if scenario_id:
                single = await demo_runner.execute_demo_scenario(scenario_id)
                result = DemoSuiteResult(
                    bundle_id="bnd_aeris_sih2026_canonical",
                    success=single.status == "complete",
                    completed_runs=1,
                    total_duration_ms=single.duration_ms,
                    scenarios=[single],
                )
            else:
                result = await demo_runner.execute_full_demo_suite(iterations=runs)

        # 3. Render table
        table = Table(title=f"AERIS Demo Scorecard ({len(result.scenarios)} executions)")
        table.add_column("Scenario ID", style="cyan", no_wrap=True)
        table.add_column("Title", style="white")
        table.add_column("Status", style="bold green")
        table.add_column("Duration", justify="right")
        table.add_column("Confidence", justify="right")
        table.add_column("Evidence", justify="right")
        table.add_column("Trace ID", style="dim")

        for s in result.scenarios:
            conf_str = f"{s.confidence:.0%}" if s.confidence is not None else "N/A"
            status_style = "bold green" if s.status == "complete" else "bold red"
            table.add_row(
                s.scenario_id,
                s.title,
                f"[{status_style}]{s.status}[/{status_style}]",
                f"{s.duration_ms}ms",
                conf_str,
                str(s.evidence_count),
                s.trace_id,
            )

        console.print(table)
        console.print(f"Total Duration: [bold]{result.total_duration_ms}ms[/bold] | Success: [bold green]{result.success}[/bold green]")

        if runs >= 3 and result.success:
            console.print("[bold green][OK] Phase 2.9 Gate Passed: 3 consecutive runs completed cleanly.[/bold green]")

        return result.success
    except Exception as exc:
        console.print(f"[bold red]Demo execution error:[/bold red] {exc}")
        logger.exception("Demo CLI failed")
        return False


async def execute_demo_bundle(console: Console) -> bool:
    """Audit and display offline demonstration bundle status."""
    status = await demo_bundle.verify_offline_bundle()
    console.print(f"Bundle ID: [bold]{status['bundleId']}[/bold]")
    console.print(f"Status: [bold green]{status['status']}[/bold green]")
    console.print(f"Manifest Present: {status['manifestPresent']}")
    console.print(f"Rasters Present: {status['rastersPresent']}")
    for k, v in status["rasterPaths"].items():
        console.print(f"  - {k}: {v}")
    return status["status"] == "ready"


async def execute_demo_seed(console: Console) -> bool:
    """Seed demonstration project, scenes, and canonical investigation."""
    res = await demo_bundle.seed_demo_environment()
    console.print("[bold green]Seeded demonstration environment:[/bold green]")
    for k, v in res.items():
        console.print(f"  {k}: [cyan]{v}[/cyan]")
    return True
