"""Works out where a raster sits in degrees and which web-map zooms can show it, so a tile layer never asks for tiles that do not exist.

what  : `geographic_bounds()` - a grid's extent in WGS 84; `zoom_range()` - the WebMercatorQuad zooms
        between "the whole raster fits one tile" and "one tile pixel is one raster pixel".
where : Called by `services/evidence/builder.py` (through `asyncio.to_thread`) for every raster layer it
        emits. `api-contract.md` §8 rule 4: send `bounds`, `minzoom`, `maxzoom`, or Cesium requests tiles
        across the whole planet and collects 404s.
how   : **Pure, sync; rasterio's `transform_bounds` and arithmetic.** WebMercatorQuad's ground resolution
        at zoom z is `156543.03 * cos(latitude) / 2**z` metres per tile pixel (the 256-pixel tile
        convention TiTiler follows). The maximum zoom is the first at which a tile pixel is at least as
        fine as a raster pixel; the minimum is the last at which the raster's extent fits in one tile.
        Checked against the 1.2 gate's TileJSON: a 10 m Sentinel-2 tile at 28 N gives 8 and 14, which is
        what TiTiler reported.
"""

import math

from rasterio.transform import Affine
from rasterio.warp import transform_bounds

WEB_MERCATOR_EQUATOR_RESOLUTION_METRES = 156_543.03392804097
WGS84_EQUATORIAL_RADIUS_METRES = 6_378_137.0
TILE_SIZE_PIXELS = 256

type AffineTransform = tuple[float, float, float, float, float, float]


def geographic_bounds(
    transform: AffineTransform, crs: str, shape: tuple[int, int]
) -> tuple[float, float, float, float]:
    """(west, south, east, north) in WGS 84, densified along the edges so a curved edge stays inside."""
    rows, columns = shape
    affine = Affine(*transform)
    x0, y0 = affine * (0, 0)
    x1, y1 = affine * (columns, rows)
    return transform_bounds(
        crs, "EPSG:4326", min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1), densify_pts=21
    )


def zoom_range(bounds: tuple[float, float, float, float], resolution_metres: float) -> tuple[int, int]:
    """(minimum_zoom, maximum_zoom) for a raster with this extent and ground sample distance."""
    west, south, east, north = bounds
    latitude = math.radians((south + north) / 2.0)
    ground_per_tile_pixel = WEB_MERCATOR_EQUATOR_RESOLUTION_METRES * math.cos(latitude)

    maximum = math.ceil(math.log2(ground_per_tile_pixel / resolution_metres))

    width_metres = math.radians(east - west) * WGS84_EQUATORIAL_RADIUS_METRES * math.cos(latitude)
    height_metres = math.radians(north - south) * WGS84_EQUATORIAL_RADIUS_METRES
    extent_metres = max(width_metres, height_metres)
    minimum = math.floor(math.log2(ground_per_tile_pixel * TILE_SIZE_PIXELS / extent_metres))

    return max(0, min(minimum, maximum)), max(0, maximum)
