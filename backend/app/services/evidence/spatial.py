"""Measures a mask the way a report will quote it - hectares, a share of what was observed, and how many regions.

what  : `MaskStatistics` and `measure_mask()`: the `geospatial-engine` model id's whole output for a
        raster mask - detected area, observed area, coverage, region count and density; and
        `measure_mask_nominal()`, the same over a picture at a declared pixel size (1.10).
where : S15. Called by `services/pipeline/nodes/evidence_localisation.py`; from 1.5 its numbers become
        claim metrics. The arithmetic is `math/area.py` and this file contains none of it.
how   : **Coverage is a share of the *observed* ground, not of the scene.** A scene that is 30% cloud
        has 70% of its ground in the denominator. Dividing by the whole grid would report a field under
        cloud as "not vegetated", which is the plausible wrong number §8 rule 1 exists to prevent - the
        same mask that kept those pixels out of the index keeps them out of the denominator here.

        The two areas are measured by the same function in the same projection, so the ratio between
        them is exact even where the projection's scale is not.
"""

import asyncio
import math
from dataclasses import dataclass

import numpy as np

from app.constants.geo import SQUARE_METRES_PER_SQUARE_KILOMETRE
from app.services.evidence.math.area import (
    AreaMeasurement,
    RegionCount,
    count_regions,
    measure_area,
    measure_area_nominal,
    measure_area_pixels,
)


@dataclass(frozen=True, slots=True)
class MaskStatistics:
    """Everything the geospatial engine can say about one mask on one grid."""

    detected: AreaMeasurement
    observed: AreaMeasurement
    regions: RegionCount

    @property
    def has_area(self) -> bool:
        """Whether the ground was measured at all. False for a picture with no grid and no declared pixel size."""
        return math.isfinite(self.detected.square_metres)

    @property
    def coverage_fraction(self) -> float:
        """Detected ground as a share of observed ground. Zero when nothing was observed. Over a picture
        with no ground size it is the share of pixels, which is the same ratio when the pixels are equal."""
        if not self.has_area:
            return self.detected.pixel_count / self.observed.pixel_count if self.observed.pixel_count else 0.0
        if self.observed.square_metres == 0.0:
            return 0.0
        return self.detected.square_metres / self.observed.square_metres

    @property
    def region_density_per_square_kilometre(self) -> float:
        if self.observed.square_metres == 0.0:
            return 0.0
        return self.regions.region_count / (self.observed.square_metres / SQUARE_METRES_PER_SQUARE_KILOMETRE)

    @property
    def equal_area_crs(self) -> str:
        return self.detected.equal_area_crs


async def measure_mask(
    detected: np.ndarray,
    observed: np.ndarray,
    *,
    transform: tuple[float, float, float, float, float, float],
    crs: str,
) -> MaskStatistics:
    """S15 measurement. `detected` must be a subset of `observed`; a detection over unobserved ground is
    a contradiction the caller made upstream, and it is refused rather than measured."""
    if detected.shape != observed.shape:
        raise ValueError(f"detected is {detected.shape} and observed is {observed.shape}; one grid only.")
    if bool(np.any(detected & ~observed)):
        raise ValueError("The mask detects pixels that were never observed. The index was not masked first.")

    detected_area, observed_area, regions = await asyncio.gather(
        asyncio.to_thread(measure_area, detected, transform=transform, crs=crs),
        asyncio.to_thread(measure_area, observed, transform=transform, crs=crs),
        asyncio.to_thread(count_regions, detected),
    )
    return MaskStatistics(detected=detected_area, observed=observed_area, regions=regions)


async def measure_mask_pixels(detected: np.ndarray, observed: np.ndarray) -> MaskStatistics:
    """S15 over a picture with no grid and no declared pixel size: counts, and no area at all."""
    if detected.shape != observed.shape:
        raise ValueError(f"detected is {detected.shape} and observed is {observed.shape}; one grid only.")
    if bool(np.any(detected & ~observed)):
        raise ValueError("The mask detects pixels that were never observed. The picture was not masked first.")
    regions = await asyncio.to_thread(count_regions, detected)
    return MaskStatistics(detected=measure_area_pixels(detected), observed=measure_area_pixels(observed), regions=regions)


async def measure_mask_nominal(detected: np.ndarray, observed: np.ndarray, *, resolution_metres: float) -> MaskStatistics:
    """S15 over a picture with no grid: the same statistics at a declared pixel size, labelled nominal.
    The same refusal as `measure_mask` - a detection over unobserved ground is a contradiction."""
    if detected.shape != observed.shape:
        raise ValueError(f"detected is {detected.shape} and observed is {observed.shape}; one grid only.")
    if bool(np.any(detected & ~observed)):
        raise ValueError("The mask detects pixels that were never observed. The picture was not masked first.")
    detected_area, observed_area, regions = await asyncio.gather(
        asyncio.to_thread(measure_area_nominal, detected, resolution_metres=resolution_metres),
        asyncio.to_thread(measure_area_nominal, observed, resolution_metres=resolution_metres),
        asyncio.to_thread(count_regions, detected),
    )
    return MaskStatistics(detected=detected_area, observed=observed_area, regions=regions)


async def measure_mask_on_grid(
    detected: np.ndarray,
    observed: np.ndarray,
    *,
    transform: tuple[float, float, float, float, float, float],
    crs: str | None,
    resolution_metres: float | None,
    resolution_declared: bool,
) -> MaskStatistics:
    """The one entry point S15 uses: geodetic hectares on a georeferenced grid, nominal hectares at a
    declared pixel size, pixels alone otherwise. The choice is the input's, never the caller's guess."""
    if crs is not None:
        return await measure_mask(detected, observed, transform=transform, crs=crs)
    if resolution_metres is not None and resolution_declared:
        return await measure_mask_nominal(detected, observed, resolution_metres=resolution_metres)
    return await measure_mask_pixels(detected, observed)
