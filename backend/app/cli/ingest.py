"""Everything `aeris ingest` does - inspect a raster, refuse it or accept it, convert it to a COG, and put it where the globe can draw it.

what  : `execute_inspect()`, `execute_ingest()` and `execute_index()` - the three async functions behind
        the `ingest` command.
where : Called from `cli/main.py`. Phase 1.2's gate is `execute_index` end to end: an NDVI COG in MinIO,
        rendered in a browser through TiTiler.
how   : This is S1-S6 and S11 wired together with a terminal in front of them, in the same relationship
        `aeris run` has to the pipeline: the command is an adapter, and every line of work is a service
        function a Phase 2 route will call unchanged.

        **`execute_index` computes NDVI, and that is not Phase 1.4 arriving early.** The 1.2 gate names an
        NDVI COG as the artefact it wants rendered in a browser, so something has to produce one. What is
        here is the *raster* half - read two bands, scale them, divide, write a COG - using only S1-S6
        primitives. What 1.4 owns and this deliberately does not touch: the index registry and its
        vocabulary, the cloud mask applied before the arithmetic (§8 rule 1), threshold selection, and the
        S12 trace step. The refusal on an unknown processing level is here because §8 rule 5 makes it a
        precondition of the arithmetic rather than a feature of the index engine.
"""

import logging
from pathlib import Path

import numpy as np
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from app.config import settings
from app.constants.raster import BandRole, ProcessingLevel
from app.constants.storage import Bucket
from app.lib.exceptions import ConflictError, InvalidRequestError
from app.services.imagery.cog import convert_to_cog, upload_cog, write_cog_from_array
from app.services.imagery.math.indices import normalised_difference, to_surface_reflectance
from app.services.imagery.metadata import RasterMetadata, inspect_raster
from app.services.imagery.tiling import plan_tiles
from app.services.imagery.validation import Severity, assess_raster, require_analysable

logger = logging.getLogger(__name__)

SEVERITY_STYLE = {Severity.WARNS: "yellow", Severity.REFUSES: "red"}


def _render_metadata(metadata: RasterMetadata, console: Console) -> None:
    """What S1-S3 found, as a table."""
    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column(style="dim")
    table.add_column(overflow="fold")
    for label, value in (
        ("driver", metadata.driver),
        ("size", f"{metadata.width} x {metadata.height}  ({metadata.pixel_count / 1e6:.0f} Mpx)"),
        ("dtype", metadata.dtype),
        ("nodata", "none declared" if metadata.nodata is None else f"{metadata.nodata:g}"),
        ("crs", metadata.crs or "NONE - cannot be placed on the globe"),
        ("projected", "yes" if metadata.is_projected else "no (degrees)"),
        ("resolution", f"{metadata.resolution[0]:g} x {metadata.resolution[1]:g}"),
        ("band", metadata.band.role.value if metadata.band.role else "unrecognised"),
        ("native gsd", f"{metadata.band.native_resolution_metres} m" if metadata.band.native_resolution_metres else "-"),
        ("level", metadata.processing_level.value),
        ("valid COG", "yes" if metadata.is_cloud_optimised else "no"),
    ):
        table.add_row(label, escape(str(value)))
    console.print(table)


async def execute_inspect(path: Path, console: Console) -> bool:
    """S1-S5: describe a raster and say what is wrong with it. Never converts anything.

    Returns whether it is analysable, which becomes the exit code - so a shell script can gate on a scene
    without parsing the table.
    """
    metadata = await inspect_raster(path)
    console.print(f"\n[bold cyan]{escape(path.name)}[/bold cyan]")
    _render_metadata(metadata, console)

    report = await assess_raster(metadata)
    statistics = report.statistics

    console.print(
        f"\n  measured over a 1/{report.decimation_step} decimated read "
        f"({statistics.valid_pixel_count:,} valid of {statistics.total_pixel_count:,} sampled)"
    )
    console.print(
        f"  nodata {statistics.nodata_fraction:.2%}   "
        f"range [{statistics.minimum:g}, {statistics.maximum:g}]   "
        f"p2-p98 [{statistics.percentile_2:g}, {statistics.percentile_98:g}]"
    )

    plan = plan_tiles(metadata)
    console.print(
        f"  inference grid: {plan.tile_count} tiles of {plan.tile_size} with {plan.overlap} overlap "
        f"(redundancy {plan.redundancy:.2f}x)"
    )

    if report.problems:
        console.print()
        for problem in report.problems:
            style = SEVERITY_STYLE[problem.severity]
            console.print(f"  [{style}]{problem.severity.value.upper():8s}[/{style}] {escape(problem.code)}")
            console.print(f"           {escape(problem.message)}")
    else:
        console.print("\n  [green]no problems[/green]")

    return report.is_analysable


