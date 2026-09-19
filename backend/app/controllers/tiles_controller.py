"""Controller for TiTiler raster tile proxy, TileJSON metadata, and preview generation (Phase 2.6).

what  : `get_scene_tilejson`, `render_scene_tile`, and `get_scene_preview`.
where : Called by `app/routes/tiles.py`. Sits between FastAPI and the `titiler` container.
how   : Conforms to `api-contract.md` §8:
        1. Tiles are in EPSG:3857 (WebMercatorQuad).
        2. Tiles are PNG with alpha channel so nodata is transparent.
        3. TileJSON carries `bounds`, `minzoom`, and `maxzoom` so Cesium does not request 404s.
        4. Band selection, contrast stretching, and colormaps remain server-side.
        5. Internal `s3://` storage paths are never leaked to browser clients.
"""

from collections.abc import AsyncIterator
import logging
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select

from app.config import settings
from app.constants.geo import STORAGE_SRID
from app.constants.presets import BandPreset, resolve_preset_rendering
from app.constants.storage import Bucket
from app.db.models.scene import Scene
from app.lib import database
from app.lib.exceptions import InvalidRequestError, ResourceNotFoundError, UpstreamUnavailableError

logger = logging.getLogger(__name__)

TILE_MATRIX_SET = "WebMercatorQuad"
_HTTP_CLIENT: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Return reusable httpx async client for TiTiler proxy requests."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.AsyncClient(timeout=15.0)
    return _HTTP_CLIENT


def _format_titiler_params(params: dict[str, Any]) -> dict[str, Any]:
    """Format query parameters for TiTiler API.

    TiTiler's FastAPI routes declare sequence fields such as `bidx` as `list[int] = Query(None)`.
    FastAPI expects repeated query parameters (`?bidx=4&bidx=3&bidx=2`) rather than comma-separated
    strings (`?bidx=4,3,2`), which trigger a 422 integer parsing failure. Converting comma-separated
    `bidx` into a list allows httpx to encode it as repeated query parameters natively.
    """
    formatted: dict[str, Any] = {}
    for k, v in params.items():
        if v is None:
            continue
        if k == "bidx" and isinstance(v, str) and "," in v:
            formatted[k] = [x.strip() for x in v.split(",") if x.strip()]
        else:
            formatted[k] = v
    return formatted


async def _resolve_scene_storage_uri(scene_id: str) -> tuple[Scene, str]:
    """Retrieve scene from database and resolve internal S3 storage URI for TiTiler."""
    async with database.get_session() as session:
        result = await session.execute(select(Scene).where(Scene.id == scene_id))
        scene = result.scalar_one_or_none()

    if scene is None:
        raise ResourceNotFoundError(
            f"Scene '{scene_id}' does not exist.",
            details={"sceneId": scene_id},
        )

    key = scene.cog_object_key or scene.raw_object_key
    if not key:
        raise ResourceNotFoundError(
            f"Scene '{scene_id}' has no raster imagery available for tiling.",
            details={"sceneId": scene_id},
        )

    cog_bucket = f"{settings.storage_bucket_prefix}-{Bucket.COG.value}"
    raw_bucket = f"{settings.storage_bucket_prefix}-{Bucket.RAW.value}"

    if key.startswith("s3://"):
        storage_uri = key
    elif key.startswith("raw/"):
        storage_uri = f"s3://{raw_bucket}/{key}"
    else:
        storage_uri = f"s3://{cog_bucket}/{key}"

    return scene, storage_uri


