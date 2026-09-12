"""Reduces a region's outline to the vertices the ground actually has, and puts it in the degrees the wire carries.

what  : `simplify_outline()` - Douglas-Peucker with topology preserved; `outer_ring_geographic()` - the
        outer ring of a polygon as (longitude, latitude) pairs.
where : Called by `services/evidence/builder.py` through `asyncio.to_thread`, after vectorisation and
        before a feature is built. Tolerance comes from `constants/evidence.py`.
how   : **Pure, sync; shapely and pyproj.** A rasterised region's outline is a staircase with one vertex
        per pixel edge, and none of those corners are a property of the ground. Douglas-Peucker (1973)
        with `preserve_topology=True` removes vertices that sit within the tolerance of the line replacing
        them and never lets a ring cross itself, which a plain simplification can do on a thin region.

        Simplified in projected metres, then projected to degrees - in that order. A tolerance in degrees
        is a different distance at every latitude.

        Only the outer ring reaches the wire: `featureGeometrySchema` is a single ring. A region with a
        hole is drawn as its outline, which overstates its drawn extent and not its measured area - the
        area on the feature comes from the full geometry, holes and all.
"""

from pyproj import CRS, Transformer
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from app.constants.geo import GEOGRAPHIC_COORDINATE_DECIMALS


def simplify_outline(geometry: BaseGeometry, tolerance: float) -> BaseGeometry:
    """Douglas-Peucker in the geometry's own units, keeping the ring valid."""
    return geometry.simplify(tolerance, preserve_topology=True)


def outer_ring_geographic(geometry: BaseGeometry, *, crs: str) -> list[tuple[float, float]]:
    """The outer ring of the largest polygon, as (longitude, latitude) in WGS 84, closing point dropped.

    A MultiPolygon - one label that vectorised into several pieces - contributes its largest piece; the
    rest are inside its measured area and outside its drawn ring, which the caller's label should say.
    """
    polygon = geometry
    if isinstance(geometry, MultiPolygon):
        polygon = max(geometry.geoms, key=lambda piece: piece.area)
    if not isinstance(polygon, Polygon):
        raise ValueError(f"Expected a polygon outline, got {geometry.geom_type}.")

    to_geographic = Transformer.from_crs(CRS.from_user_input(crs), CRS.from_epsg(4326), always_xy=True)
    x, y = zip(*polygon.exterior.coords[:-1], strict=True)
    longitudes, latitudes = to_geographic.transform(x, y)
    return [
        (round(float(lon), GEOGRAPHIC_COORDINATE_DECIMALS), round(float(lat), GEOGRAPHIC_COORDINATE_DECIMALS))
        for lon, lat in zip(longitudes, latitudes, strict=True)
    ]
