"""Turns a boolean mask into labelled regions and one polygon per region, so a claim can point at ground rather than at pixels.

what  : `label_regions()` - eight-connected components; `vectorise_regions()` - one shapely polygon per
        region in the raster's own CRS; `region_means()` - the mean of a value raster inside each region.
where : Called by `services/evidence/builder.py` through `asyncio.to_thread`, and `label_regions` is the
        one labelling every region count in the project uses (`evidence/math/area.py`).
how   : **Pure, sync; NumPy, SciPy, rasterio's `shapes`, shapely** (`architecture-context.md` §12). Knows a
        grid as six affine numbers. Does not know what a scene or a claim is.

        `architecture-context.md` invariant 14: every mask is produced in both representations. This is
        the vector half. Eight-connectivity throughout, because two pixels touching at a corner are one
        patch of ground to an operator, and because `rasterio.features.shapes` and `ndimage.label` must
        agree on what a region is or a polygon and its count will disagree.

        Polygons are in the raster's CRS, not WGS 84. Simplification (`evidence/math/simplification.py`)
        and area (`evidence/math/area.py`) both want projected metres; the ring is projected to degrees
        last, once, for the wire.
"""

from dataclasses import dataclass

import numpy as np
from rasterio.features import shapes
from rasterio.transform import Affine
from scipy import ndimage
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import unary_union

# Eight-connectivity: the structuring element that makes diagonal neighbours one region.
EIGHT_CONNECTED = np.ones((3, 3), dtype=int)

type AffineTransform = tuple[float, float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class Region:
    """One connected region of a mask: its label, its pixels, and its outline."""

    label: int
    pixel_count: int
    geometry: Polygon | MultiPolygon


def label_regions(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Integer labels 1..count over the `True` pixels of `mask`, eight-connected; 0 elsewhere."""
    labels, count = ndimage.label(mask, structure=EIGHT_CONNECTED)
    return labels.astype(np.int32, copy=False), int(count)


def vectorise_regions(labels: np.ndarray, transform: AffineTransform) -> list[Region]:
    """One polygon per label, in the raster's CRS. Holes are kept; the wire drops them later."""
    if labels.max(initial=0) == 0:
        return []
    affine = Affine(*transform)
    by_label: dict[int, list[Polygon]] = {}
    for geometry, value in shapes(labels, mask=labels > 0, connectivity=8, transform=affine):
        by_label.setdefault(int(value), []).append(shape(geometry))

    pixel_counts = np.bincount(labels.ravel())
    regions = []
    for label in sorted(by_label):
        pieces = by_label[label]
        geometry = pieces[0] if len(pieces) == 1 else unary_union(pieces)
        regions.append(Region(label=label, pixel_count=int(pixel_counts[label]), geometry=geometry))
    return regions


def region_means(labels: np.ndarray, values: np.ndarray, count: int) -> np.ndarray:
    """The mean of `values` inside each region 1..count, NaN-aware. Index 0 is the region's label minus one."""
    if count == 0:
        return np.zeros(0, dtype=np.float64)
    finite = np.where(np.isfinite(values), values, 0.0)
    sums = ndimage.sum_labels(finite, labels, index=np.arange(1, count + 1))
    counts = ndimage.sum_labels(np.isfinite(values).astype(np.float64), labels, index=np.arange(1, count + 1))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(counts > 0, sums / counts, np.nan)
