"""Keplerian circular orbit ground-track propagation for Earth Observation constellations.

what  : Computes sub-satellite ground track positions and orbital phase for Sentinel-1 and Sentinel-2.
where : Called by globe_controller to supply physical orbital tracks to the Cesium 3D canvas.
how   : Pure numerical method. Uses nominal inclination, altitude, and mean motion to project
        sub-satellite latitude and longitude as a function of UTC epoch.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime

EARTH_ROTATION_RATE_DEG_PER_SEC = 360.0 / 86164.1  # Sidereal day rotation rate


@dataclass(frozen=True, slots=True)
class OrbitParameters:
    platform: str
    altitude_km: float
    inclination_deg: float
    period_seconds: float
    initial_raan_deg: float
    initial_phase_deg: float


SENTINEL_CONSTELLATION: tuple[OrbitParameters, ...] = (
    OrbitParameters(
        platform="Sentinel-2A",
        altitude_km=786.0,
        inclination_deg=98.62,
        period_seconds=6036.0,  # 100.6 min
        initial_raan_deg=45.0,
        initial_phase_deg=0.0,
    ),
    OrbitParameters(
        platform="Sentinel-2B",
        altitude_km=786.0,
        inclination_deg=98.62,
        period_seconds=6036.0,
        initial_raan_deg=45.0,
        initial_phase_deg=180.0,  # 180° phased opposite 2A in the same plane
    ),
    OrbitParameters(
        platform="Sentinel-1A",
        altitude_km=693.0,
        inclination_deg=98.18,
        period_seconds=5916.0,  # 98.6 min
        initial_raan_deg=120.0,
        initial_phase_deg=30.0,
    ),
    OrbitParameters(
        platform="Sentinel-1C",
        altitude_km=693.0,
        inclination_deg=98.18,
        period_seconds=5916.0,
        initial_raan_deg=120.0,
        initial_phase_deg=210.0,
    ),
)


def compute_ground_point(params: OrbitParameters, epoch_seconds: float) -> tuple[float, float]:
    """Compute sub-satellite (latitude, longitude) in degrees for a given UTC epoch timestamp."""
    inc_rad = math.radians(params.inclination_deg)
    mean_motion_deg_per_sec = 360.0 / params.period_seconds

    # Argument of latitude u(t)
    u_deg = (params.initial_phase_deg + mean_motion_deg_per_sec * epoch_seconds) % 360.0
    u_rad = math.radians(u_deg)

    # Sub-satellite latitude
    sin_lat = math.sin(inc_rad) * math.sin(u_rad)
    lat_deg = math.degrees(math.asin(max(-1.0, min(1.0, sin_lat))))

    # Longitude of ascending node accounting for Earth rotation
    raan_deg = (params.initial_raan_deg - EARTH_ROTATION_RATE_DEG_PER_SEC * epoch_seconds) % 360.0

    # In-plane longitude relative to node
    delta_lon_rad = math.atan2(math.cos(inc_rad) * math.sin(u_rad), math.cos(u_rad))
    lon_deg = (raan_deg + math.degrees(delta_lon_rad)) % 360.0
    if lon_deg > 180.0:
        lon_deg -= 360.0

    return round(lat_deg, 4), round(lon_deg, 4)


def propagate_track(
    params: OrbitParameters,
    epoch: datetime,
    window_seconds: float = 600.0,
) -> tuple[tuple[float, float], tuple[float, float], float]:
    """Calculate (origin_lat_lon, destination_lat_lon, phase) for a satellite track arc."""
    epoch_sec = epoch.timestamp()
    origin = compute_ground_point(params, epoch_sec - window_seconds)
    destination = compute_ground_point(params, epoch_sec + window_seconds)
    phase = round(((epoch_sec % params.period_seconds) / params.period_seconds), 3)

    return origin, destination, phase