async def execute_ingest(path: Path, console: Console) -> bool:
    """S1-S6: validate, convert to a COG, and upload it.

    Refuses before converting rather than after. A COG of an unusable scene costs minutes of GDAL and
    produces an artefact that looks legitimate in the bucket - which is worse than not producing it,
    because something downstream will find it and use it.
    """
    metadata = await inspect_raster(path)
    console.print(f"\n[bold cyan]{escape(path.name)}[/bold cyan]")
    _render_metadata(metadata, console)

    report = await require_analysable(metadata)
    for problem in report.warnings:
        console.print(f"  [yellow]{escape(problem.code)}[/yellow]: {escape(problem.message)}")

    destination = settings.cog_working_directory_path.parent / f"{path.parent.name}__{path.stem}.tif"
    console.print(f"\n  converting to COG -> {escape(str(destination))}")
    await convert_to_cog(metadata, destination)

    object_key = f"{path.parent.name}/{path.stem}.tif"
    result = await upload_cog(destination, object_key=object_key, bucket=Bucket.COG)

    console.print(f"  [green]uploaded[/green] {escape(result.storage_uri)}  ({result.size_bytes / 1e6:.1f} MB)")
    console.print(f"  tiles: {escape(_tilejson_url(result.storage_uri))}")
    return True


async def execute_index(
    *, scene_directory: Path, console: Console, index_name: str = "ndvi"
) -> bool:
    """**The Phase 1.2 gate.** Compute NDVI from a scene's bands and publish it as a COG.

    Only NDVI, and only from a scene whose two bands are already on disk. The index *engine* - the
    registry, the vocabulary, the cloud mask, the S12 trace step - is Phase 1.4; what this exercises is
    the raster path the gate names: read, scale, compute, write a COG, upload, serve.
    """
    red_path, nir_path = _require_ndvi_bands(scene_directory)

    red_metadata = await inspect_raster(red_path)
    nir_metadata = await inspect_raster(nir_path)

    # §8 rule 5. An index over uncorrected digital numbers is a different quantity wearing the same name,
    # and nothing in the pixels says which one it is - so an unknown level is refused rather than assumed.
    if red_metadata.processing_level is not ProcessingLevel.L2A:
        raise ConflictError(
            f"NDVI needs surface reflectance (L2A); this scene reads as "
            f"{red_metadata.processing_level.value}. An index over uncorrected values is a different "
            "quantity wearing the same name (architecture-context.md §8 rule 5).",
            details={"level": red_metadata.processing_level.value},
        )

    # Both bands must share a grid, or every pixel of the result combines two different places. Both are
    # 10 m Sentinel-2 bands so they do in practice, and checking costs nothing against being silently wrong.
    if (red_metadata.width, red_metadata.height) != (nir_metadata.width, nir_metadata.height):
        raise ConflictError(
            f"B04 is {red_metadata.width}x{red_metadata.height} and B08 is "
            f"{nir_metadata.width}x{nir_metadata.height}. Bands at different resolutions must be "
            "resampled onto one grid before any index is computed.",
            details={"red": list(red_metadata.resolution), "nir": list(nir_metadata.resolution)},
        )

    await require_analysable(red_metadata)
    await require_analysable(nir_metadata)

    console.print(f"\n  computing {escape(index_name.upper())} over {red_metadata.width}x{red_metadata.height}")
    array = await _compute_ndvi(red_metadata, nir_metadata)

    valid = np.isfinite(array)
    console.print(
        f"  {escape(index_name.upper())} range [{np.nanmin(array):.3f}, {np.nanmax(array):.3f}]   "
        f"mean {np.nanmean(array):.3f}   vegetated (>0.3) {float((array[valid] > 0.3).mean()):.1%}"
    )

    destination = settings.cog_working_directory_path.parent / f"{scene_directory.name}__{index_name}.tif"
    await write_cog_from_array(array, reference=red_metadata, destination=destination)

    object_key = f"{scene_directory.name}/{index_name}.tif"
    result = await upload_cog(destination, object_key=object_key, bucket=Bucket.COG)

    console.print(f"  [green]uploaded[/green] {escape(result.storage_uri)}  ({result.size_bytes / 1e6:.1f} MB)")
    console.print("\n  Render it:")
    console.print(f"    tilejson  {escape(_tilejson_url(result.storage_uri))}")
    console.print(f"    viewer    {escape(_viewer_url(result.storage_uri))}")
    return True


