"""Measures how much ground a mask covers - in hectares, from an equal-area projection, never from the raster's own units.

what  : `measure_area()` - pixel count, square metres and hectares of a boolean mask on a georeferenced
        grid; `polygon_area()` - the same measurement for a vector outline; `count_regions()` - how many
        connected regions the mask has; `local_equal_area_crs()` - the projection all three use;
        `measure_area_nominal()` - the one case with no projection: a picture whose pixel size the
        operator declared, labelled nominal so it is never quoted as a geodetic area.
where : Called by `services/evidence/spatial.py` through `asyncio.to_thread`. The number it returns is
        the one a report quotes, which is why it is the most carefully bounded function in Phase 1.4.
how   : **Pure, sync; NumPy, pyproj and SciPy** (`architecture-context.md` §12). Knows a grid as six
        affine numbers and a CRS string. Does not know what a scene is.

        `architecture-context.md` §8 rule 3: areas are computed in an equal-area projection, never from
        degrees. The obvious shortcut - `count * |pixel_width * pixel_height|` - is right only when the
        CRS is projected *and* its scale factor is exactly 1 at the scene, which it never is: UTM is 0.9996
        on its central meridian and above 1 at the zone edges, so pixel counting in UTM units is off by up
        to 0.1%, and in a geographic CRS it is off by ten orders of magnitude (degrees are not a length).
        Both are plausible-looking numbers.

        So every pixel's footprint is measured where area is conserved: its corners are projected into a
        Lambert Azimuthal Equal-Area CRS centred on the grid (`constants/geo.py`), and the shoelace formula
        gives the footprint's area there. The raster is never resampled - resampling a mask into another
        grid changes which pixels it contains, which is the one thing a measurement of that mask must not
        do.

        Measured per block rather than per pixel (`AREA_BLOCK_SIZE_PIXELS`), because projecting a hundred
        and twenty million corners for one number is a gigabyte of coordinates; the error the block
        introduces is stated with the constant and is orders of magnitude below what any claim reports.

        Verified against an independent method: `tests/unit/test_area_math.py` compares this function
        with pyproj's geodesic polygon area on the WGS 84 ellipsoid, which shares no code path with it.
"""

from dataclasses import dataclass

import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as transform_geometry

from app.constants.geo import AREA_BLOCK_SIZE_PIXELS, LOCAL_EQUAL_AREA_PROJ, SQUARE_METRES_PER_HECTARE
from app.services.segmentation.math.vectorize import label_regions

