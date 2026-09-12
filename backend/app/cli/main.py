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
from collections.abc import Coroutine
from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

from app.cli import analyse as analyse_command
from app.cli import ask as ask_command
from app.cli import dataset as dataset_command
from app.cli import doctor as doctor_command
from app.cli import figures as figures_command
from app.cli import ingest as ingest_command
from app.cli import models as models_command
from app.cli import preprocess as preprocess_command
from app.cli import route as route_command
from app.cli import run as run_command
from app.config import settings
from app.constants.datasets import DatasetId, DatasetSplit
from app.constants.intents import Intent
from app.constants.model_ids import ModelId
from app.constants.pipeline import GraphName
from app.constants.raster import ProcessingLevel
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


dataset_app = typer.Typer(
    name="dataset",
    help="Acquire, licence-check and catalogue the datasets the later phases need.",
    no_args_is_help=True,
)
app.add_typer(dataset_app)


@dataset_app.command("list")
def dataset_list() -> None:
    """Every dataset with its location, size, licence and redistribution status. The Phase 1.1 gate."""
    every_licence_checked = asyncio.run(_run_dataset(dataset_command.render_catalogue(console)))

    # Non-zero when a dataset is on disk whose terms nobody has read. The exit code is the contract, as it
    # is for `doctor`: this is what a CI step or a pre-training script actually branches on, and a warning
    # printed into a log is not something a script can act on.
    if not every_licence_checked:
        raise typer.Exit(code=1)


@dataset_app.command("show")
def dataset_show(
    dataset_id: DatasetId = typer.Argument(..., help="Which dataset."),
) -> None:
    """Everything known about one dataset, including its quirks and expected layout."""
    asyncio.run(_run_dataset(dataset_command.render_dataset(dataset_id, console)))


@dataset_app.command("fetch")
def dataset_fetch(
    dataset_id: DatasetId = typer.Argument(..., help="Which dataset."),
    bbox: str = typer.Option("", "--bbox", help="west,south,east,north in EPSG:4326. Imagery only."),
    from_date: str = typer.Option("", "--from", help="Start date, YYYY-MM-DD. Imagery only."),
    to_date: str = typer.Option("", "--to", help="End date, YYYY-MM-DD. Imagery only."),
    max_cloud: float = typer.Option(
        -1.0, "--max-cloud", help="Maximum cloud cover percentage. Optical only; Sentinel-1 has none."
    ),
    limit: int = typer.Option(10, "--limit", help="How many scenes to consider."),
    assets: str = typer.Option(
        "",
        "--asset",
        help=(
            "Comma-separated asset names to fetch, e.g. B04,B08 for NDVI. Defaults to the 10 m bands plus "
            "the scene classification layer; a full L2A scene is over a gigabyte."
        ),
    ),
    split: str = typer.Option(
        "", "--split", help="One split of a Hub-mirrored benchmark (train, val, test). Default: every split."
    ),
) -> None:
    """Acquire a dataset: STAC for imagery, a direct download or a Hub mirror where one exists, instructions otherwise."""
    acquired = asyncio.run(
        _run_dataset(
            dataset_command.execute_fetch(
                dataset_id,
                bounding_box=_parse_bounding_box(bbox),
                start=_parse_date(from_date, "--from"),
                end=_parse_date(to_date, "--to"),
                maximum_cloud_percentage=None if max_cloud < 0 else max_cloud,
                limit=limit,
                asset_names=tuple(name.strip() for name in assets.split(",") if name.strip()) or None,
                console=console,
                split=DatasetSplit(split) if split else None,
            )
        )
    )
    if not acquired:
        raise typer.Exit(code=1)


@dataset_app.command("search")
def dataset_search(
    dataset_id: DatasetId = typer.Argument(..., help="Sentinel-2 or Sentinel-1."),
    bbox: str = typer.Option(..., "--bbox", help="west,south,east,north in EPSG:4326."),
    from_date: str = typer.Option(..., "--from", help="Start date, YYYY-MM-DD."),
    to_date: str = typer.Option(..., "--to", help="End date, YYYY-MM-DD."),
    max_cloud: float = typer.Option(-1.0, "--max-cloud", help="Maximum cloud cover percentage."),
    limit: int = typer.Option(10, "--limit", help="How many scenes to list."),
) -> None:
    """List the scenes available over an area and date range, without downloading any."""
    asyncio.run(
        _run_dataset(
            dataset_command.execute_search(
                dataset_id,
                bounding_box=_parse_bounding_box(bbox) or (0.0, 0.0, 0.0, 0.0),
                start=_parse_date(from_date, "--from") or date.today(),
                end=_parse_date(to_date, "--to") or date.today(),
                maximum_cloud_percentage=None if max_cloud < 0 else max_cloud,
                limit=limit,
                console=console,
            )
        )
    )


