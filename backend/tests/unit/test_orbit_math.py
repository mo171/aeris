"""Unit tests for Keplerian circular orbit ground-track propagation."""

from datetime import UTC, datetime, timedelta

from app.services.globe.math.orbit import (
    SENTINEL_CONSTELLATION,
    compute_ground_point,
    propagate_track,
)


def test_orbit_propagation_lat_lon_bounds():
    """Ensure computed sub-satellite positions stay within physical geographic bounds."""
    now = datetime(2026, 9, 18, 12, 0, 0, tzinfo=UTC)

    for params in SENTINEL_CONSTELLATION:
        # Sample across 2 hours in 5-minute increments
        for step_min in range(0, 120, 5):
            t = now + timedelta(minutes=step_min)
            lat, lon = compute_ground_point(params, t.timestamp())

            assert -params.inclination_deg <= lat <= params.inclination_deg, (
                f"Latitude {lat} out of inclination bounds {params.inclination_deg} for {params.platform}"
            )
            assert -180.0 <= lon <= 180.0, f"Longitude {lon} out of WGS84 range for {params.platform}"


def test_propagate_track_returns_valid_arc():
    """Ensure track propagation returns distinct origin, destination, and phase."""
    now = datetime(2026, 9, 18, 12, 0, 0, tzinfo=UTC)

    for params in SENTINEL_CONSTELLATION:
        origin, dest, phase = propagate_track(params, now, window_seconds=600.0)

        assert 0.0 <= phase <= 1.0, f"Phase {phase} out of [0, 1] range for {params.platform}"
        assert origin != dest, f"Origin and destination must differ for moving satellite {params.platform}"
