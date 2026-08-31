"""Builds optical cloud and projected-shadow masks from s2cloudless probabilities.

what  : Mask thresholding and geometric cloud-shadow projection over arrays.
where : Called by ``cloud_masking.py`` after model inference or when probabilities are supplied by a scene.
how   : The kernels only know pixels and solar geometry. They preserve invalid pixels and never turn a
        cloud probability into a spectral value, keeping masking ahead of all later index arithmetic.
"""

import numpy as np
from scipy.ndimage import binary_dilation


def threshold_cloud_probability(probability: np.ndarray, threshold: float) -> np.ndarray:
    """Return a cloud mask; non-finite probabilities remain unobserved rather than becoming clear sky."""
    if probability.ndim != 2:
        raise ValueError(f"cloud probability must be two-dimensional, got {probability.shape}")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"cloud threshold must be in [0, 1], got {threshold}")
    if np.nanmin(probability) < 0.0 or np.nanmax(probability) > 1.0:
        raise ValueError("cloud probability must be in [0, 1]")
    return np.isfinite(probability) & (probability >= threshold)


def project_cloud_shadow(
    cloud_mask: np.ndarray,
    *,
    sun_azimuth_degrees: float,
    sun_elevation_degrees: float,
    cloud_height_metres: float,
    pixel_size_metres: float,
    dilation_pixels: int = 1,
) -> np.ndarray:
    """Project clouds away from the sun to produce a conservative shadow candidate mask."""
    if cloud_mask.ndim != 2:
        raise ValueError(f"cloud mask must be two-dimensional, got {cloud_mask.shape}")
    if not 0.0 < sun_elevation_degrees < 90.0:
        raise ValueError("sun elevation must be between 0 and 90 degrees")
    if cloud_height_metres <= 0.0 or pixel_size_metres <= 0.0:
        raise ValueError("cloud height and pixel size must be positive")
    if dilation_pixels < 0:
        raise ValueError("dilation pixels must not be negative")

    # Image rows grow south and columns east. A shadow points opposite the incoming solar azimuth.
    distance_pixels = cloud_height_metres / np.tan(np.deg2rad(sun_elevation_degrees)) / pixel_size_metres
    shadow_azimuth = np.deg2rad((sun_azimuth_degrees + 180.0) % 360.0)
    row_shift = int(np.rint(-np.cos(shadow_azimuth) * distance_pixels))
    column_shift = int(np.rint(np.sin(shadow_azimuth) * distance_pixels))

    source = binary_dilation(cloud_mask, iterations=dilation_pixels) if dilation_pixels else cloud_mask
    projected = np.zeros_like(cloud_mask, dtype=bool)
    source_rows, source_columns = np.nonzero(source)
    target_rows = source_rows + row_shift
    target_columns = source_columns + column_shift
    inside = (
        (target_rows >= 0)
        & (target_rows < cloud_mask.shape[0])
        & (target_columns >= 0)
        & (target_columns < cloud_mask.shape[1])
    )
    projected[target_rows[inside], target_columns[inside]] = True
    return projected & ~cloud_mask
