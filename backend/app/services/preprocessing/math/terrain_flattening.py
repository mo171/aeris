"""Computes terrain-flattened SAR power and the two masks that record where radar could not see at all.

what  : Local incidence angle from a DEM, a projected-area terrain correction, and separate layover and
        shadow masks.
where : Called after speckle filtering by ``sar_calibration.py``.
how   : **Pure, sync, NumPy only** - `architecture-context.md` §12. Layover and shadow are retained rather
        than folded into nodata, because "radar saw nothing" and "radar could not see" are different
        observations and §8 rule 7 turns on keeping them apart.

        THE SIGN CONVENTION IS THE WHOLE FILE. `radar_azimuth_degrees` is the *look* azimuth - the compass
        bearing the beam travels along - so the sensor sits behind that direction. Terrain rising back
        towards the sensor shortens the slant range and folds; terrain falling away steeply enough is
        never illuminated. Getting this backwards is invisible in a figure, because both cases produce a
        plausible mask over plausible ground, and it silently swaps the two states §8 rule 7 exists to
        distinguish. It was inverted once here and is now pinned by a test that names the compass
        direction rather than asserting that both masks are non-empty.

        Everything follows from the local incidence angle, theta_local = theta - alpha, where alpha is the
        terrain rise *towards* the sensor:

            layover   theta_local <= 0        the slope out-faces the beam and folds towards it
            shadow    theta_local >= 90 deg   the slope hides behind its own crest
            correction = cos(theta) / cos(theta_local)

        That correction is exactly 1 on flat ground, which is the property that makes it a correction. The
        previous form, cos(alpha) / cos(theta), multiplied every flat pixel by 1.22 at a 35 deg incidence -
        a gain wearing a correction's name, and the kind of confident wrong number §8 opens by warning about.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class TerrainCorrectionResult:
    """Terrain-corrected power, the geometry it was derived from, and the visibility masks."""

    corrected_power: np.ndarray
    layover_mask: np.ndarray
    shadow_mask: np.ndarray

    # Kept because it is the quantity every decision above was made from. A mask alone cannot be argued
    # with; the angle that produced it can, and the frontend already declares `incidenceAngleDegrees`.
    local_incidence_degrees: np.ndarray

    @property
    def obscured_mask(self) -> np.ndarray:
        """Ground the radar could not read at all, for either geometric reason."""
        return self.layover_mask | self.shadow_mask

    @property
    def obscured_fraction(self) -> float:
        """Share of the scene radar could not see - the radar half of `sensorRunSchema.obscuredFraction`."""
        return float(self.obscured_mask.mean())


def terrain_flatten(
    power: np.ndarray,
    elevation_metres: np.ndarray,
    *,
    incidence_angle_degrees: float,
    radar_azimuth_degrees: float,
    pixel_size_metres: float,
    epsilon: float,
) -> TerrainCorrectionResult:
    """Correct SAR power for the slope-induced change in illuminated area, and mark what radar cannot see."""
    if power.shape != elevation_metres.shape or power.ndim != 2:
        raise ValueError("power and elevation must be same-shaped two-dimensional arrays")
    if not 0.0 < incidence_angle_degrees < 90.0 or pixel_size_metres <= 0.0 or epsilon <= 0.0:
        raise ValueError("incidence angle, pixel size, and epsilon must be positive and physically valid")

    elevation = elevation_metres.astype(np.float64, copy=False)

    # `np.gradient` returns the rise per metre along rows (increasing row = southward) and along columns
    # (increasing column = eastward).
    rise_southward, rise_eastward = np.gradient(elevation, pixel_size_metres, pixel_size_metres)

    # The unit vector the beam travels along, in the same row/column frame. Azimuth is clockwise from
    # north, so due north (0 deg) travels towards decreasing rows and due east (90 deg) towards increasing
    # columns.
    azimuth = np.deg2rad(radar_azimuth_degrees)
    beam_row_component = -np.cos(azimuth)
    beam_column_component = np.sin(azimuth)

    # Rise measured *against* the beam is rise back towards the sensor, so this is negated relative to the
    # slope along the look direction. This minus sign is the one the file docstring is about.
    rise_towards_sensor = -(rise_southward * beam_row_component + rise_eastward * beam_column_component)
    slope_towards_sensor = np.arctan(rise_towards_sensor)

    incidence = np.deg2rad(incidence_angle_degrees)
    local_incidence = incidence - slope_towards_sensor

    known = np.isfinite(elevation)
    layover = known & (local_incidence <= 0.0)
    shadow = known & (local_incidence >= np.pi / 2.0)
    observable = np.isfinite(power) & known & ~layover & ~shadow

    # cos(theta_local) is strictly positive wherever the pixel is observable; the clamp only guards the
    # boundary, where the pixel is already masked and the value is discarded.
    correction = np.cos(incidence) / np.maximum(np.cos(local_incidence), epsilon)
    corrected = np.where(observable, power * correction, np.nan)

    return TerrainCorrectionResult(
        corrected_power=corrected.astype(np.float32),
        layover_mask=layover,
        shadow_mask=shadow,
        local_incidence_degrees=np.degrees(local_incidence).astype(np.float32),
    )
