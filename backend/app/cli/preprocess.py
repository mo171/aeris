"""Everything `aeris preprocess` does - demonstrate the Phase 1.3 gate on a real scene.

what  : `execute_coregister()` and `execute_sar()`.
where : Called from `cli/main.py`. Phase 1.8 calls the same `services/preprocessing/` functions from S7-S10
        nodes; nothing here is logic a route will not reuse.
how   : The 1.3 gate, exactly: *"residual measured on a known-good and a known-bad pair; the bad pair is
        refused with a stated reason. Layover/shadow masks are what let the system distinguish `radar saw
        nothing` from `radar could not see`, and that distinction is demonstrated."*

        The bad pair is built by warping a band locally rather than by shifting it globally, because a
        global shift is the case a residual trivially catches. A pair that is aligned on average and wrong
        in every tile is the one that reaches change detection and produces a confident wrong answer.

        The SAR half runs on a real Sentinel-1 RTC product against the real Copernicus DEM over the same
        ground, so the masks describe terrain that exists.
"""

import logging
from pathlib import Path

import numpy as np
import rasterio
from rich.console import Console
from rich.markup import escape
from scipy.ndimage import shift as shift_array

from app.cli.renderers.figure_writer import open_figure_writer
from app.constants.preprocessing import MAXIMUM_COREGISTRATION_RESIDUAL_PIXELS
from app.constants.scenes import Polarisation
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.lib.exceptions import InvalidRequestError
from app.services.preprocessing.coregistration import measure_coregistration, require_comparison_ready
from app.services.preprocessing.elevation import elevation_on_grid
from app.services.preprocessing.sar_calibration import preprocess_sar
from app.services.rendering.figures import render_sar_backscatter

logger = logging.getLogger(__name__)

KNOWN_SHIFT_PIXELS = (2.5, -1.25)
WARP_SHIFT_COLUMNS = 4.0
SAMPLE_EXTENT = 1024
DARK_TARGET_DECIBELS = -22.0

# Sentinel-1 IW mid-swath geometry. Real products carry these per-scene; the gate scene is a band extracted
# into a research directory and has lost its metadata, so they are stated rather than guessed (§8 rule 5).
INCIDENCE_ANGLE_DEGREES = 39.0
LOOK_AZIMUTH_DEGREES = 100.0

# Khumbu, Nepal. Layover and shadow need slopes steeper than the incidence angle, so they do not exist on
# flat ground - the local gate scene is coastal Mumbai with 91 m of relief and correctly produces neither.
# This is the steepest terrain on the planet, and a descending Sentinel-1 pass looks west-northwest across
# it (right-looking, heading about 190 deg).
RELIEF_AREA_NAME = "Khumbu, Nepal"
RELIEF_BBOX = (86.80, 27.90, 86.95, 28.05)
RELIEF_COLLECTION = "sentinel-1-rtc"
RELIEF_PERIOD = ("2023-01-01", "2023-03-31")
RELIEF_LOOK_AZIMUTH_DEGREES = 280.0


def _read(path: Path, extent: int | None = None) -> np.ndarray:
    with rasterio.open(path) as dataset:
        values = dataset.read(1).astype(np.float32)
        if dataset.nodata is not None:
            values[values == dataset.nodata] = np.nan
    return values[:extent, :extent] if extent else values


def _shift_carrying_nodata(values: np.ndarray, offset: tuple[float, float]) -> np.ndarray:
    """Translate an array by a sub-pixel amount, moving its nodata with it."""
    known = shift_array(np.isfinite(values).astype(np.float32), offset, order=1, cval=0.0)
    moved = shift_array(np.nan_to_num(values), offset, order=1, cval=0.0)
    return np.where(known > 0.999, moved, np.nan).astype(np.float32)


