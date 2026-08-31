"""Contains pure grid checks for reprojection and resampling.

what  : Validation that array grids can be compared without implicit broadcasting or interpolation.
where : Used by preprocessing services before registration and SAR/optical fusion later in the pipeline.
how   : The functions never read rasters; rasterio I/O remains at the async service boundary.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GridDefinition:
    """The comparison-relevant identity of a raster grid."""

    width: int
    height: int
    crs: str
    transform: tuple[float, float, float, float, float, float]


def grids_match(left: GridDefinition, right: GridDefinition, *, tolerance: float = 1e-9) -> bool:
    """Whether two grids have the same dimensions, CRS, and affine transform within numeric tolerance."""
    if tolerance < 0.0:
        raise ValueError("grid tolerance cannot be negative")
    return (
        left.width == right.width
        and left.height == right.height
        and left.crs == right.crs
        and all(abs(first - second) <= tolerance for first, second in zip(left.transform, right.transform, strict=True))
    )