async def get_scene_tilejson(
    scene_id: str,
    preset: str | None = None,
    **rendering_params: Any,
) -> dict[str, Any]:
    """Retrieve TileJSON for a scene, rewrite tile URLs to point to AERIS backend."""
    scene, storage_uri = await _resolve_scene_storage_uri(scene_id)

    # Resolve server-side visualization preset
    params: dict[str, str] = {"url": storage_uri}
    if preset:
        preset_args = resolve_preset_rendering(preset, scene.band_count, scene.modality)
        params.update(preset_args)

    # Filter out None and merge explicit query params
    for k, v in rendering_params.items():
        if v is not None:
            params[k] = str(v)

    client = _get_http_client()
    titiler_url = f"{settings.tile_server}/cog/{TILE_MATRIX_SET}/tilejson.json"

    try:
        response = await client.get(titiler_url, params=_format_titiler_params(params))
    except Exception as exc:
        raise UpstreamUnavailableError(
            f"Failed to connect to tile server: {exc}",
            details={"upstream": "titiler", "error": str(exc)},
        ) from exc

    if response.status_code != 200:
        logger.warning(
            "TiTiler tilejson request failed",
            extra={"status": response.status_code, "body": response.text, "scene_id": scene_id},
        )
        raise ResourceNotFoundError(
            f"TileJSON generation failed for scene '{scene_id}'.",
            details={"sceneId": scene_id, "status": response.status_code},
        )

    tilejson = response.json()

    # Build sanitized query params to append to the rewritten tile template URL
    query_params: dict[str, str] = {}
    if preset:
        query_params["preset"] = preset
    for k, v in rendering_params.items():
        if v is not None and k != "url":
            query_params[k] = str(v)

    query_str = f"?{urlencode(query_params)}" if query_params else ""
    backend_tile_template = f"/api/v1/tiles/{scene_id}/{{z}}/{{x}}/{{y}}.png{query_str}"
    tilejson["tiles"] = [backend_tile_template]

    return tilejson


async def render_scene_tile(
    scene_id: str,
    z: int,
    x: int,
    y: int,
    format: str = "png",
    preset: str | None = None,
    **rendering_params: Any,
) -> tuple[bytes, str]:
    """Render a single XYZ tile for a scene, returning (tile_bytes, content_type)."""
    scene, storage_uri = await _resolve_scene_storage_uri(scene_id)

    params: dict[str, str] = {"url": storage_uri}
    if preset:
        preset_args = resolve_preset_rendering(preset, scene.band_count, scene.modality)
        params.update(preset_args)

    for k, v in rendering_params.items():
        if v is not None:
            params[k] = str(v)

    client = _get_http_client()
    # Request 1x scale tile with specified format (e.g. .png)
    titiler_tile_url = f"{settings.tile_server}/cog/tiles/{TILE_MATRIX_SET}/{z}/{x}/{y}@1x.{format}"

    try:
        response = await client.get(titiler_tile_url, params=_format_titiler_params(params))
    except Exception as exc:
        raise UpstreamUnavailableError(
            f"Failed to fetch tile from tile server: {exc}",
            details={"upstream": "titiler", "error": str(exc)},
        ) from exc

    if response.status_code == 404:
        raise ResourceNotFoundError(
            f"Tile {z}/{x}/{y} not found for scene '{scene_id}'.",
            details={"sceneId": scene_id, "z": z, "x": x, "y": y},
        )

    if response.status_code != 200:
        raise UpstreamUnavailableError(
            f"Tile server error ({response.status_code}) rendering tile {z}/{x}/{y}.",
            details={"sceneId": scene_id, "status": response.status_code},
        )

    content_type = response.headers.get("content-type", f"image/{format}")
    return response.content, content_type


async def get_scene_preview(
    scene_id: str,
    format: str = "png",
    preset: str | None = None,
    max_size: int = 512,
    **rendering_params: Any,
) -> tuple[bytes, str]:
    """Render a fast raster preview image for a scene."""
    scene, storage_uri = await _resolve_scene_storage_uri(scene_id)

    params: dict[str, str] = {"url": storage_uri, "max_size": str(max_size)}
    if preset:
        preset_args = resolve_preset_rendering(preset, scene.band_count, scene.modality)
        params.update(preset_args)

    for k, v in rendering_params.items():
        if v is not None:
            params[k] = str(v)

    client = _get_http_client()
    titiler_preview_url = f"{settings.tile_server}/cog/preview.{format}"

    try:
        response = await client.get(titiler_preview_url, params=_format_titiler_params(params))
    except Exception as exc:
        raise UpstreamUnavailableError(
            f"Failed to fetch preview from tile server: {exc}",
            details={"upstream": "titiler", "error": str(exc)},
        ) from exc

    if response.status_code != 200:
        raise UpstreamUnavailableError(
            f"Tile server error ({response.status_code}) generating preview for '{scene_id}'.",
            details={"sceneId": scene_id, "status": response.status_code},
        )

    content_type = response.headers.get("content-type", f"image/{format}")
    return response.content, content_type
