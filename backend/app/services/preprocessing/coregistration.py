"""Measures and gates temporal-image co-registration.

what  : `CoregistrationResult`, `RegistrationVerdict`, `measure_coregistration()` and
        `require_comparison_ready()` - the S9 measurement and the typed refusal for geometrically unsafe
        comparisons.
where : Stage S9 (`pipeline/nodes/change_detection.py`) is called before change detection and, in 1.11,
        before optical/SAR fusion.
how   : A high residual stops the comparison. It is not converted into a lower confidence because the
        underlying pixels may represent different places on the ground.

        **The tolerance is a distance on the ground, expressed in pixels of the grid at hand** (1.10).
        `architecture-context.md` §8 rule 2 says a residual larger than the feature under discussion
        invalidates the comparison - a statement about metres, not pixels. 1.3 set the gate at half a
        Sentinel-2 pixel, 5 m; a 0.5 m aerial pair held to half of *its* pixel would be refused for a
        25 cm wobble under buildings 15 m across. So the ground tolerance is the constant and the pixel
        tolerance is derived from the input's resolution; a picture whose pixel size nobody declared
        keeps the pixel constant, because nothing else about it is known.

        **Two ways to be admitted, one way to be refused, and the record says which.**
        - `TILES`: the majority of tiles agree (median residual within tolerance) *and* the median shift
          is within tolerance. The residual catches a warp or a partial offset; the shift catches a pair
          consistently offset, which a change model reads as every edge having moved.
        - `GLOBAL`: the tiles do not agree - their content differs too much between the dates for local
          correlation to see geometry - but the whole-frame correlation finds a shift within tolerance
          and at least `COREGISTRATION_GLOBAL_QUORUM` of the tiles stand behind it. Measured on sixty
          LEVIR-CD pairs (registered by their authors; seasons and shadows differ): the tile majority
          admitted 14, the global route 32 more than that, and neither admitted one of forty pairs
          offset on purpose by 25-30 px.
        - Otherwise refused, with the residual, the shift, the tolerance in pixels and metres, and the
          share of tiles that agreed, so the operator reads whether the pair was misregistered or merely
          too changed to measure.
        - `DECLARED`: the operator has said the pair is co-registered (`--registered`) - a benchmark
          aligned by its authors, a pair orthorectified upstream. §8 rule 5's rule for the processing
          level and the pixel size applies: a human's statement is recorded as such, never a guess. The
          measurement is still made and recorded beside the declaration.

        **The tile is sized to the input.** 128 px gives enough texture to separate a translation from
        periodic ground on a Sentinel-2 subset; on a 256 px crop it gives four tiles and no majority to
        take a median over, so the tile shrinks until at least four tiles fit each way, never below 32.
"""

import asyncio
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from app.constants.preprocessing import (
    COREGISTRATION_GLOBAL_QUORUM,
    COREGISTRATION_MINIMUM_TILE_SIZE_PIXELS,
    COREGISTRATION_MINIMUM_TILES_PER_SIDE,
    COREGISTRATION_MINIMUM_VALID_TILES,
    COREGISTRATION_TILE_SIZE_PIXELS,
    MAXIMUM_COREGISTRATION_RESIDUAL_METRES,
    MAXIMUM_COREGISTRATION_RESIDUAL_PIXELS,
)
from app.lib.exceptions import InvalidRequestError
from app.services.preprocessing.math.registration_residual import (
    RegistrationMeasurement,
    global_translation,
    measure_registration_residual,
)


