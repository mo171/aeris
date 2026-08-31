"""Everything `aeris figures` does - render the three figures the Phase 1.2.1 gate names, and prove one of them redraws byte-identically.

what  : `execute_render_figures()`.
where : Called from `cli/main.py`. Phase 1.4 onwards calls the same `services/rendering/` functions from
        inside pipeline nodes, emitting each figure the moment its stage produces an array.
how   : The 1.2.1 gate, exactly: *"three figures rendered from the scene that closed 1.2 and nothing more:
        a true-colour RGB composite, its NDVI array as a colourised index map with a drawn colourbar, and a
        binary mask over that composite. Each carries a machine-readable legend, a non-null `traceStepId`
        and a complete `renderSpec`; each is written to `runs/<run_id>/figures/` and to MinIO.
        Re-rendering from the recorded `renderSpec` is byte-identical."*

        **The reproduction check runs here, not only in a test.** `api-contract.md` §6 rule 2 is about
        evidence months later, so the command an operator actually runs is the one that demonstrates it -
        a claim proven only in CI is a claim the person holding the figure cannot check.

        **The local copies are fetched back out of storage**, by the same `figure_writer` consumer the
        pipeline registers. It would be quicker to write the bytes we already have in memory; fetching
        them proves the object is retrievable under a key something else can reconstruct, which is
        precisely what breaks silently and surfaces in Phase 2 as an image that will not load.

        This is a CLI adapter and nothing more: every line of work is a `services/rendering/` function a
        Phase 2 route will call unchanged.
"""

import logging
from pathlib import Path

import numpy as np
import rasterio
from rich.console import Console
from rich.markup import escape

from app.cli.renderers.figure_writer import FigureWriter, open_figure_writer
from app.constants.raster import BandRole, ProcessingLevel
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.lib.exceptions import ConflictError, InvalidRequestError
from app.schemas.events import serialise_event
from app.services.imagery.math.indices import normalised_difference, to_surface_reflectance
from app.services.imagery.metadata import RasterMetadata, identify_band, inspect_raster
from app.services.rendering.figures import (
    RenderedFigure,
    render_from_spec,
    render_index_map,
    render_mask_overlay,
    render_rgb_composite,
)

logger = logging.getLogger(__name__)

# Above this NDVI a pixel is called vegetated. A demonstration threshold, not a calibrated one - Phase 1.4
# owns index thresholds and their justification. Stated here so the mask figure has something real to draw.
VEGETATION_THRESHOLD = 0.3

REQUIRED_ROLES = (BandRole.RED, BandRole.GREEN, BandRole.BLUE, BandRole.NEAR_INFRARED)


def _find_bands(scene_directory: Path) -> dict[BandRole, Path]:
    """Locate bands by role, never by file position.

    `B04` is red on Sentinel-2 and band 3 on Landsat; a positional read is how a true-colour composite
    silently becomes a false-colour one that still looks like a photograph.
    """
    found: dict[BandRole, Path] = {}
    for candidate in sorted(scene_directory.glob("*.tif")):
        role = identify_band(candidate).role
        if role is not None:
            found[role] = candidate
    return found


async def execute_render_figures(
    *,
    scene_directory: Path,
    console: Console,
    declared_level: ProcessingLevel | None = None,
) -> bool:
    """Render the three gate figures from one scene and verify the reproduction claim."""
    bands = _find_bands(scene_directory)
    missing = set(REQUIRED_ROLES) - set(bands)
    if missing:
        raise InvalidRequestError(
            f"{scene_directory.name} is missing {', '.join(sorted(role.value for role in missing))}. "
            "A true-colour composite needs red, green and blue; the index map needs near-infrared.",
            details={"sceneDirectory": str(scene_directory)},
        )

    reflectance, metadata = await _read_reflectance(bands)
    _require_surface_reflectance(metadata, declared_level)

    # A real run id, so the figures land under `runs/<run_id>/figures/` exactly as a pipeline run's would.
    run_id = new_identifier(IdentifierPrefix.RUN)
    console.print(f"\nrun {escape(run_id)}  from {escape(scene_directory.name)}")
    console.print(f"  {metadata.width}x{metadata.height}  {escape(metadata.crs or 'no CRS')}")

    async with open_figure_writer(run_id) as writer:
        return await _render_three(
            reflectance=reflectance,
            metadata=metadata,
            run_id=run_id,
            scene_name=scene_directory.name,
            writer=writer,
            console=console,
        )


async def _read_reflectance(
    bands: dict[BandRole, Path],
) -> tuple[dict[BandRole, np.ndarray], RasterMetadata]:
    """Read every required band and scale it to surface reflectance."""
    reflectance: dict[BandRole, np.ndarray] = {}
    metadata: RasterMetadata | None = None

    for role in REQUIRED_ROLES:
        metadata = await inspect_raster(bands[role])
        with rasterio.open(bands[role]) as source:
            raw = source.read(1)
        reflectance[role] = to_surface_reflectance(raw, nodata=metadata.nodata)

    assert metadata is not None
    return reflectance, metadata


