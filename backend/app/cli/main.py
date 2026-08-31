"""The `aeris` command, and the one place in `app/` where `asyncio.run()` is called.

what  : The Typer application, the commands registered on it, and the translation from a result object into
        a process exit code.
where : The console script entry point declared in `pyproject.toml`. Phase 1 adds `dataset`, `ingest`,
        `analyse` and `voice` here as they are built; Phase 2 adds `app/routes/` beside this file and this
        one keeps working unchanged (`folder-archtecture.md` rule 1).
how   : **A Typer command callback is sync, and that is the `code-standards.md` §7 exception, not a
        violation of it.** Typer calls it synchronously, so declaring it `async def` would hand Typer a
        coroutine object where it expects a return. The callback therefore does exactly two things: start
        the loop, and turn the result into an exit code. Every line of actual work is an `async def` in a
        sibling module, which is what lets a Phase 2 route call the same function without touching the loop.

        **The exit code is part of the contract.** `aeris doctor` is meant to be usable from a shell script
        and from CI, where the table is decoration and `$?` is the answer. `0` means every check passed;
        `1` means at least one did not. It is asserted by a test that runs the real command in a
        subprocess - the only way to test an exit code without the test itself being the thing that gets it
        wrong.

        Connections are closed on the way out. The CLI is a short-lived process and the OS would reclaim
        them regardless, but leaving them open prints a wall of asyncio teardown warnings over the table the
        operator is trying to read.
"""

import asyncio

import typer
from rich.console import Console
from rich.markup import escape

from app.cli import doctor as doctor_command
from app.cli import run as run_command
from app.config import settings
from app.constants.intents import Intent
from app.constants.pipeline import GraphName
from app.constants.statuses import RunStatus
from app.lib import database, inngest, redis, storage
from app.lib.logger import configure_logging

app = typer.Typer(
    name="aeris",
    help="AERIS - agentic Earth-observation analysis with evidence-grounded answers.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()


@app.command()
def doctor(
    read_only: bool = typer.Option(
        False,
        "--read-only",
        help=(
            "Observe only. Skips the two probes that write: creating missing storage buckets, and sending "
            "the Inngest health-probe event."
        ),
    ),
) -> None:
    """Check every dependency and print what is in force. Exits non-zero if anything is wrong."""
    report = asyncio.run(_run_doctor(read_only=read_only))

    if not report.is_healthy:
        raise typer.Exit(code=1)


async def _run_doctor(read_only: bool) -> doctor_command.DoctorReport:
    """Everything `doctor` actually does, inside one event loop."""
    await configure_logging()
    try:
        report = await doctor_command.collect_report(read_only=read_only)
        await doctor_command.render_report(report, console)
        return report
    finally:
        await _close_connections()


async def _close_connections() -> None:
    """Release every pooled connection before the loop closes.

    Gathered rather than awaited in sequence because a hanging close on one client must not stop the others
    from being released - and `return_exceptions=True` because this runs in a `finally`, where raising would
    replace whatever the command was already reporting.
    """
    await asyncio.gather(
        database.dispose_engine(),
        redis.close_client(),
        storage.close_client(),
        inngest.reset_client(),
        return_exceptions=True,
    )


@app.command()
def run(
    query: str = typer.Argument("", help="The question to run. Not needed with --replay or --resume."),
    replay: str = typer.Option(
        "", "--replay", help="Re-render a finished run from its journal. Computes nothing, needs nothing."
    ),
    resume: str = typer.Option(
        "", "--resume", help="Continue a run that stopped partway, from its last checkpoint."
    ),
    intent: Intent = typer.Option(
        Intent.SCENE_VQA, "--intent", help="What kind of question this is. Phase 1.8 classifies it instead."
    ),
    graph: GraphName = typer.Option(GraphName.PROBE, "--graph", help="Which pipeline graph to run."),
    pause_seconds: float = typer.Option(
        0.0, "--pause", help="Seconds the probe graph's last stage pretends to work for. For testing stop."
    ),
) -> None:
    """Start, resume or replay a pipeline run, drawing its live S1-S20 trace."""
    # Mutually exclusive rather than silently preferring one: an operator who typed both meant something,
    # and guessing which half to honour is how a replay quietly becomes a second execution.
    if replay and resume:
        console.print("[red]--replay and --resume do different things; pass one.[/red]")
        raise typer.Exit(code=2)
    if not (replay or resume or query):
        console.print("[red]Nothing to do. Pass a query, --replay <run_id> or --resume <run_id>.[/red]")
        raise typer.Exit(code=2)

    status = asyncio.run(
        _run_pipeline(
            query=query,
            replay=replay,
            resume=resume,
            intent=intent,
            graph_name=graph,
            pause_seconds=pause_seconds,
        )
    )

    # The exit code is the contract, as it is for `doctor`. `complete` is the only success: a cancelled run
    # is a run that did not answer, and a script that treated it as one would carry on with no result.
    if status is not RunStatus.COMPLETE:
        raise typer.Exit(code=1)


async def _run_pipeline(
    *,
    query: str,
    replay: str,
    resume: str,
    intent: Intent,
    graph_name: GraphName,
    pause_seconds: float,
) -> RunStatus:
    """Everything `run` does, inside one event loop."""
    await configure_logging()
    try:
        if replay:
            return await run_command.execute_replay(run_id=replay, console=console)
        if resume:
            return await run_command.execute_resume(
                run_id=resume, intent=intent, graph_name=graph_name, console=console
            )
        return await run_command.execute_run(
            query=query,
            intent=intent,
            graph_name=graph_name,
            console=console,
            pause_seconds=pause_seconds,
        )
    finally:
        await _close_connections()


@app.command()
def version() -> None:
    """Print the version and the environment this process is configured for."""
    # `escape` because rich reads `[local]` as a style tag and prints nothing at all where the environment
    # should be - which is how the first run of this command reported a blank environment.
    console.print(escape(f"{settings.project_name} {settings.version} [{settings.environment}]"))


if __name__ == "__main__":
    app()