class RegistrationVerdict(StrEnum):
    """How the pair was admitted, or that it was not."""

    TILES = "tiles-agree"
    GLOBAL = "global-correlation"
    DECLARED = "declared-by-operator"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class CoregistrationResult:
    """The reported S9 measurement, including whether a temporal comparison may proceed."""

    measurement: RegistrationMeasurement
    tolerance_pixels: float
    # The tolerance as ground distance when the resolution was known; `None` when the pixel constant applied.
    tolerance_metres: float | None = None
    tile_size: int = COREGISTRATION_TILE_SIZE_PIXELS
    # The whole-frame translation, and the share of tiles within tolerance of it.
    global_shift_pixels: tuple[float, float] | None = None
    declared_registered: bool = False

    @property
    def agreeing_fraction(self) -> float:
        """Tiles within tolerance of the median translation."""
        return self.measurement.agreeing_fraction(self.tolerance_pixels)

    @property
    def global_shift_magnitude_pixels(self) -> float | None:
        return float(np.hypot(*self.global_shift_pixels)) if self.global_shift_pixels is not None else None

    @property
    def global_agreeing_fraction(self) -> float:
        return self.measurement.agreeing_fraction(self.tolerance_pixels, self.global_shift_pixels) if self.global_shift_pixels else 0.0

    @property
    def verdict(self) -> RegistrationVerdict:
        measured = self.measurement
        if measured.residual_pixels <= self.tolerance_pixels and measured.shift_magnitude_pixels <= self.tolerance_pixels:
            return RegistrationVerdict.TILES
        magnitude = self.global_shift_magnitude_pixels
        if magnitude is not None and magnitude <= self.tolerance_pixels and self.global_agreeing_fraction >= COREGISTRATION_GLOBAL_QUORUM:
            return RegistrationVerdict.GLOBAL
        if self.declared_registered:
            return RegistrationVerdict.DECLARED
        return RegistrationVerdict.REFUSED

    @property
    def is_accepted(self) -> bool:
        return self.verdict is not RegistrationVerdict.REFUSED

    def describe(self) -> str:
        """One line with every number the gate looked at."""
        measured = self.measurement
        ground = f" = {self.tolerance_metres:g} m" if self.tolerance_metres is not None else ""
        line = (
            f"residual {measured.residual_pixels:.2f} px, shift {measured.shift_magnitude_pixels:.2f} px "
            f"(tolerance {self.tolerance_pixels:.2f} px{ground}); {self.agreeing_fraction:.0%} of {measured.valid_tile_count} "
            f"{self.tile_size} px tiles agree"
        )
        if self.global_shift_pixels is not None:
            line += f"; whole-frame shift {self.global_shift_magnitude_pixels:.2f} px with {self.global_agreeing_fraction:.0%} of tiles behind it"
        return line + f": {self.verdict.value}"


def tolerance_for(resolution_metres: float | None) -> tuple[float, float | None]:
    """The pixel tolerance for this grid, and the ground tolerance it came from (or `None`)."""
    if resolution_metres is None or resolution_metres <= 0:
        return MAXIMUM_COREGISTRATION_RESIDUAL_PIXELS, None
    return MAXIMUM_COREGISTRATION_RESIDUAL_METRES / resolution_metres, MAXIMUM_COREGISTRATION_RESIDUAL_METRES


def tile_size_for(shape: tuple[int, ...], preferred: int = COREGISTRATION_TILE_SIZE_PIXELS) -> int:
    """The preferred tile, shrunk until at least the minimum number of tiles fits each way."""
    side = min(shape[0], shape[1])
    size = preferred
    while size > COREGISTRATION_MINIMUM_TILE_SIZE_PIXELS and side // size < COREGISTRATION_MINIMUM_TILES_PER_SIDE:
        size //= 2
    return max(size, COREGISTRATION_MINIMUM_TILE_SIZE_PIXELS)


async def measure_coregistration(
    reference: np.ndarray,
    moving: np.ndarray,
    *,
    resolution_metres: float | None = None,
    tile_size: int | None = None,
    minimum_valid_tiles: int = COREGISTRATION_MINIMUM_VALID_TILES,
    tolerance_pixels: float | None = None,
    declared_registered: bool = False,
) -> CoregistrationResult:
    """S9: report local registration residual without silently approving an unsafe pair.

    `resolution_metres` sets the tolerance from the ground constant; an explicit `tolerance_pixels`
    overrides it (tests pin the pixel form). `tile_size` defaults to the input-sized tile.
    """
    size = tile_size if tile_size is not None else tile_size_for(reference.shape)
    if tolerance_pixels is not None:
        tolerance, metres = tolerance_pixels, None
    else:
        tolerance, metres = tolerance_for(resolution_metres)
    measurement = await asyncio.to_thread(
        measure_registration_residual, reference, moving, tile_size=size, minimum_valid_tiles=minimum_valid_tiles,
    )
    try:
        whole = await asyncio.to_thread(global_translation, reference, moving)
    except ValueError:
        whole = None
    return CoregistrationResult(measurement, tolerance, metres, size, whole, declared_registered)


async def require_comparison_ready(result: CoregistrationResult) -> None:
    """Refuse temporal comparison when neither the tiles nor the whole frame vouch for the geometry."""
    if not result.is_accepted:
        measurement = result.measurement
        raise InvalidRequestError(
            "Temporal comparison refused: co-registration residual exceeds the allowed tolerance. "
            + result.describe()
            + ". Align the pair first, or say it is co-registered (--registered) if its source already did.",
            details={
                "residualPixels": measurement.residual_pixels,
                "shiftPixels": measurement.shift_magnitude_pixels,
                "tolerancePixels": result.tolerance_pixels,
                "toleranceMetres": result.tolerance_metres,
                "rowShiftPixels": measurement.row_shift_pixels,
                "columnShiftPixels": measurement.column_shift_pixels,
                "validTileCount": measurement.valid_tile_count,
                "agreeingFraction": result.agreeing_fraction,
                "globalShiftPixels": result.global_shift_magnitude_pixels,
                "globalAgreeingFraction": result.global_agreeing_fraction,
                "tileSize": result.tile_size,
            },
        )
