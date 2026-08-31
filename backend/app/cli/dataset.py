"""Everything `aeris dataset` does - the licence-and-availability table that is the Phase 1.1 gate, plus fetching.

what  : `render_catalogue()`, `render_dataset()`, `execute_fetch()` and `execute_search()`.
where : Called from `cli/main.py`. `search_scenes` is shared with Phase 1.2's catalogue endpoint, so the
        query behind `POST /catalogue/search` is the one this command runs.
how   : The roadmap's gate: **"`aeris dataset list` reports every dataset with its on-disk location, size,
        licence and redistribution status."** The table below is that sentence, column for column.

        **The licence column is the one that matters, and unverified entries are made loud rather than
        blank.** A dataset whose terms nobody has read prints `UNVERIFIED` in red, not an empty cell -
        because an empty cell reads as "nothing to worry about" and the whole point of the gate is that
        this question gets answered before a training run rather than after one.

        Size is measured from the disk, never taken from the record's published figure. A half-finished
        4 GB download of a 10 GB dataset is the case the whole command exists to make visible.

        Every value is `escape`d before it reaches rich, as everywhere else - a licence summary or a quirk
        containing square brackets would otherwise silently print as nothing (`aeris version`, Phase 0.6).
"""

import logging
from datetime import date

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from app.constants.datasets import DATASET_CATALOGUE, DatasetId
from app.constants.licences import Licence, Redistribution
from app.services.datasets.acquisition import (
    acquisition_plan,
    download_archive,
    fetch_scene,
    search_scenes,
)
from app.services.datasets.catalogue import Availability, inspect_catalogue, inspect_dataset

logger = logging.getLogger(__name__)

AVAILABILITY_STYLE: dict[Availability, str] = {
    Availability.READY: "green",
    Availability.PARTIAL: "yellow",
    Availability.ABSENT: "dim",
    Availability.MALFORMED: "red",
}

REDISTRIBUTION_STYLE: dict[Redistribution, str] = {
    Redistribution.PERMITTED: "green",
    Redistribution.PERMITTED_WITH_ATTRIBUTION: "green",
    Redistribution.PERMITTED_SHARE_ALIKE: "yellow",
    Redistribution.FORBIDDEN: "red",
}


def human_size(size_bytes: int) -> str:
    """Bytes as something an operator can read. Returns `-` for nothing, never `0 B`, which reads as an
    empty download rather than as an absent one."""
    if size_bytes == 0:
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024 or unit == "TB":
            return f"{size_bytes:.0f} {unit}" if unit == "B" else f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} TB"


async def render_catalogue(console: Console) -> bool:
    """The gate's table. Returns whether every present dataset has a licence somebody has actually read."""
    statuses = inspect_catalogue()

    table = Table(title="Datasets", expand=False)
    table.add_column("dataset", style="cyan", overflow="fold")
    table.add_column("phase", width=5)
    table.add_column("state", width=9)
    table.add_column("on disk", justify="right", width=9)
    table.add_column("samples", justify="right", width=8)
    table.add_column("licence", overflow="fold")
    table.add_column("redistribution", overflow="fold")

    for status in statuses:
        total_samples = sum(status.sample_counts.values())
        licence_style = "red" if status.record.licence is Licence.UNVERIFIED else (
            "yellow" if not status.record.licence_verified else "green"
        )
        table.add_row(
            escape(status.record.dataset_id.value),
            escape(status.record.unlocked_in),
            f"[{AVAILABILITY_STYLE[status.availability]}]{status.availability.value}[/]",
            human_size(status.size_bytes),
            str(total_samples) if total_samples else "-",
            f"[{licence_style}]{escape(status.licence_label)}[/]",
            f"[{REDISTRIBUTION_STYLE[status.terms.redistribution]}]"
            f"{escape(status.terms.redistribution.value)}[/]",
        )

    console.print(table)
    console.print(f"root: {escape(str(statuses[0].directory.parent))}")

    unverified = [status for status in statuses if not status.record.licence_verified]
    present_unverified = [status for status in unverified if status.availability is not Availability.ABSENT]

    if present_unverified:
        # Loud, because this is the gate's actual subject. A dataset sitting on the disk whose terms nobody
        # has read is the exact situation "recorded before any training begins" is written against.
        console.print(
            f"\n[red]{len(present_unverified)} dataset(s) are on disk with an unchecked licence.[/red] "
            "Training on them is refused until someone reads the terms:"
        )
        for status in present_unverified:
            console.print(f"  {escape(status.record.dataset_id.value)}  ->  {escape(status.record.licence_url)}")
    elif unverified:
        console.print(
            f"\n{len(unverified)} catalogued dataset(s) have an unchecked licence, none of them downloaded "
            "yet. Check the terms as part of acquiring each one."
        )

    for status in statuses:
        if status.availability is Availability.MALFORMED:
            console.print(f"\n[red]{escape(status.record.dataset_id.value)}[/red]: {escape(status.problem or '')}")

    return not present_unverified


