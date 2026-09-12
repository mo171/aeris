"""Measures and gates temporal-image co-registration.

what  : Async registration measurement and a typed refusal for geometrically unsafe comparisons.
where : Stage S9 is called before change detection and later optical/SAR fusion.
how   : A high residual stops the comparison. It is not converted into a lower confidence because the
        underlying pixels may represent different places on the ground.
"""

import asyncio
from dataclasses import dataclass

import numpy as np

from app.constants.preprocessing import (
    COREGISTRATION_MINIMUM_VALID_TILES,
    COREGISTRATION_TILE_SIZE_PIXELS,
    MAXIMUM_COREGISTRATION_RESIDUAL_PIXELS,
)
from app.lib.exceptions import InvalidRequestError
from app.services.preprocessing.math.registration_residual import RegistrationMeasurement, measure_registration_residual


@dataclass(frozen=True, slots=True)
class CoregistrationResult:
    """The reported S9 measurement, including whether a temporal comparison may proceed."""

    measurement: RegistrationMeasurement
    tolerance_pixels: float

    @property
    def is_accepted(self) -> bool:
        """Whether local registration disagreement stays within the policy tolerance."""
        return self.measurement.residual_pixels <= self.tolerance_pixels


async def measure_coregistration(
    reference: np.ndarray,
    moving: np.ndarray,
    *,
    tile_size: int = COREGISTRATION_TILE_SIZE_PIXELS,
    minimum_valid_tiles: int = COREGISTRATION_MINIMUM_VALID_TILES,
    tolerance_pixels: float = MAXIMUM_COREGISTRATION_RESIDUAL_PIXELS,
) -> CoregistrationResult:
    """S9: report local registration residual without silently approving an unsafe pair."""
    measurement = await asyncio.to_thread(
        measure_registration_residual,
        reference,
        moving,
        tile_size=tile_size,
        minimum_valid_tiles=minimum_valid_tiles,
    )
    return CoregistrationResult(measurement, tolerance_pixels)


async def require_comparison_ready(result: CoregistrationResult) -> None:
    """Refuse temporal comparison when the measured residual exceeds the declared tolerance."""
    if not result.is_accepted:
        measurement = result.measurement
        raise InvalidRequestError(
            "Temporal comparison refused: co-registration residual exceeds the allowed tolerance.",
            details={
                "residualPixels": measurement.residual_pixels,
                "tolerancePixels": result.tolerance_pixels,
                "rowShiftPixels": measurement.row_shift_pixels,
                "columnShiftPixels": measurement.column_shift_pixels,
                "validTileCount": measurement.valid_tile_count,
            },
        )
