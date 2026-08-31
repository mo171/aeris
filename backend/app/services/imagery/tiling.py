"""Reads a large raster as the overlapping windows a specialist model can actually run on, and stitches its output back seamlessly.

what  : `TilePlan`, `plan_tiles()`, `read_tile()` and `stitch_predictions()`. Stage S11.
where : Called by Phase 1.6's specialists, which cannot take a 10980x10980 scene as one input. `aeris
        ingest --plan-tiles` reports the grid without reading anything.
how   : A change-detection or segmentation model takes a fixed input size - 512 is what most of the PDF's
        table were trained at. A Sentinel-2 scene is 10980 on a side, so it has to be windowed, and the
        two decisions that make windowing correct rather than merely possible both live here.

        **The windows overlap, and the overlap is the point.** A convolutional model has a receptive
        field: near a window edge it predicts from context that was cropped away, so those predictions are
        systematically worse. Tile without overlap and those errors land in a regular grid across the
        output - visible as seams in a change mask, and countable as false positives in a system whose
        whole claim is that its evidence is trustworthy.

        **Stitching is weighted, not averaged.** Overlapping means a pixel has two predictions; averaging
        them equally keeps half the edge error the overlap existed to remove. `blend_weights` ramps to
        near zero at the tile edge, so each pixel is weighted towards whichever tile saw it with the most
        context.

        The grid arithmetic is in `math/windowing.py` - pure, sync, testable against hand-computed values.
        This module does the I/O and nothing else, which is the `architecture-context.md` §12 split.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from app.constants.raster import INFERENCE_TILE_OVERLAP, INFERENCE_TILE_SIZE
from app.lib.exceptions import InternalError
from app.services.imagery.math.windowing import (
    TileWindow,
    blend_weights,
    plan_tile_grid,
    tile_count_for,
)
from app.services.imagery.metadata import RasterMetadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TilePlan:
    """The complete window grid for one raster, plus what it will cost to run."""

    metadata: RasterMetadata
    tile_size: int
    overlap: int
    windows: list[TileWindow]

    @property
    def tile_count(self) -> int:
        return len(self.windows)

    @property
    def redundancy(self) -> float:
        """How many times the average pixel is read, because of overlap.

        Worth reporting rather than hiding: at 512/64 it is about 1.3, and an operator deciding whether an
        inference run is minutes or hours is deciding about `tile_count`, not about pixels.
        """
        if self.metadata.pixel_count == 0:
            return 0.0
        return (self.tile_count * self.tile_size * self.tile_size) / self.metadata.pixel_count


def plan_tiles(
    metadata: RasterMetadata,
    *,
    tile_size: int = INFERENCE_TILE_SIZE,
    overlap: int = INFERENCE_TILE_OVERLAP,
) -> TilePlan:
    """Lay out the window grid for a raster. Reads nothing.

    Sync, and cheap: it is integer arithmetic over the raster's dimensions, which `inspect_raster` already
    established. Separating the plan from the reading is what lets a caller ask "how many tiles is this"
    before committing to hours of GPU time.
    """
    windows = plan_tile_grid(
        width=metadata.width, height=metadata.height, tile_size=tile_size, overlap=overlap
    )
    plan = TilePlan(metadata=metadata, tile_size=tile_size, overlap=overlap, windows=windows)

    logger.info(
        "tile grid planned",
        extra={
            "path": str(metadata.path), "tiles": plan.tile_count,
            "tile_size": tile_size, "overlap": overlap, "redundancy": round(plan.redundancy, 2),
        },
    )
    return plan


def estimate_tile_count(metadata: RasterMetadata, *, tile_size: int, overlap: int) -> int:
    """How many tiles a raster would produce, without building the grid.

    On a large scene the grid is thousands of objects, and the question "is this affordable" should not
    cost that.
    """
    return tile_count_for(
        width=metadata.width, height=metadata.height, tile_size=tile_size, overlap=overlap
    )


async def read_tile(path: Path, window: TileWindow, *, band_index: int = 1) -> np.ndarray:
    """Read one window's pixels.

    One window per call rather than a batch, because the caller is feeding a model that takes one input at
    a time and holding N tiles of a scene in memory is how a 512-tile plan becomes 4 GB. rasterio's own
    read is sync, so it is offloaded here.
    """
    return await asyncio.to_thread(_read_window, path, window, band_index)


def _read_window(path: Path, window: TileWindow, band_index: int) -> np.ndarray:
    """Sync read of one window. `boundless=False` - every window is inside the raster by construction."""
    with rasterio.open(path) as source:
        return source.read(
            band_index,
            window=Window(window.column_offset, window.row_offset, window.width, window.height),
        )


def stitch_predictions(
    plan: TilePlan, predictions: list[np.ndarray], *, dtype: str = "float32"
) -> np.ndarray:
    """Reassemble per-tile model output into one array covering the whole raster.

    **Weighted by distance from the tile edge, not averaged.** The tiles overlap because predictions near
    an edge are made with cropped context and are worse; averaging the two answers for an overlapping
    pixel keeps half of that error, which is the seam the overlap existed to remove.

    Sync, and deliberately: it is NumPy over arrays already in memory, and `code-standards.md` §7 asks for
    async where there is I/O. A caller running this on a large scene offloads it with `to_thread` at the
    call site, where the cost is visible.

    Returns NaN where no tile covered a pixel. That cannot happen for a grid built by `plan_tile_grid` -
    which covers every pixel by construction - so a NaN here means the caller passed a grid this plan did
    not produce, and NaN says so rather than a plausible zero.
    """
    if len(predictions) != plan.tile_count:
        raise InternalError(
            f"Stitching {len(predictions)} predictions into a {plan.tile_count}-tile grid. "
            "Every window must have exactly one prediction, in the order the plan lists them.",
            details={"expected": plan.tile_count, "received": len(predictions)},
        )

    height, width = plan.metadata.height, plan.metadata.width
    accumulated = np.zeros((height, width), dtype=np.float64)
    weight_total = np.zeros((height, width), dtype=np.float64)
    weights = blend_weights(tile_size=plan.tile_size, overlap=plan.overlap)

    for window, prediction in zip(plan.windows, predictions, strict=True):
        if prediction.shape != (window.height, window.width):
            raise InternalError(
                f"Prediction for tile ({window.row_index}, {window.column_index}) is "
                f"{prediction.shape}, but its window is {(window.height, window.width)}.",
                details={"tile": [window.row_index, window.column_index]},
            )
        rows, columns = window.as_slices()
        tile_weights = weights[: window.height, : window.width]
        accumulated[rows, columns] += prediction.astype(np.float64, copy=False) * tile_weights
        weight_total[rows, columns] += tile_weights

    with np.errstate(invalid="ignore", divide="ignore"):
        stitched = np.where(weight_total > 0, accumulated / weight_total, np.nan)

    return stitched.astype(dtype)
