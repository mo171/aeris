"""Computes the overlapping window grid a specialist model runs over, and the arithmetic that stitches its output back without seams.

what  : `TileWindow`, `plan_tile_grid()`, `blend_weights()` and `tile_count_for()`.
where : Called by `services/imagery/tiling.py` (S11) through `asyncio.to_thread`. Phase 1.6's specialists
        consume the grid this produces.
how   : **Pure, sync, and free of I/O** - `architecture-context.md` §12. It takes integers and returns
        integers; it never opens a raster. That is what makes the seam arithmetic below testable against
        hand-computed values rather than against whatever a GDAL read happened to return.

        **Why the tiles overlap, which is the whole reason this file is not a two-line range().** A
        convolutional model has a receptive field: near a window edge it is predicting from context that
        was cropped away, so those predictions are systematically worse. Tile without overlap and those
        errors land in a regular grid across the output - visible as seams in a change mask and countable
        as false positives, in a product whose entire claim is that its evidence is trustworthy.

        Overlapping fixes the prediction but creates a second problem: pixels covered by two tiles now have
        two answers. `blend_weights` is the resolution - a ramp that goes to zero at the tile edge, so a
        pixel's answer is weighted towards whichever tile saw it with the most context. Averaging the two
        equally would keep half of the edge error.

        **The last tile is shifted, not padded.** A 10980-pixel band tiled at 512 with 64 overlap does not
        divide evenly. Padding the remainder with zeros feeds a model a strip of fabricated black pixels
        and gets a prediction about them; shifting the final window back so it ends flush with the raster
        means every pixel is real and the only cost is that the last two tiles overlap more than the rest -
        which the blend already handles.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class TileWindow:
    """One window of the inference grid, in pixel coordinates of the source raster."""

    column_offset: int
    row_offset: int
    width: int
    height: int

    # Position in the grid, so a caller can reassemble without recomputing the layout.
    column_index: int
    row_index: int

    @property
    def column_end(self) -> int:
        return self.column_offset + self.width

    @property
    def row_end(self) -> int:
        return self.row_offset + self.height

    def as_slices(self) -> tuple[slice, slice]:
        """Row and column slices, in the order NumPy indexes a 2-D array.

        Rows first. Rasterio's `Window` takes (col_off, row_off) and NumPy takes [row, col], and swapping
        them produces a transposed read that is only obviously wrong on a non-square raster.
        """
        return (slice(self.row_offset, self.row_end), slice(self.column_offset, self.column_end))


def plan_tile_grid(
    *, width: int, height: int, tile_size: int, overlap: int
) -> list[TileWindow]:
    """The complete set of windows covering a raster, in row-major order.

    Every pixel of the source is covered by at least one window, and no window extends past the edge.
    Raises on arguments that cannot produce a valid grid rather than returning a grid that silently skips
    pixels - a partial cover is the failure that produces a change mask with a hole in it.
    """
    if tile_size <= 0:
        raise ValueError(f"tile_size must be positive, got {tile_size}")
    if overlap < 0:
        raise ValueError(f"overlap cannot be negative, got {overlap}")
    if overlap >= tile_size:
        # The step would be zero or negative and the grid would never advance. Caught here because the
        # symptom otherwise is an infinite loop rather than a wrong answer.
        raise ValueError(
            f"overlap ({overlap}) must be smaller than tile_size ({tile_size}), or the grid never advances."
        )

    column_offsets = _offsets_along(extent=width, tile_size=tile_size, overlap=overlap)
    row_offsets = _offsets_along(extent=height, tile_size=tile_size, overlap=overlap)

    return [
        TileWindow(
            column_offset=column_offset,
            row_offset=row_offset,
            width=min(tile_size, width),
            height=min(tile_size, height),
            column_index=column_index,
            row_index=row_index,
        )
        for row_index, row_offset in enumerate(row_offsets)
        for column_index, column_offset in enumerate(column_offsets)
    ]


def _offsets_along(*, extent: int, tile_size: int, overlap: int) -> list[int]:
    """Window start positions along one axis.

    The final offset is **shifted back** to end flush with the raster rather than being padded. See the
    module docstring: padding feeds a model fabricated pixels and asks it about them.
    """
    if extent <= tile_size:
        return [0]

    step = tile_size - overlap
    offsets = list(range(0, extent - tile_size + 1, step))

    last_covered = offsets[-1] + tile_size
    if last_covered < extent:
        offsets.append(extent - tile_size)

    return offsets


def tile_count_for(*, width: int, height: int, tile_size: int, overlap: int) -> int:
    """How many windows a raster would produce, without building them.

    Separate from `plan_tile_grid` because the answer is wanted before committing to the work - a caller
    deciding whether an inference run is minutes or hours should not have to materialise the grid to find
    out, and on a large scene the grid is thousands of objects.
    """
    columns = len(_offsets_along(extent=width, tile_size=tile_size, overlap=overlap))
    rows = len(_offsets_along(extent=height, tile_size=tile_size, overlap=overlap))
    return columns * rows


def blend_weights(*, tile_size: int, overlap: int) -> np.ndarray:
    """A 2-D weight surface that falls to near zero at the tile edge, for stitching overlapping predictions.

    **Why not average the overlaps equally.** The reason the tiles overlap at all is that predictions near
    an edge are made with cropped context and are worse. An equal average keeps half of that error; a ramp
    weights each pixel towards the tile that saw it with the most context, which is the tile whose centre
    it is nearer to.

    The ramp is linear over the overlap width and flat across the interior, and it never reaches exactly
    zero - a pixel with zero weight in every tile covering it would divide by zero during normalisation,
    and the caller would get NaN in a mask rather than a class.

    Returns `float32`: these multiply model output, which is float32, and a float64 weight surface would
    silently upcast every tile and double the memory of a stitch.
    """
    if overlap == 0:
        return np.ones((tile_size, tile_size), dtype=np.float32)

    ramp = np.ones(tile_size, dtype=np.float32)
    # `1 / (overlap + 1)` up to `overlap / (overlap + 1)`: strictly positive at the very edge, reaching 1
    # just inside the overlap band.
    edge = np.arange(1, overlap + 1, dtype=np.float32) / (overlap + 1)
    ramp[:overlap] = edge
    ramp[-overlap:] = edge[::-1]

    # Outer product: the 2-D weight is the product of the two 1-D ramps, so a corner - cropped on both
    # axes - is weighted lowest of all, which is correct.
    return np.outer(ramp, ramp).astype(np.float32)
