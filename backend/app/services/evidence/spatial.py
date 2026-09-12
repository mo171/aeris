"""Measures a mask the way a report will quote it - hectares, a share of what was observed, and how many regions.

what  : `MaskStatistics` and `measure_mask()`: the `geospatial-engine` model id's whole output for a
        raster mask - detected area, observed area, coverage, region count and density.
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
from dataclasses import dataclass

import numpy as np

from app.constants.geo import SQUARE_METRES_PER_SQUARE_KILOMETRE
from app.services.evidence.math.area import AreaMeasurement, RegionCount, count_regions, measure_area


@dataclass(frozen=True, slots=True)
class MaskStatistics:
    """Everything the geospatial engine can say about one mask on one grid."""

    detected: AreaMeasurement
    observed: AreaMeasurement
    regions: RegionCount

    @property
    def coverage_fraction(self) -> float:
        """Detected ground as a share of observed ground. Zero when nothing was observed."""
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
