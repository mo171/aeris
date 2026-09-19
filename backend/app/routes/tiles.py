"""Tiles routes declaration (Phase 2.6).

what  : FastAPI routes for TileJSON metadata, XYZ WebMercatorQuad tile streaming, and preview images.
where : Mounted at `/api/v1/tiles` by `app/main.py`.
how   : Conforms to `api-contract.md` §8:
        - Pure route declarations. All logic resides in `tiles_controller`.
        - Server-side preset mapping and band math.
        - Direct binary PNG responses with alpha channel.
"""

from typing import Any

from fastapi import APIRouter, Path, Query, Response

from app.controllers import tiles_controller

router = APIRouter(prefix="/tiles", tags=["tiles"])


@router.get("/{scene_id}/tilejson.json")
@router.get("/scenes/{scene_id}/tilejson.json")
async def get_tilejson(
    scene_id: str = Path(..., description="Scene identifier"),
    preset: str | None = Query(None, description="Visualization preset (e.g. true_color, false_color_nir, ndvi, ndwi, sar_vv, grayscale)"),
    bidx: str | None = Query(None, description="Band indexes (e.g. 1,2,3 or 4,3,2)"),
    rescale: str | None = Query(None, description="Min/max value stretch range (e.g. 0,3000)"),
    colormap_name: str | None = Query(None, description="TiTiler colormap name (e.g. rdylgn, blues, viridis)"),
    expression: str | None = Query(None, description="Band math formula (e.g. (b8-b4)/(b8+b4))"),
) -> dict[str, Any]:
    """Retrieve TileJSON metadata with rewritten tile URLs pointing to the AERIS backend proxy."""
    return await tiles_controller.get_scene_tilejson(
        scene_id=scene_id,
        preset=preset,
        bidx=bidx,
        rescale=rescale,
        colormap_name=colormap_name,
        expression=expression,
    )


@router.get("/{scene_id}/{z}/{x}/{y}.png")
@router.get("/scenes/{scene_id}/{z}/{x}/{y}.png")
async def get_tile(
    scene_id: str = Path(..., description="Scene identifier"),
    z: int = Path(..., ge=0, le=24, description="Tile zoom level"),
    x: int = Path(..., ge=0, description="Tile column"),
    y: int = Path(..., ge=0, description="Tile row"),
    preset: str | None = Query(None, description="Visualization preset (e.g. true_color, false_color_nir, ndvi, ndwi, sar_vv, grayscale)"),
    bidx: str | None = Query(None, description="Band indexes (e.g. 1,2,3 or 4,3,2)"),
    rescale: str | None = Query(None, description="Min/max value stretch range (e.g. 0,3000)"),
    colormap_name: str | None = Query(None, description="TiTiler colormap name (e.g. rdylgn, blues, viridis)"),
    expression: str | None = Query(None, description="Band math formula (e.g. (b8-b4)/(b8+b4))"),
) -> Response:
    """Stream a single XYZ raster tile in WebMercatorQuad PNG format with alpha transparency."""
    tile_bytes, content_type = await tiles_controller.render_scene_tile(
        scene_id=scene_id,
        z=z,
        x=x,
        y=y,
        format="png",
        preset=preset,
        bidx=bidx,
        rescale=rescale,
        colormap_name=colormap_name,
        expression=expression,
    )
    return Response(
        content=tile_bytes,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/{scene_id}/preview")
@router.get("/scenes/{scene_id}/preview")
@router.get("/scenes/{scene_id}/quicklook.webp")
async def get_preview(
    scene_id: str = Path(..., description="Scene identifier"),
    preset: str | None = Query(None, description="Visualization preset (e.g. true_color, false_color_nir, ndvi, ndwi, sar_vv, grayscale)"),
    max_size: int = Query(512, ge=64, le=2048, description="Maximum pixel dimension of the preview"),
    bidx: str | None = Query(None, description="Band indexes (e.g. 1,2,3 or 4,3,2)"),
    rescale: str | None = Query(None, description="Min/max value stretch range (e.g. 0,3000)"),
    colormap_name: str | None = Query(None, description="TiTiler colormap name (e.g. rdylgn, blues, viridis)"),
    expression: str | None = Query(None, description="Band math formula (e.g. (b8-b4)/(b8+b4))"),
) -> Response:
    """Render a fast raster preview image for the scene."""
    img_bytes, content_type = await tiles_controller.get_scene_preview(
        scene_id=scene_id,
        format="png",
        preset=preset,
        max_size=max_size,
        bidx=bidx,
        rescale=rescale,
        colormap_name=colormap_name,
        expression=expression,
    )
    return Response(
        content=img_bytes,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