def _require_surface_reflectance(
    metadata: RasterMetadata, declared_level: ProcessingLevel | None
) -> None:
    """**§8 rule 5**, and the same refusal `aeris ingest index` makes.

    An NDVI over uncorrected values is a different quantity wearing the same name - and a *figure* of it is
    worse than a number, because the VLM reads the picture at S14 and an operator reads it at a glance.

    `--level` exists because the level is read from the scene path, and a band extracted into a research
    directory has lost it. **A human stating what the data is is not the same thing as the code guessing**;
    only the second is what §8 rule 5 forbids.
    """
    level = declared_level or metadata.processing_level
    if level is not ProcessingLevel.L2A:
        raise ConflictError(
            f"This scene reads as {level.value}, and NDVI needs surface reflectance (L2A). If you know "
            "what it is, say so with --level; the code will not assume it "
            "(architecture-context.md §8 rule 5).",
            details={"level": level.value},
        )


async def _render_three(
    *,
    reflectance: dict[BandRole, np.ndarray],
    metadata: RasterMetadata,
    run_id: str,
    scene_name: str,
    writer: FigureWriter,
    console: Console,
) -> bool:
    """The three figures, each fetched back to disk as it lands, then the reproduction check."""
    scene_reference = [scene_name]

    # --- 1. True colour --------------------------------------------------------------------------------
    composite = await render_rgb_composite(
        reflectance[BandRole.RED],
        reflectance[BandRole.GREEN],
        reflectance[BandRole.BLUE],
        run_id=run_id,
        # Every figure names the stage whose output it renders (§6 rule 1). Minted here because this
        # command is not a pipeline run; from 1.4 they are the real trace step ids.
        trace_step_id=new_identifier(IdentifierPrefix.TRACE_STEP),
        title="True colour",
        bands=["B04", "B03", "B02"],
        scene_ids=scene_reference,
        crs=metadata.crs,
        is_primary=True,
    )
    await _report(composite, writer, console)

    # --- 2. NDVI index map -----------------------------------------------------------------------------
    ndvi = normalised_difference(reflectance[BandRole.NEAR_INFRARED], reflectance[BandRole.RED])
    index_map = await render_index_map(
        ndvi,
        run_id=run_id,
        trace_step_id=new_identifier(IdentifierPrefix.TRACE_STEP),
        title="NDVI",
        label="NDVI",
        bands=["B08", "B04"],
        scene_ids=scene_reference,
        crs=metadata.crs,
        # Honest: no cloud mask has been applied. Phase 1.3 builds one, and §8 rule 1 makes applying it
        # before index arithmetic mandatory - so this figure records that it was not.
        mask_applied=False,
    )
    await _report(index_map, writer, console)

    # --- 3. Vegetation mask over the composite ---------------------------------------------------------
    # NaN becomes -1 rather than 0: a masked pixel must fall below the threshold, and 0 would put every
    # unobserved pixel just under it by luck rather than by decision.
    vegetated = np.nan_to_num(ndvi, nan=-1.0) > VEGETATION_THRESHOLD
    overlay = await render_mask_overlay(
        vegetated,
        composite.rgba,
        run_id=run_id,
        trace_step_id=new_identifier(IdentifierPrefix.TRACE_STEP),
        title=f"Vegetation (NDVI > {VEGETATION_THRESHOLD})",
        label=f"NDVI > {VEGETATION_THRESHOLD}",
        scene_ids=scene_reference,
        crs=metadata.crs,
    )
    await _report(overlay, writer, console)
    console.print(f"  vegetated: {float(vegetated.mean()):.1%} of the scene")

    # --- The reproduction claim ------------------------------------------------------------------------
    console.print("\n  re-rendering the index map from its recorded renderSpec...")
    redrawn = await render_from_spec(ndvi, index_map.event.render_spec, label="NDVI")
    identical = redrawn == index_map.image_bytes

    if identical:
        console.print(f"  [green]byte-identical[/green]  {len(redrawn):,} bytes  (api-contract.md §6 rule 2)")
    else:
        console.print(
            f"  [red]NOT identical[/red]  {len(index_map.image_bytes):,} vs {len(redrawn):,} bytes. "
            "The renderSpec is missing something the render depends on."
        )

    console.print(f"\n  {len(writer.written)} figures written to {escape(str(writer.directory))}")
    for path in writer.written:
        console.print(f"    {escape(path.name)}")

    return identical


async def _report(figure: RenderedFigure, writer: FigureWriter, console: Console) -> None:
    """Print one figure's provenance, then hand its event to the writer that fetches it back."""
    event = figure.event
    legend = event.legend
    console.print(
        f"\n  [cyan]{escape(event.kind.value)}[/cyan]  {escape(event.figure_id)}  "
        f"{event.width}x{event.height}  {len(figure.image_bytes) / 1024:.0f} KB"
    )
    console.print(f"    trace step   {escape(event.trace_step_id)}")
    console.print(
        f"    legend       {escape(legend.kind.value)}  {escape(legend.label)}  "
        f"ramp {escape(legend.color_ramp.value)}"
        + (f"  domain {legend.domain}" if legend.domain else "")
    )
    specification = event.render_spec
    console.print(
        f"    renderSpec   bands {specification.bands}  stretch {specification.stretch}  "
        f"resampling {escape(specification.resampling)}  masked {specification.mask_applied}"
    )

    # Serialised here so the wire form is exercised by the command an operator runs, not only by a test -
    # `by_alias` and `mode="json"` are the two things a figure event can silently get wrong.
    logger.debug("figure event", extra={"event": serialise_event(event)})

    await writer(event)