def _require_ndvi_bands(scene_directory: Path) -> tuple[Path, Path]:
    """Find red and near-infrared in a fetched scene directory.

    By band *role* rather than by file position: `B04` is red on Sentinel-2 and band 3 on Landsat, and a
    hardcoded index is how an NDVI silently becomes an NDWI.
    """
    from app.services.imagery.metadata import identify_band

    found: dict[BandRole, Path] = {}
    for candidate in sorted(scene_directory.glob("*.tif")):
        descriptor = identify_band(candidate)
        if descriptor.role in (BandRole.RED, BandRole.NEAR_INFRARED):
            found[descriptor.role] = candidate

    missing = {BandRole.RED, BandRole.NEAR_INFRARED} - set(found)
    if missing:
        raise InvalidRequestError(
            f"{scene_directory.name} has no {', '.join(sorted(role.value for role in missing))} band. "
            "NDVI needs red and near-infrared - fetch them with "
            "`aeris dataset fetch sentinel2-l2a --asset B04,B08 ...`.",
            details={"sceneDirectory": str(scene_directory)},
        )
    return found[BandRole.RED], found[BandRole.NEAR_INFRARED]


async def _compute_ndvi(red: RasterMetadata, nir: RasterMetadata) -> np.ndarray:
    """`(NIR - RED) / (NIR + RED)` over scaled surface reflectance, as float32 with NaN for nodata."""
    import asyncio

    return await asyncio.to_thread(_compute_ndvi_synchronously, red, nir)


def _compute_ndvi_synchronously(red: RasterMetadata, nir: RasterMetadata) -> np.ndarray:
    """Read both bands, scale them, and hand the arithmetic to `math/`.

    This function does I/O and nothing else. The scaling and the division live in
    `services/imagery/math/indices.py` - pure, sync and testable against arrays whose answers are known by
    construction (`architecture-context.md` §12). Keeping them apart is what let the [-337, +347] bug be
    fixed with a unit test rather than by re-running a two-minute scene conversion.
    """
    import rasterio

    with rasterio.open(red.path) as source:
        red_raw = source.read(1)
    with rasterio.open(nir.path) as source:
        nir_raw = source.read(1)

    red_reflectance = to_surface_reflectance(red_raw, nodata=red.nodata)
    nir_reflectance = to_surface_reflectance(nir_raw, nodata=nir.nodata)

    return normalised_difference(nir_reflectance, red_reflectance)


def _tilejson_url(storage_uri: str) -> str:
    """The TileJSON document for a COG. Carries `bounds`, `minzoom` and `maxzoom` - the 1.2 gate."""
    return f"{settings.tile_server}/cog/WebMercatorQuad/tilejson.json?url={storage_uri}"


def _viewer_url(storage_uri: str) -> str:
    """TiTiler's built-in map viewer, for looking at the result without writing a page."""
    return f"{settings.tile_server}/cog/viewer?url={storage_uri}"