async def execute_coregister(scene_directory: Path, console: Console) -> bool:
    """S9: measure a known-good and a known-bad pair, and show the bad one refused."""
    reference_path = scene_directory / "s2_B04.tif"
    partner_path = scene_directory / "s2_B08.tif"
    if not reference_path.exists():
        console.print(f"[red]{escape(str(reference_path))} not found.[/red]")
        return False

    reference = _read(reference_path, SAMPLE_EXTENT)
    console.print(
        f"\n  reference {escape(reference_path.name)}  {reference.shape[1]}x{reference.shape[0]}"
        f"  nodata {100 * float(np.isnan(reference).mean()):.1f}%"
        f"  tolerance {MAXIMUM_COREGISTRATION_RESIDUAL_PIXELS} px\n"
    )

    good = _shift_carrying_nodata(reference, KNOWN_SHIFT_PIXELS)

    bad = reference.copy()
    half = bad.shape[0] // 2
    bad[:half] = _shift_carrying_nodata(reference[:half], (0.0, WARP_SHIFT_COLUMNS))
    bad[half:] = _shift_carrying_nodata(reference[half:], (0.0, -WARP_SHIFT_COLUMNS))

    accepted = await _report_pair(
        "known-good", f"one rigid translation of {KNOWN_SHIFT_PIXELS}", reference, good, console
    )
    refused = not await _report_pair(
        "known-bad", "opposite translations in each half", reference, bad, console
    )

    cross_band: bool | None = None
    if partner_path.exists():
        cross_band = await _report_pair(
            "real pair",
            f"{reference_path.name} against {partner_path.name}",
            reference,
            _read(partner_path, SAMPLE_EXTENT),
            console,
        )

    # No square brackets around the verdicts: rich reads them as style tags and prints nothing at all,
    # which is the same bug `aeris version` hit with `[local]`.
    verdicts = [
        f"good pair accepted: {'yes' if accepted else 'NO'}",
        f"bad pair refused: {'yes' if refused else 'NO'}",
    ]
    if cross_band is not None:
        verdicts.append(f"real pair accepted: {'yes' if cross_band else 'NO'}")
    console.print("\n  gate: " + "   ".join(verdicts))
    return accepted and refused and cross_band is not False


async def _report_pair(
    label: str, description: str, reference: np.ndarray, moving: np.ndarray, console: Console
) -> bool:
    """Measure one pair, print what was measured, and state the refusal when there is one."""
    result = await measure_coregistration(reference, moving)
    measurement = result.measurement
    console.print(
        f"  {label:11s} {description}\n"
        f"{'':14s}shift ({measurement.row_shift_pixels:+.2f}, {measurement.column_shift_pixels:+.2f}) px"
        f"   residual {measurement.residual_pixels:.4f} px"
        f"   {measurement.valid_tile_count} tiles"
    )
    try:
        await require_comparison_ready(result)
    except InvalidRequestError as refusal:
        console.print(f"[yellow]{'':14s}REFUSED - {escape(str(refusal))}[/yellow]")
        return False
    console.print(f"{'':14s}accepted")
    return True


async def execute_sar(scene_directory: Path, console: Console) -> bool:
    """S10: run the fixed SAR order over a real product and draw what radar could not see."""
    path = scene_directory / "s1_vv.tif"
    if not path.exists():
        console.print(f"[red]{escape(str(path))} not found.[/red]")
        return False

    observed = _read(path)
    with rasterio.open(path) as dataset:
        pixel_size = float(dataset.res[0])
        crs = str(dataset.crs)

    console.print(
        f"\n  {escape(path.name)}  {observed.shape[1]}x{observed.shape[0]}  {pixel_size:g} m  {crs}"
    )
    console.print("  fetching Copernicus DEM GLO-30 over the same ground ...")
    elevation = await elevation_on_grid(path)
    console.print(
        f"  elevation {np.nanmin(elevation):.0f} to {np.nanmax(elevation):.0f} m"
        f"   known {100 * float(np.isfinite(elevation).mean()):.1f}%"
    )

    result = await preprocess_sar(
        observed,
        elevation,
        polarisation=Polarisation.VV,
        # The product is Sentinel-1 RTC: already linear power. Calibrating again would square it.
        calibration_factor=None,
        incidence_angle_degrees=INCIDENCE_ANGLE_DEGREES,
        radar_azimuth_degrees=LOOK_AZIMUTH_DEGREES,
        pixel_size_metres=pixel_size,
    )

    console.print(
        f"\n  calibration   pass-through (product is already linear power)\n"
        f"  speckle       coefficient of variation {_variation(result.calibrated_power):.3f}"
        f" -> {_variation(result.filtered_power):.3f}\n"
        f"  terrain       local incidence {np.nanmin(result.local_incidence_degrees):.1f}"
        f" to {np.nanmax(result.local_incidence_degrees):.1f} deg"
        f"  (nominal {INCIDENCE_ANGLE_DEGREES:.0f} deg)"
    )

    decibels = result.backscatter_decibels
    dark = np.isfinite(decibels) & (decibels < DARK_TARGET_DECIBELS)
    console.print(
        f"\n  radar could not see   {100 * result.obscured_fraction:.2f}%"
        f"  (layover {100 * float(result.layover_mask.mean()):.2f}%,"
        f" shadow {100 * float(result.shadow_mask.mean()):.2f}%)\n"
        f"  radar saw nothing     {100 * float(dark.mean()):.2f}%"
        f"  (below {DARK_TARGET_DECIBELS:.0f} dB, and observed)"
    )

    run_id = new_identifier(IdentifierPrefix.RUN)
    async with open_figure_writer(run_id) as writer:
        figure = await render_sar_backscatter(
            decibels,
            run_id=run_id,
            trace_step_id=new_identifier(IdentifierPrefix.TRACE_STEP),
            title=f"{Polarisation.VV.value} backscatter",
            polarisation=Polarisation.VV,
            mask_applied=True,
            crs=crs,
            scene_ids=[path.stem],
        )
        await writer(figure.event)
        console.print(
            f"\n  {figure.event.kind.value:15s} {figure.event.width}x{figure.event.height}"
            f"  {len(figure.image_bytes) // 1024} KB"
            f"  ramp {figure.event.render_spec.color_ramp.value}"
            f"  stretch {figure.event.render_spec.stretch}"
        )
        for written in writer.written:
            console.print(f"  {escape(str(written))}")

    # Not `obscured > 0`: this scene is coastal and flat, so zero is the *correct* answer and an operator
    # needs it in order to read an absence as evidence rather than as a blind spot. What must be true is
    # that the terrain was actually used - a DEM that never reached the geometry leaves the local
    # incidence pinned at the nominal angle. `aeris preprocess relief` is where the masks fill in.
    local_incidence = result.local_incidence_degrees
    spread = float(np.nanmax(local_incidence) - np.nanmin(local_incidence))
    return spread > 1.0


