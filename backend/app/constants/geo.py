"""The coordinate reference systems this system stores in, measures in, and serves tiles in.

what  : `STORAGE_SRID`, `WEB_MERCATOR_SRID`, the geometry type names used by the schema, and the two
        constants that encode how an area is allowed to be measured.
where : Read by `app/db/models/` for every geometry column, by `app/lib/database.py`'s health probe, and
        later by `services/evidence/math/area.py`. Nothing computes an area without going through one of the
        two routes named here.
how   : **Geometry is stored in EPSG:4326 and measured somewhere else.** Storing in a projected CRS would
        force a reprojection on every read and would make a global catalogue impossible, since no projected
        CRS is valid worldwide. Measuring *in* 4326 is the error this module exists to prevent: degrees are
        not a unit of length, so `ST_Area` on a 4326 geometry returns square degrees - a number that looks
        like an answer and is not one (`architecture-context.md` §8 rule 3).

        There are two correct ways to get square metres, and which one applies depends on what is being
        measured:

        1. **Vector geometry in the database** - cast to `geography` and let PostGIS integrate on the WGS 84
           spheroid. Accurate anywhere on Earth, needs no projection choice, and is the only option that
           stays correct for a catalogue spanning multiple continents. This is what `AREA_MEASUREMENT_SQL`
           records, and it is the route the Phase 0.2 gate demonstrates.

        2. **Raster pixel counting in Python** (Phase 1.4 onward) - reproject the raster to a *local*
           equal-area projection centred on the scene, then count pixels and multiply by pixel area. A
           spheroidal integral is not available for a grid of pixels, and a global equal-area grid distorts
           shape badly enough at scene scale to bias which pixels fall inside a mask. `LOCAL_EQUAL_AREA_PROJ`
           is the template for that projection.

        Both produce square metres; `SQUARE_METRES_PER_HECTARE` is the only place the conversion is written.
"""

from typing import Final

# --- Storage and display -------------------------------------------------------------------------------

# WGS 84 lat/lon. Every geometry column in `app/db/models/` uses this, and every geometry on the wire is in
# it - the frontend's `geoPointSchema` and `geoBoundingBoxSchema` are latitude/longitude degrees.
STORAGE_SRID: Final[int] = 4326

# WebMercatorQuad, the tiling scheme TiTiler serves by default and the one Cesium expects
# (`api-contract.md` §7 rule 1). Named here so that no service invents a different scheme; nothing in the
# database is stored in it.
WEB_MERCATOR_SRID: Final[int] = 3857

# --- Geometry types ------------------------------------------------------------------------------------

# Scene footprints, areas of interest and evidence outlines. `POLYGON` rather than `MULTIPOLYGON`: a scene
# footprint and an area of interest are each one connected region, and allowing a multipolygon here would
# let a disjoint "area of interest" through, whose centroid can fall outside the area it names.
POLYGON_GEOMETRY: Final[str] = "POLYGON"
POINT_GEOMETRY: Final[str] = "POINT"

# --- Measurement ---------------------------------------------------------------------------------------

SQUARE_METRES_PER_HECTARE: Final[float] = 10_000.0

# The only sanctioned way to measure a stored geometry's area in SQL. Written as a template so that the
# expression appears once: a second hand-written `ST_Area` somewhere in a repository is exactly how square
# degrees get into a report.
#
# `::geography` triggers PostGIS's spheroidal integration (`use_spheroid` defaults to true), which is why no
# projection is named. Verified in `tests/integration/test_postgis_round_trip.py` against areas computed by
# hand from the spherical excess formula.
AREA_MEASUREMENT_SQL: Final[str] = "ST_Area({column}::geography)"

# Template for the Phase 1.4+ raster route. Lambert Azimuthal Equal Area centred on the scene, which is what
# makes it *local*: LAEA is exactly equal-area everywhere, and centring it on the data keeps linear
# distortion small enough that pixel-boundary decisions are not biased. A global equal-area grid such as
# EPSG:6933 would also conserve area but shears mid-latitude scenes noticeably, which changes which pixels a
# mask contains.
#
# Formatted with the scene centroid, then handed to pyproj. Not used yet - it is written here rather than in
# Phase 1.4 because it is the other half of the rule this module exists to state.
LOCAL_EQUAL_AREA_PROJ: Final[str] = (
    "+proj=laea +lat_0={latitude} +lon_0={longitude} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
)