def _parse_bounding_box(raw: str) -> tuple[float, float, float, float] | None:
    """`west,south,east,north` as four floats, or `None` when not given.

    Validated here rather than at the STAC call because a transposed box is still a valid box - usually
    somewhere in the ocean - so it comes back as "no scenes found" rather than as an error. Checking the
    ordering at the argument is the only place it is cheap.
    """
    if not raw:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        raise typer.BadParameter("--bbox takes four numbers: west,south,east,north")
    try:
        west, south, east, north = (float(part) for part in parts)
    except ValueError as error:
        raise typer.BadParameter(f"--bbox must be four numbers: {error}") from error
    if west >= east or south >= north:
        raise typer.BadParameter(
            f"--bbox must be west,south,east,north with west<east and south<north. "
            f"Got west={west} east={east} south={south} north={north} - the coordinates look transposed."
        )
    return (west, south, east, north)


def _parse_date(raw: str, flag: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as error:
        raise typer.BadParameter(f"{flag} must be YYYY-MM-DD: {error}") from error


async def _run_dataset[T](work: Coroutine[object, object, T]) -> T:
    """Configure logging, do the work, and close whatever it opened."""
    await configure_logging()
    try:
        return await work
    finally:
        await _close_connections()


ingest_app = typer.Typer(
    name="ingest",
    help="Inspect, validate and convert imagery into COGs the globe can draw. Stages S1-S6, S11.",
    no_args_is_help=True,
)
app.add_typer(ingest_app)


@ingest_app.command("inspect")
def ingest_inspect(
    path: Path = typer.Argument(..., help="A raster file."),
) -> None:
    """Describe a raster and report what is wrong with it. Converts nothing."""
    analysable = asyncio.run(_run_dataset(ingest_command.execute_inspect(path, console)))
    # Exit code is the contract, as with `doctor` and `dataset list`: a script deciding whether to run an
    # analysis over a scene branches on this rather than parsing a table.
    if not analysable:
        raise typer.Exit(code=1)


@ingest_app.command("scene")
def ingest_scene(
    path: Path = typer.Argument(..., help="A raster file to convert and upload."),
) -> None:
    """Validate a raster, convert it to a COG and upload it to object storage."""
    asyncio.run(_run_dataset(ingest_command.execute_ingest(path, console)))


@ingest_app.command("index")
def ingest_index(
    scene_directory: Path = typer.Argument(..., help="A fetched scene directory holding B04 and B08."),
) -> None:
    """Compute NDVI over a scene and publish it as a COG. The Phase 1.2 gate."""
    asyncio.run(
        _run_dataset(ingest_command.execute_index(scene_directory=scene_directory, console=console))
    )


@app.command()
def figures(
    scene_directory: Path = typer.Argument(..., help="A scene directory holding B02, B03, B04 and B08."),
    level: ProcessingLevel = typer.Option(
        ProcessingLevel.UNKNOWN,
        "--level",
        help="State the processing level when the path does not carry it. NDVI needs L2A.",
    ),
) -> None:
    """Render the three gate figures from a scene and verify one redraws byte-identically."""
    reproducible = asyncio.run(
        _run_dataset(
            figures_command.execute_render_figures(
                scene_directory=scene_directory,
                console=console,
                declared_level=None if level is ProcessingLevel.UNKNOWN else level,
            )
        )
    )
    # Non-zero when the reproduction claim fails. `api-contract.md` §6 rule 2 is a property of the system,
    # so it belongs in an exit code a script can gate on rather than in prose an operator has to read.
    if not reproducible:
        raise typer.Exit(code=1)


@app.command()
def analyse(
    scene: Path = typer.Option(..., "--scene", help="A scene directory holding the bands the index needs."),
    query: str = typer.Option(..., "--query", help='The question, e.g. "unhealthy vegetation" or "water".'),
    level: ProcessingLevel = typer.Option(
        ProcessingLevel.UNKNOWN,
        "--level",
        help="State the processing level when the path does not carry it. Every index needs L2A.",
    ),
) -> None:
    """Answer an index question over one scene: the map, the region, and its area in hectares. Phase 1.4."""
    status = asyncio.run(
        _run_dataset(
            analyse_command.execute_analyse(
                scene_directory=scene,
                query=query,
                console=console,
                declared_level=None if level is ProcessingLevel.UNKNOWN else level,
            )
        )
    )
    if status is not RunStatus.COMPLETE:
        raise typer.Exit(code=1)


preprocess_app = typer.Typer(
    name="preprocess",
    help="Cloud masking, co-registration and the SAR branch. Stages S7-S10.",
    no_args_is_help=True,
)
app.add_typer(preprocess_app)


@preprocess_app.command("coregister")
def preprocess_coregister(
    scene_directory: Path = typer.Argument(..., help="A scene directory holding s2_B04.tif."),
) -> None:
    """Measure a known-good and a known-bad pair, and refuse the bad one. Half the Phase 1.3 gate."""
    if not asyncio.run(
        _run_dataset(preprocess_command.execute_coregister(scene_directory, console))
    ):
        raise typer.Exit(code=1)


@preprocess_app.command("sar")
def preprocess_sar_command(
    scene_directory: Path = typer.Argument(..., help="A scene directory holding s1_vv.tif."),
) -> None:
    """Calibrate, speckle-filter and terrain-correct a radar scene, keeping the visibility masks."""
    if not asyncio.run(_run_dataset(preprocess_command.execute_sar(scene_directory, console))):
        raise typer.Exit(code=1)


@preprocess_app.command("relief")
def preprocess_relief() -> None:
    """Run the SAR branch over terrain steep enough to blind a radar. The rest of the Phase 1.3 gate."""
    if not asyncio.run(_run_dataset(preprocess_command.execute_relief(console))):
        raise typer.Exit(code=1)


models_app = typer.Typer(
    name="models",
    help="The specialist fleet: status, warming and eviction, and benchmark scores. Phase 1.6.",
    no_args_is_help=True,
)
app.add_typer(models_app)


@models_app.command("status")
def models_status() -> None:
    """The fleet as the frontend's strip draws it: health, latency, queue depth, per model."""
    asyncio.run(_run_models(models_command.render_status(console)))


@models_app.command("warm")
def models_warm(
    model_ids: list[ModelId] = typer.Argument(..., help="Models to load, in order."),
    budget: int = typer.Option(
        0, "--budget", help="VRAM budget in MB to work within. 0 measures the device. Half the 1.6 gate."
    ),
) -> None:
    """Load models back to back, printing each health transition, and show what was evicted to fit."""
    if not asyncio.run(
        _run_models(models_command.execute_warm(model_ids, budget_megabytes=budget or None, console=console))
    ):
        raise typer.Exit(code=1)


@app.command("ask")
def ask(
    image: list[Path] = typer.Option(..., "--image", help="One picture, or two for a pair (bi-temporal or optical/SAR)."),
    question: str | None = typer.Option(None, "--question", help="What to ask. Omit for a caption."),
    sar: list[bool] = typer.Option([], "--sar", help="Per image, in order: true if it is radar backscatter."),
    force_vlm: bool = typer.Option(False, "--force-vlm", help="Bypass the router and ask the VLM regardless. For comparison only."),
) -> None:
    """Ask about a picture: the router picks the specialist (a count goes to the detector, never the VLM). No run, no claims."""
    flags = list(sar) + [False] * (len(image) - len(sar))
    answered = asyncio.run(
        _run_models(ask_command.execute_ask(images=image, question=question, sar=flags[: len(image)], console=console, force_vlm=force_vlm))
    )
    if not answered:
        raise typer.Exit(code=1)


@app.command()
def route(
    query: str = typer.Argument("", help="The question to route. Omit with --evaluate."),
    evaluate: bool = typer.Option(False, "--evaluate", help="Score the classifier on the held-out questions: the 1.8 gate."),
    gsd: float | None = typer.Option(None, "--gsd", help="Metres per pixel of the scene, for the resolution gate."),
    images: int = typer.Option(1, "--images", help="How many images the question would be asked over."),
    sar: bool = typer.Option(False, "--sar", help="The image is radar."),
) -> None:
    """Show what the router makes of a question - intent, entities, specialist, graph - without running anything."""
    if evaluate:
        passed = asyncio.run(_run_models(route_command.execute_route_evaluate(console=console)))
    elif query:
        passed = asyncio.run(_run_models(route_command.execute_route(query=query, ground_sample_distance=gsd, image_count=images, sar=sar, console=console)))
    else:
        console.print("[red]Pass a question, or --evaluate.[/red]")
        raise typer.Exit(code=2)
    if not passed:
        raise typer.Exit(code=1)


@models_app.command("evaluate")
def models_evaluate(
    model_id: ModelId = typer.Option(ModelId.CHANGEFORMER, "--model", help="changeformer, dota-detector or rs-vlm."),
    dataset_id: DatasetId | None = typer.Option(None, "--dataset", help="A benchmark; defaults per model."),
    split: DatasetSplit | None = typer.Option(None, "--split", help="Which split to score; defaults per model."),
    limit: int = typer.Option(0, "--limit", help="Score only the first N samples. 0 scores every one."),
    file: Path | None = typer.Option(None, "--file", help="rs-vlm: an instruction .jsonl written by training/vlm/prepare_*.py."),
    predictions: Path | None = typer.Option(None, "--predictions", help="rs-vlm: write every row's prediction to this .jsonl for paired comparison."),
) -> None:
    """Score a learned model - change-class F1/IoU (changeformer), box F1 at IoU 0.5 (dota-detector), per-type VQA accuracy (rs-vlm)."""
    asyncio.run(
        _run_models(
            models_command.execute_evaluate(
                model_id=model_id, dataset_id=dataset_id, split=split, limit=limit or None, file=file,
                predictions=predictions, console=console,
            )
        )
    )


async def _run_models[T](work: Coroutine[object, object, T]) -> T:
    """Configure logging, do the work, unload the fleet, and close whatever it opened."""
    from app.models.manager import reset_manager

    await configure_logging()
    try:
        return await work
    finally:
        await reset_manager()
        await _close_connections()


@app.command()
def version() -> None:
    """Print the version and the environment this process is configured for."""
    # `escape` because rich reads `[local]` as a style tag and prints nothing at all where the environment
    # should be - which is how the first run of this command reported a blank environment.
    console.print(escape(f"{settings.project_name} {settings.version} [{settings.environment}]"))


if __name__ == "__main__":
    app()
