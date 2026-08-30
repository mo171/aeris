"""The Phase 0.2 gate: a polygon survives a round trip, and its area comes back in square metres, not degrees.

what  : Integration tests against a live PostGIS. Proves the extension is installed, that geometry stored in
        EPSG:4326 reads back unchanged, and that `AREA_MEASUREMENT_SQL` produces areas matching values
        computed by hand.
where : `tests/integration/`. Marked `integration`, so it needs `docker compose up -d` (or a Supabase
        `DATABASE_URL`). It is not skipped when infrastructure is missing - it fails, loudly, because it is
        the evidence for a Phase 0 gate and a silently skipped gate is an unproven one.
how   : **The expected areas are computed by hand, not recorded from a previous run** (`code-standards.md`
        §11). On a sphere, the area of a latitude/longitude box is exactly

            A = R^2 * dLongitude * (sin(lat_2) - sin(lat_1))          [radians]

        with R the WGS 84 authalic radius, 6_371_007.181 m - the sphere with the same surface area as the
        ellipsoid. PostGIS integrates on the ellipsoid itself rather than on that sphere, so the two differ
        slightly and in opposite directions with latitude: measured here, PostGIS reads 0.44% *low* at the
        equator and 0.57% *high* at 60 N, which is the ellipsoid's flattening showing up. The tolerance below
        is sized for that and nothing larger.

        The second test is the one worth having. It asserts the failure mode `architecture-context.md` §8
        rule 3 exists to prevent: two boxes of identical extent in degrees, one at the equator and one at
        60 N, have the *same* `ST_Area` in degrees and areas differing by a factor of two in reality. A
        system that measured in degrees would report them as equal, and would be wrong in a way that reads
        as a plausible number.
"""

import math

import pytest
from sqlalchemy import text

from app.constants.geo import AREA_MEASUREMENT_SQL, SQUARE_METRES_PER_HECTARE, STORAGE_SRID
from app.lib.database import check_health, get_session

pytestmark = pytest.mark.integration

# WGS 84 authalic radius: the sphere with the same surface area as the ellipsoid.
AUTHALIC_RADIUS_METRES = 6_371_007.181

# PostGIS integrates on the ellipsoid; the closed form above is spherical. Measured difference is 0.44% at
# the equator and 0.57% at 60 N, so 1% covers the spheroid gap with margin while still catching a wrong CRS,
# a wrong unit, or a degrees-based measurement - each of which is wrong by orders of magnitude, not by half a
# percent. A tolerance loose enough to hide a unit error would defeat the test.
AREA_TOLERANCE = 0.01


def spherical_box_area_square_metres(
    south_latitude: float,
    north_latitude: float,
    longitude_span_degrees: float,
) -> float:
    """Exact area of a latitude/longitude box on a sphere. The reference the database is checked against."""
    return (
        AUTHALIC_RADIUS_METRES**2
        * math.radians(longitude_span_degrees)
        * (math.sin(math.radians(north_latitude)) - math.sin(math.radians(south_latitude)))
    )


def box_well_known_text(west: float, south: float, east: float, north: float) -> str:
    """A closed polygon ring, in the winding order PostGIS expects."""
    return (
        f"POLYGON(({west} {south}, {east} {south}, {east} {north}, "
        f"{west} {north}, {west} {south}))"
    )


async def test_postgis_extension_is_installed() -> None:
    """The precondition for every geometry column. Reported by `aeris doctor` as its own row."""
    health = await check_health()
    assert health.is_reachable, f"Database unreachable: {health.failure_reason}"
    assert health.postgis_version is not None, health.failure_reason


