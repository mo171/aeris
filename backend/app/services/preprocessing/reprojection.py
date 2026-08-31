"""Reprojects rasters onto an explicitly selected analysis grid.

what  : `reproject_to_reference_grid`, the S8 file-level alignment operation.
where : Called before co-registration whenever two scenes do not already share a CRS, transform, and shape.
how   : Raster I/O is isolated in a blocking helper reached through ``asyncio.to_thread``. Continuous
        measurements use bilinear interpolation; categorical masks use nearest neighbour, never averaging.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

from app.lib.exceptions import InvalidRequestError
from app.services.preprocessing.math.grid_alignment import GridDefinition, grids_match


@dataclass(frozen=True, slots=True)
class ReprojectionResult:
    """The destination and its grid identity, suitable for a later comparison check."""

    path: Path
    grid: GridDefinition
    resampling: str


async def reproject_to_reference_grid(
    source_path: Path,
    reference_path: Path,
    destination_path: Path,
    *,
    categorical: bool = False,
) -> ReprojectionResult:
    """S8: write source pixels on the reference grid with the only valid resampling mode for their type."""
    return await asyncio.to_thread(
        _reproject_to_reference_grid,
        source_path,
        reference_path,
        destination_path,
        categorical,
    )


def _reproject_to_reference_grid(
    source_path: Path,
    reference_path: Path,
    destination_path: Path,
    categorical: bool,
) -> ReprojectionResult:
    """Blocking rasterio boundary. Sync because it is called only through ``to_thread`` above."""
    with rasterio.open(reference_path) as reference, rasterio.open(source_path) as source:
        if source.crs is None or reference.crs is None:
            raise ValueError("source and reference rasters need a CRS before reprojection")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        profile = reference.profile.copy()
        profile.update(count=source.count, dtype=source.dtypes[0], nodata=source.nodata)
        method = Resampling.nearest if categorical else Resampling.bilinear
        with rasterio.open(destination_path, "w", **profile) as destination:
            for band_index in range(1, source.count + 1):
                reproject(
                    source=rasterio.band(source, band_index),
                    destination=rasterio.band(destination, band_index),
                    src_transform=source.transform,
                    src_crs=source.crs,
                    src_nodata=source.nodata,
                    dst_transform=reference.transform,
                    dst_crs=reference.crs,
                    dst_nodata=source.nodata,
                    resampling=method,
                )
        grid = _grid_from_dataset(reference)
    return ReprojectionResult(destination_path, grid, method.name)


def _grid_from_dataset(dataset: rasterio.DatasetReader) -> GridDefinition:
    """Read only the grid identity required to reject implicit comparisons."""
    if dataset.crs is None:
        raise ValueError("a comparison grid requires a CRS")
    transform = dataset.transform
    return GridDefinition(
        width=dataset.width,
        height=dataset.height,
        crs=str(dataset.crs),
        transform=(transform.a, transform.b, transform.c, transform.d, transform.e, transform.f),
    )


async def require_matching_grids(left: GridDefinition, right: GridDefinition) -> None:
    """Refuse a comparison that has not been explicitly aligned to one grid.

    The same refusal type as `coregistration.require_comparison_ready`, because it is the same kind of
    refusal: two rasters compared by index rather than by ground.
    """
    if not grids_match(left, right):
        raise InvalidRequestError(
            "Comparison refused: the two rasters are not on one grid.",
            details={
                "left": {"width": left.width, "height": left.height, "crs": left.crs,
                         "transform": list(left.transform)},
                "right": {"width": right.width, "height": right.height, "crs": right.crs,
                          "transform": list(right.transform)},
            },
        )