type AffineTransform = tuple[float, float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class AreaMeasurement:
    """How much ground a set of pixels covers, and where that was measured."""

    pixel_count: int
    square_metres: float
    equal_area_crs: str

    @property
    def hectares(self) -> float:
        return self.square_metres / SQUARE_METRES_PER_HECTARE


@dataclass(frozen=True, slots=True)
class RegionCount:
    """How many connected regions a mask has, and how large each one is in pixels."""

    region_count: int
    region_pixel_counts: tuple[int, ...]

    @property
    def largest_region_pixels(self) -> int:
        return max(self.region_pixel_counts, default=0)


def local_equal_area_crs(transform: AffineTransform, crs: str, shape: tuple[int, int]) -> str:
    """The LAEA projection centred on this grid's centre, as a PROJ string."""
    rows, columns = shape
    centre_x, centre_y = _grid_to_source(transform, np.array([columns / 2.0]), np.array([rows / 2.0]))
    to_geographic = Transformer.from_crs(CRS.from_user_input(crs), CRS.from_epsg(4326), always_xy=True)
    longitude, latitude = to_geographic.transform(centre_x, centre_y)
    return LOCAL_EQUAL_AREA_PROJ.format(latitude=float(latitude[0]), longitude=float(longitude[0]))


def measure_area(
    mask: np.ndarray,
    *,
    transform: AffineTransform,
    crs: str,
    block_size: int = AREA_BLOCK_SIZE_PIXELS,
) -> AreaMeasurement:
    """Square metres covered by the `True` pixels of `mask`, measured in a local equal-area projection."""
    if mask.ndim != 2 or mask.dtype != bool:
        raise ValueError(f"A mask is a 2-D boolean array; got {mask.ndim}-D {mask.dtype}.")

    rows, columns = mask.shape
    equal_area_crs = local_equal_area_crs(transform, crs, mask.shape)
    block_pixel_area = _block_pixel_areas(transform, crs, mask.shape, equal_area_crs, block_size)

    row_edges = np.arange(0, rows, block_size)
    column_edges = np.arange(0, columns, block_size)
    counts = np.add.reduceat(np.add.reduceat(mask, row_edges, axis=0), column_edges, axis=1)

    return AreaMeasurement(
        pixel_count=int(mask.sum()),
        square_metres=float((counts * block_pixel_area).sum()),
        equal_area_crs=equal_area_crs,
    )


def measure_area_nominal(mask: np.ndarray, *, resolution_metres: float) -> AreaMeasurement:
    """Square metres of the `True` pixels at a *declared* ground sample distance - a picture with no grid.

    Not a projection and not a measurement of the ground: `count * gsd^2`, which is exact for what it
    claims (the pixels) and only as true as the operator's declaration. The record says `nominal` so a
    report cannot quote it as a geodetic area.
    """
    if mask.ndim != 2 or mask.dtype != bool:
        raise ValueError(f"A mask is a 2-D boolean array; got {mask.ndim}-D {mask.dtype}.")
    if resolution_metres <= 0.0:
        raise ValueError("A declared ground sample distance must be positive metres per pixel.")
    count = int(mask.sum())
    return AreaMeasurement(pixel_count=count, square_metres=count * resolution_metres**2, equal_area_crs=nominal_crs_label(resolution_metres))


def measure_area_pixels(mask: np.ndarray) -> AreaMeasurement:
    """The count alone, with the area explicitly unknown (NaN): a picture with no grid and no declaration."""
    if mask.ndim != 2 or mask.dtype != bool:
        raise ValueError(f"A mask is a 2-D boolean array; got {mask.ndim}-D {mask.dtype}.")
    return AreaMeasurement(pixel_count=int(mask.sum()), square_metres=float("nan"), equal_area_crs=PIXELS_ONLY_LABEL)


PIXELS_ONLY_LABEL = "pixels"


def nominal_crs_label(resolution_metres: float) -> str:
    """What `equal_area_crs` says when no projection was used: the declaration the number rests on."""
    return f"nominal:{resolution_metres:g} m per pixel"


def count_regions(mask: np.ndarray) -> RegionCount:
    """Connected regions of the mask, eight-connected: two pixels touching at a corner are one region."""
    labels, count = label_regions(mask)
    sizes = np.bincount(labels.ravel(), minlength=count + 1)[1:]
    return RegionCount(region_count=count, region_pixel_counts=tuple(int(size) for size in sizes))


def polygon_area(geometry: BaseGeometry, *, crs: str, equal_area_crs: str) -> float:
    """Square metres of a geometry given in `crs`, measured in the equal-area projection the raster used.

    The same projection as `measure_area`, so a region's polygon and its pixel count agree to the straight-
    edge approximation of a 10 m pixel edge - which is nothing - rather than by a projection's worth.
    """
    to_equal_area = Transformer.from_crs(
        CRS.from_user_input(crs), CRS.from_proj4(equal_area_crs), always_xy=True
    )
    return float(transform_geometry(to_equal_area.transform, geometry).area)


def _block_pixel_areas(
    transform: AffineTransform,
    crs: str,
    shape: tuple[int, int],
    equal_area_crs: str,
    block_size: int,
) -> np.ndarray:
    """The area of one pixel inside each block, from the block's projected corners. Shape (blocks_down,
    blocks_across); the last row and column of blocks may be narrower than `block_size`."""
    rows, columns = shape
    row_edges = np.append(np.arange(0, rows, block_size), rows).astype(np.float64)
    column_edges = np.append(np.arange(0, columns, block_size), columns).astype(np.float64)
    column_grid, row_grid = np.meshgrid(column_edges, row_edges)

    source_x, source_y = _grid_to_source(transform, column_grid, row_grid)
    to_equal_area = Transformer.from_crs(
        CRS.from_user_input(crs), CRS.from_proj4(equal_area_crs), always_xy=True
    )
    x, y = to_equal_area.transform(source_x, source_y)

    # Shoelace over each block's four corners: top-left, top-right, bottom-right, bottom-left.
    x_tl, x_tr, x_br, x_bl = x[:-1, :-1], x[:-1, 1:], x[1:, 1:], x[1:, :-1]
    y_tl, y_tr, y_br, y_bl = y[:-1, :-1], y[:-1, 1:], y[1:, 1:], y[1:, :-1]
    block_area = 0.5 * np.abs(
        x_tl * y_tr - x_tr * y_tl + x_tr * y_br - x_br * y_tr + x_br * y_bl - x_bl * y_br + x_bl * y_tl - x_tl * y_bl
    )
    pixels_per_block = np.outer(np.diff(row_edges), np.diff(column_edges))
    return block_area / pixels_per_block


def _grid_to_source(
    transform: AffineTransform, column: np.ndarray, row: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Pixel-edge coordinates to the raster's CRS. `(a, b, c, d, e, f)` is rasterio's affine order."""
    a, b, c, d, e, f = transform
    return c + a * column + b * row, f + d * column + e * row