async def test_polygon_survives_a_round_trip_unchanged() -> None:
    """Store a polygon in EPSG:4326 and read it back. Geometry and SRID must be identical.

    Compared with `ST_Equals` and an exact vertex check rather than by comparing well-known text. PostGIS
    normalises its text output - `77.0` comes back as `77` - so a string comparison would fail on a geometry
    that is unchanged, and would be asserting a formatting detail that is not part of any contract.
    """
    polygon = box_well_known_text(west=77.0, south=12.0, east=78.0, north=13.0)

    async with get_session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT "
                    "  ST_Equals(geometry, ST_GeomFromText(:wkt, :srid)) AS is_geometrically_equal, "
                    "  ST_SRID(geometry) AS srid, "
                    "  ST_NPoints(geometry) AS vertex_count, "
                    "  ST_XMin(geometry) AS west, ST_YMin(geometry) AS south, "
                    "  ST_XMax(geometry) AS east, ST_YMax(geometry) AS north "
                    "FROM (SELECT ST_GeomFromText(:wkt, :srid) AS geometry) AS stored"
                ),
                {"wkt": polygon, "srid": STORAGE_SRID},
            )
        ).one()

    assert row.is_geometrically_equal
    assert row.srid == STORAGE_SRID
    # Five vertices: four corners plus the closing repeat. A ring that lost its closure would still pass
    # ST_Equals against itself, so the count is checked separately.
    assert row.vertex_count == 5
    assert (row.west, row.south, row.east, row.north) == (77.0, 12.0, 78.0, 13.0)


async def test_area_is_measured_in_square_metres_against_a_hand_computed_value() -> None:
    """The gate. A one-degree box at the equator, measured through `AREA_MEASUREMENT_SQL`."""
    polygon = box_well_known_text(west=0.0, south=0.0, east=1.0, north=1.0)
    expected = spherical_box_area_square_metres(south_latitude=0.0, north_latitude=1.0, longitude_span_degrees=1.0)

    async with get_session() as session:
        measured = (
            await session.execute(
                text(f"SELECT {AREA_MEASUREMENT_SQL.format(column='geometry')} AS area "
                     "FROM (SELECT ST_GeomFromText(:wkt, :srid) AS geometry) AS stored"),
                {"wkt": polygon, "srid": STORAGE_SRID},
            )
        ).scalar_one()

    # ~12,364 km^2. If this comes back as roughly 1.0, the measurement is in square degrees.
    assert measured == pytest.approx(expected, rel=AREA_TOLERANCE), (
        f"Measured {measured:,.0f} m^2, expected about {expected:,.0f} m^2. "
        "A value near 1.0 means the area was computed in degrees rather than on the spheroid."
    )
    assert measured / SQUARE_METRES_PER_HECTARE == pytest.approx(expected / SQUARE_METRES_PER_HECTARE, rel=AREA_TOLERANCE)


async def test_degrees_are_not_an_area_unit() -> None:
    """Two boxes, identical in degrees, twice the area apart in reality.

    This is the failure this whole rule exists for. `ST_Area` on a 4326 geometry reports both as 1.0; the
    ground truth is ~12,364 km^2 at the equator and ~6,089 km^2 at 60 N. Hectares are quoted in reports, so
    a system that measured in degrees would publish the two as equal.
    """
    equatorial_box = box_well_known_text(west=0.0, south=0.0, east=1.0, north=1.0)
    high_latitude_box = box_well_known_text(west=0.0, south=60.0, east=1.0, north=61.0)

    async with get_session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT "
                    "  ST_Area(ST_GeomFromText(:equator, :srid)) AS equator_degrees, "
                    "  ST_Area(ST_GeomFromText(:high, :srid)) AS high_degrees, "
                    "  ST_Area(ST_GeomFromText(:equator, :srid)::geography) AS equator_metres, "
                    "  ST_Area(ST_GeomFromText(:high, :srid)::geography) AS high_metres"
                ),
                {"equator": equatorial_box, "high": high_latitude_box, "srid": STORAGE_SRID},
            )
        ).one()

    # Measured in degrees the two are indistinguishable.
    assert row.equator_degrees == pytest.approx(1.0)
    assert row.high_degrees == pytest.approx(1.0)

    # Measured properly they are not.
    assert row.equator_metres == pytest.approx(
        spherical_box_area_square_metres(0.0, 1.0, 1.0), rel=AREA_TOLERANCE
    )
    assert row.high_metres == pytest.approx(
        spherical_box_area_square_metres(60.0, 61.0, 1.0), rel=AREA_TOLERANCE
    )
    assert row.equator_metres / row.high_metres == pytest.approx(2.03, rel=0.02)
