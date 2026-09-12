"""Fetches a DEM and puts it on a radar scene's own grid, because terrain geometry is what layover and shadow are made of.

what  : `elevation_on_grid()` - Copernicus DEM GLO-30 windowed, mosaicked and warped onto a reference
        raster - and `fetch_backscatter_window()`, the same windowed read pointed at a radar COG.
where : Called by `cli/preprocess.py` and, from Phase 1.8, by the S10 node before `terrain_flatten`.
how   : Async orchestration; the reads and the warp are blocking rasterio calls reached through
        `asyncio.to_thread`.

        Terrain correction without a DEM is not terrain correction. §8 rule 7 requires layover and shadow
        masks and both come from slope against the look geometry, so a synthetic surface would produce
        masks that are shaped like an answer and are about nothing.

        **Only the window covering the scene is read.** A GLO-30 tile is one degree square; a Sentinel-1
        subset is a hundredth of that, and pulling whole tiles over HTTP took long enough that the first
        run of the gate never returned. Reading windows rather than datasets is the same rule the raster
        engine already follows.

        Bilinear, because elevation is continuous (§8 rule 6). Nodata stays NaN, so unknown terrain gives
        an unknown mask rather than a flat one.
"""

import asyncio
import logging
from pathlib import Path

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds

from app.config import settings
from app.constants.scenes import Polarisation

logger = logging.getLogger(__name__)

ELEVATION_COLLECTION = "cop-dem-glo-30"

# Degrees of DEM read beyond the scene on every side. The gradient at the edge of the window needs a
# neighbour outside it, and a warp lands on pixel centres that may sit just past the bounds.
ELEVATION_MARGIN_DEGREES = 0.02


async def elevation_on_grid(reference_path: Path) -> np.ndarray:
    """Return elevation in metres, on the same grid and shape as `reference_path`."""
    return await asyncio.to_thread(_elevation_on_grid, reference_path)


def _elevation_on_grid(reference_path: Path) -> np.ndarray:
    with rasterio.open(reference_path) as reference:
        west, south, east, north = transform_bounds(reference.crs, "EPSG:4326", *reference.bounds)
        target_crs, target_transform = reference.crs, reference.transform
        shape = (reference.height, reference.width)

    bounds = (
        west - ELEVATION_MARGIN_DEGREES,
        south - ELEVATION_MARGIN_DEGREES,
        east + ELEVATION_MARGIN_DEGREES,
        north + ELEVATION_MARGIN_DEGREES,
    )
    client = pystac_client.Client.open(
        str(settings.stac_api_url), modifier=planetary_computer.sign_inplace
    )
    items = list(client.search(collections=[ELEVATION_COLLECTION], bbox=bounds).items())
    if not items:
        raise ValueError(f"no {ELEVATION_COLLECTION} coverage for {bounds}")

    destination = np.full(shape, np.nan, dtype=np.float32)
    used = 0
    for item in items:
        patch = _read_window(item.assets["data"].href, bounds)
        if patch is None:
            continue
        used += 1
        values, source_transform, source_crs, source_nodata = patch
        warped = np.full(shape, np.nan, dtype=np.float32)
        reproject(
            source=values,
            destination=warped,
            src_transform=source_transform,
            src_crs=source_crs,
            src_nodata=source_nodata,
            dst_transform=target_transform,
            dst_crs=target_crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
        # A later tile only fills what is still unknown, so an overlap is never two surfaces averaged.
        destination = np.where(np.isnan(destination), warped, destination)

    known = float(np.isfinite(destination).mean())
    logger.info(
        "elevation fetched",
        extra={"items": len(items), "tiles_used": used, "known_fraction": known},
    )
    if known == 0.0:
        raise ValueError(f"{ELEVATION_COLLECTION} returned no elevation over {bounds}")
    return destination


def _read_window(href: str, bounds: tuple[float, float, float, float]):
    """Read just the part of one DEM tile that overlaps `bounds`, or None when it does not overlap."""
    with rasterio.open(href) as tile:
        window = from_bounds(*bounds, transform=tile.transform).round_offsets().round_lengths()
        clipped = window.intersection(rasterio.windows.Window(0, 0, tile.width, tile.height))
        if clipped.width <= 0 or clipped.height <= 0:
            return None
        values = tile.read(1, window=clipped).astype(np.float32)
        return values, tile.window_transform(clipped), tile.crs, tile.nodata


async def fetch_backscatter_window(
    *,
    collection: str,
    bounding_box: tuple[float, float, float, float],
    period: tuple[str, str],
    polarisation: Polarisation,
) -> tuple[Path, str]:
    """Window one polarisation out of a remote radar scene and write it to a local GeoTIFF.

    An IW scene is 27577 x 21415 pixels and the area under discussion is a thousandth of it, so the whole
    product is never fetched. Returns the local path and the scene id it came from.
    """
    return await asyncio.to_thread(
        _fetch_backscatter_window, collection, bounding_box, period, polarisation
    )


def _fetch_backscatter_window(
    collection: str,
    bounding_box: tuple[float, float, float, float],
    period: tuple[str, str],
    polarisation: Polarisation,
) -> tuple[Path, str]:
    client = pystac_client.Client.open(
        str(settings.stac_api_url), modifier=planetary_computer.sign_inplace
    )
    items = list(
        client.search(
            collections=[collection], bbox=bounding_box, datetime=f"{period[0]}/{period[1]}"
        ).items()
    )
    if not items:
        raise ValueError(f"no {collection} scene over {bounding_box} in {period[0]}..{period[1]}")

    item = items[0]
    asset = polarisation.value.lower()
    if asset not in item.assets:
        raise ValueError(f"{item.id} has no {polarisation.value} asset; it carries {sorted(item.assets)}")

    destination = settings.cog_working_directory / f"{item.id}_{asset}_window.tif"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(item.assets[asset].href) as scene:
        window = (
            from_bounds(
                *transform_bounds("EPSG:4326", scene.crs, *bounding_box), transform=scene.transform
            )
            .round_offsets()
            .round_lengths()
        )
        values = scene.read(1, window=window)
        profile = scene.profile | {
            "driver": "GTiff",
            "count": 1,
            "height": int(window.height),
            "width": int(window.width),
            "transform": scene.window_transform(window),
        }
    with rasterio.open(destination, "w", **profile) as output:
        output.write(values, 1)

    logger.info(
        "backscatter window fetched",
        extra={"scene_id": item.id, "asset": asset, "shape": values.shape},
    )
    return destination, item.id