async def render_dataset(dataset_id: DatasetId, console: Console) -> None:
    """Everything known about one dataset, including the quirks that cost someone an afternoon."""
    status = inspect_dataset(dataset_id)
    record = status.record

    console.print(f"\n[bold cyan]{escape(record.title)}[/bold cyan]  ({escape(record.dataset_id.value)})")
    console.print(f"  {escape(record.task)}")

    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column(style="dim")
    table.add_column(overflow="fold")
    for label, value in (
        ("sensor", record.sensor),
        ("resolution", record.resolution),
        ("published scale", record.scale),
        ("unlocked in", f"Phase {record.unlocked_in}"),
        ("state", status.availability.value),
        ("directory", str(status.directory)),
        ("on disk", human_size(status.size_bytes)),
        ("download size", record.approximate_size),
        ("licence", status.licence_label),
        ("licence terms", status.terms.summary),
        ("redistribution", status.terms.redistribution.value),
        ("commercial use", status.terms.commercial_use.value),
        ("training permitted", "yes" if status.is_licensed_for_training else "no - see licence"),
        ("licence page", record.licence_url),
        ("source", record.source_url),
        ("acquisition", record.acquisition),
        ("layout", record.layout.kind.value),
    ):
        table.add_row(label, escape(str(value)))
    console.print(table)

    if status.sample_counts:
        counts = "  ".join(f"{split.value}={count}" for split, count in status.sample_counts.items())
        console.print(f"  samples: {escape(counts)}")

    expected = "  ".join(
        f"{split.value}->{directory}" for split, directory in record.layout.split_directories.items()
    )
    console.print(f"  expected splits: {escape(expected)}")
    console.print(f"  images in: {escape(', '.join(record.layout.image_directories))}")
    if record.layout.label_directory:
        console.print(f"  labels in: {escape(record.layout.label_directory)}")

    if record.quirks:
        console.print("\n  [yellow]quirks[/yellow]")
        for quirk in record.quirks:
            console.print(f"    - {escape(quirk)}")

    if status.problem:
        console.print(f"\n  [red]{escape(status.problem)}[/red]")


async def execute_search(
    dataset_id: DatasetId,
    *,
    bounding_box: tuple[float, float, float, float],
    start: date,
    end: date,
    maximum_cloud_percentage: float | None,
    limit: int,
    console: Console,
) -> list:
    """Search the STAC catalogue and print what is available over an area."""
    scenes = await search_scenes(
        dataset_id,
        bounding_box=bounding_box,
        start=start,
        end=end,
        maximum_cloud_percentage=maximum_cloud_percentage,
        limit=limit,
    )

    if not scenes:
        console.print("[yellow]No scenes match. Widen the dates, the box, or the cloud limit.[/yellow]")
        return scenes

    table = Table(title=f"{dataset_id.value} over {bounding_box}", expand=False)
    table.add_column("#", width=3, justify="right")
    table.add_column("scene", style="cyan", overflow="fold")
    table.add_column("acquired", width=12)
    table.add_column("cloud", justify="right", width=8)
    for index, scene in enumerate(scenes):
        cloud = "-" if scene.cloud_cover_percentage is None else f"{scene.cloud_cover_percentage:.1f}%"
        table.add_row(str(index), escape(scene.scene_id), scene.acquired_on, cloud)
    console.print(table)
    return scenes


async def execute_fetch(
    dataset_id: DatasetId,
    *,
    bounding_box: tuple[float, float, float, float] | None,
    start: date | None,
    end: date | None,
    maximum_cloud_percentage: float | None,
    limit: int,
    asset_names: tuple[str, ...] | None,
    console: Console,
) -> bool:
    """Acquire a dataset by whichever of the three routes its record declares."""
    record = DATASET_CATALOGUE[dataset_id]

    if record.acquisition == "manual":
        console.print(escape(acquisition_plan(dataset_id).instructions))
        # Not a failure. "Go and get this one yourself" is an answer, and exiting non-zero would make a
        # script treat a correct response as a broken command.
        return True

    if record.acquisition == "download":
        console.print(f"Downloading {escape(record.title)} ({escape(record.approximate_size)})...")
        destination = await download_archive(dataset_id)
        console.print(f"[green]Saved[/green] {escape(str(destination))}")
        console.print(
            "  Left compressed on purpose - several of these unpack to a different top-level directory "
            "than their name suggests. Unpack it so the layout in "
            f"`aeris dataset show {escape(dataset_id.value)}` holds."
        )
        return True

    if bounding_box is None or start is None or end is None:
        console.print(
            "[red]--bbox, --from and --to are required to fetch imagery.[/red] "
            "A STAC fetch needs an area and a date range; there is no sensible default for either."
        )
        return False

    scenes = await execute_search(
        dataset_id,
        bounding_box=bounding_box,
        start=start,
        end=end,
        maximum_cloud_percentage=maximum_cloud_percentage,
        limit=limit,
        console=console,
    )
    if not scenes:
        return False

    console.print(f"\nFetching {escape(scenes[0].scene_id)}...")
    destination = await fetch_scene(dataset_id, scenes[0], asset_names=asset_names)
    console.print(f"[green]Fetched[/green] {escape(str(destination))}")
    return True
