"""Runs cloud/shadow masking before optical arithmetic.

what  : Typed cloud-mask result plus s2cloudless inference, thresholding, and mask application.
where : Stage S7 feeds this result to spectral indices and renders its raster artefact in later graphs.
how   : The s2cloudless model is invoked here rather than approximated from visible bands. Masking converts
        cloud, shadow, and invalid observations to NaN before downstream math.
"""

import asyncio
from dataclasses import dataclass

import numpy as np

from app.constants.preprocessing import CLOUD_PROBABILITY_THRESHOLD
from app.services.preprocessing.math.cloud_probability import project_cloud_shadow, threshold_cloud_probability


@dataclass(frozen=True, slots=True)
class OpticalMaskResult:
    """Cloud and shadow masks plus the combined exclusion mask."""

    cloud_probability: np.ndarray
    cloud_mask: np.ndarray
    shadow_mask: np.ndarray

    @property
    def exclusion_mask(self) -> np.ndarray:
        """Pixels that later optical arithmetic must turn into nodata."""
        return self.cloud_mask | self.shadow_mask | ~np.isfinite(self.cloud_probability)

    @property
    def obscured_fraction(self) -> float:
        """The optical half of the frontend's `sensorRunSchema.obscuredFraction`.

        Counts pixels of *unknown* cloud state alongside cloud and shadow, because the field means "share
        of the area this sensor could not read at all" - and a pixel the detector could not judge is one
        the operator has not been shown, not one that was clear.
        """
        return float(self.exclusion_mask.mean())


async def build_optical_mask(
    cloud_probability: np.ndarray,
    *,
    sun_azimuth_degrees: float,
    sun_elevation_degrees: float,
    cloud_height_metres: float,
    pixel_size_metres: float,
    threshold: float = CLOUD_PROBABILITY_THRESHOLD,
) -> OpticalMaskResult:
    """S7: threshold cloud probability and project a conservative cloud-shadow mask."""
    cloud_mask = await asyncio.to_thread(threshold_cloud_probability, cloud_probability, threshold)
    shadow_mask = await asyncio.to_thread(
        project_cloud_shadow,
        cloud_mask,
        sun_azimuth_degrees=sun_azimuth_degrees,
        sun_elevation_degrees=sun_elevation_degrees,
        cloud_height_metres=cloud_height_metres,
        pixel_size_metres=pixel_size_metres,
    )
    return OpticalMaskResult(cloud_probability, cloud_mask, shadow_mask)


async def infer_s2cloudless_probability(sentinel2_bands: np.ndarray) -> np.ndarray:
    """Run s2cloudless over a ``(height, width, 10)`` Sentinel-2 reflectance cube.

    The package owns its model and band convention. Calling it with another band set is refused here instead
    of producing a plausible probability map from a mismatched spectral order.
    """
    if sentinel2_bands.ndim != 3 or sentinel2_bands.shape[-1] != 10:
        raise ValueError("s2cloudless requires a (height, width, 10) Sentinel-2 reflectance cube")
    return await asyncio.to_thread(_infer_s2cloudless_probability, sentinel2_bands)


def _infer_s2cloudless_probability(sentinel2_bands: np.ndarray) -> np.ndarray:
    """Blocking model boundary, called only through ``to_thread`` by the async service."""
    from s2cloudless import S2PixelCloudDetector

    # ``all_bands=False`` is s2cloudless's documented 10-band Sentinel-2 interface. ``True`` expects all
    # 13 product bands and would reject the validated cube at runtime.
    detector = S2PixelCloudDetector(all_bands=False, average_over=4, dilation_size=2)
    probabilities = detector.get_cloud_probability_maps(sentinel2_bands[np.newaxis, ...])[0]
    return probabilities.astype(np.float32, copy=False)


async def apply_optical_mask(values: np.ndarray, mask: OpticalMaskResult) -> np.ndarray:
    """Replace cloud, shadow, and unobserved pixels with NaN before any index formula runs."""
    if values.shape != mask.exclusion_mask.shape:
        raise ValueError("optical values and mask must share one grid")
    return await asyncio.to_thread(lambda: np.where(mask.exclusion_mask, np.nan, values).astype(np.float32))
