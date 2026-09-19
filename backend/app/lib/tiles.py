"""Builds the URLs TiTiler answers, so no service or CLI spells the tiler's routes by hand.

what  : `tilejson_url()`, `viewer_url()` and `xyz_template()` for a COG in object storage.
where : Called by `cli/ingest.py` and by `services/evidence/builder.py` for every raster layer's
        `tileUrlTemplate`. The tiler itself is provisioned in `docker-compose.yml` (Phase 1.2).
how   : `api-contract.md` §8: XYZ in WebMercatorQuad, TiTiler's default and the only scheme Cesium is
        configured for. The `s3://` form of the object is what TiTiler opens through GDAL's `/vsis3/`
        driver with the credentials the compose file sets; an `http://` URL would bypass that and require
        a public bucket (`services/imagery/cog.py`, `CogResult.storage_uri`).

        Band selection and stretch stay server-side, as query parameters (`api-contract.md` §8 rule 5);
        the browser never does band math, so the template carries them.
"""

from urllib.parse import urlencode

from app.config import settings

TILE_MATRIX_SET = "WebMercatorQuad"


def tilejson_url(storage_uri: str) -> str:
    """The TileJSON document for a COG. Carries `bounds`, `minzoom` and `maxzoom` - the 1.2 gate."""
    return f"{settings.tile_server}/cog/{TILE_MATRIX_SET}/tilejson.json?{urlencode({'url': storage_uri})}"


def viewer_url(storage_uri: str) -> str:
    """TiTiler's built-in map viewer, for looking at a COG without writing a page."""
    return f"{settings.tile_server}/cog/viewer?{urlencode({'url': storage_uri})}"


def xyz_template(storage_uri: str, **rendering: str) -> str:
    """An XYZ template with `{z}`, `{x}` and `{y}` left for the client, plus server-side rendering options
    such as `rescale="0,1"` or `colormap_name`."""
    query = urlencode({"url": storage_uri, **rendering})
    return f"{settings.tile_server}/cog/tiles/{TILE_MATRIX_SET}/{{z}}/{{x}}/{{y}}.png?{query}"


def backend_tilejson_url(scene_id: str, preset: str | None = None, **rendering: str) -> str:
    """Backend proxy TileJSON endpoint: /api/v1/tiles/{scene_id}/tilejson.json."""
    query = {"preset": preset} if preset else {}
    for k, v in rendering.items():
        if v is not None:
            query[k] = str(v)
    qs = f"?{urlencode(query)}" if query else ""
    return f"/api/v1/tiles/{scene_id}/tilejson.json{qs}"


def backend_xyz_template(scene_id: str, preset: str | None = None, **rendering: str) -> str:
    """Backend proxy XYZ tile template: /api/v1/tiles/{scene_id}/{z}/{x}/{y}.png."""
    query = {"preset": preset} if preset else {}
    for k, v in rendering.items():
        if v is not None:
            query[k] = str(v)
    qs = f"?{urlencode(query)}" if query else ""
    return f"/api/v1/tiles/{scene_id}/{{z}}/{{x}}/{{y}}.png{qs}"