async def execute_relief(console: Console) -> bool:
    """S10 over terrain steep enough to blind a radar - the half of the gate a flat scene cannot show.

    Windowed straight out of the Planetary Computer COG rather than downloaded: an IW scene is 27577 x
    21415, and the patch that matters is a thousandth of it.
    """
    from app.services.preprocessing.elevation import fetch_backscatter_window

    console.print(
        f"\n  {RELIEF_AREA_NAME}  {RELIEF_BBOX}\n"
        f"  searching {RELIEF_COLLECTION} {RELIEF_PERIOD[0]} to {RELIEF_PERIOD[1]} ..."
    )
    patch_path, scene_id = await fetch_backscatter_window(
        collection=RELIEF_COLLECTION,
        bounding_box=RELIEF_BBOX,
        period=RELIEF_PERIOD,
        polarisation=Polarisation.VV,
    )
    observed = _read(patch_path)
    with rasterio.open(patch_path) as dataset:
        pixel_size = float(dataset.res[0])
    console.print(f"  {escape(scene_id)}\n  window {observed.shape[1]}x{observed.shape[0]}  {pixel_size:g} m")

    elevation = await elevation_on_grid(patch_path)
    console.print(
        f"  elevation {np.nanmin(elevation):.0f} to {np.nanmax(elevation):.0f} m"
        f"   relief {np.nanmax(elevation) - np.nanmin(elevation):.0f} m"
    )

    results = []
    for azimuth in (RELIEF_LOOK_AZIMUTH_DEGREES, (RELIEF_LOOK_AZIMUTH_DEGREES + 180.0) % 360.0):
        result = await preprocess_sar(
            observed,
            elevation,
            polarisation=Polarisation.VV,
            calibration_factor=None,
            incidence_angle_degrees=INCIDENCE_ANGLE_DEGREES,
            radar_azimuth_degrees=azimuth,
            pixel_size_metres=pixel_size,
        )
        decibels = result.backscatter_decibels
        dark = float((np.isfinite(decibels) & (decibels < DARK_TARGET_DECIBELS)).mean())
        console.print(
            f"\n  look azimuth {azimuth:.0f} deg\n"
            f"    radar could not see   {100 * result.obscured_fraction:5.2f}%"
            f"   (layover {100 * float(result.layover_mask.mean()):.2f}%,"
            f" shadow {100 * float(result.shadow_mask.mean()):.2f}%)\n"
            f"    radar saw nothing     {100 * dark:5.2f}%"
            f"   (below {DARK_TARGET_DECIBELS:.0f} dB, and observed)"
        )
        results.append((result, dark))

    first, first_dark = results[0]
    second, _ = results[1]
    # Three claims, and all three are the point. The masks are non-empty over real relief; they are not
    # the same thing as low backscatter; and they move when the orbit does, because they are geometry
    # rather than a property of the ground.
    distinguishable = first.obscured_fraction > 0.0 and first.obscured_fraction > first_dark * 10
    direction_dependent = not np.array_equal(first.layover_mask, second.layover_mask)
    console.print(
        f"\n  gate: masks non-empty over relief: {'yes' if first.obscured_fraction > 0 else 'NO'}"
        f"   distinct from low backscatter: {'yes' if distinguishable else 'NO'}"
        f"   follows the look direction: {'yes' if direction_dependent else 'NO'}"
    )
    return distinguishable and direction_dependent


def _variation(values: np.ndarray) -> float:
    """Coefficient of variation over observed pixels - the scale-free measure of how speckled a field is."""
    finite = values[np.isfinite(values)]
    return float(finite.std() / finite.mean()) if finite.size else float("nan")
