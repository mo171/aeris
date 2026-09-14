"""Exports retained drawable geometries without changing their scientific values."""

from typing import Any


async def build_geojson(values: dict[str, Any]) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for layer in values.get("layers", []) or []:
        for item in layer.get("features", []):
            geometry = item.get("geometry", {})
            if geometry.get("type") == "polygon":
                ring = [[point.get("longitude"), point.get("latitude")] for point in geometry.get("ring", [])]
                exported = {"type": "Polygon", "coordinates": [ring]}
            elif geometry.get("type") == "point":
                position = geometry.get("position", {})
                exported = {"type": "Point", "coordinates": [position.get("longitude"), position.get("latitude")]}
            elif geometry.get("type") == "bbox":
                bounds = geometry.get("bounds", {})
                west, south, east, north = (bounds.get("west"), bounds.get("south"), bounds.get("east"), bounds.get("north"))
                exported = {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}
            else:
                continue
            features.append({"type": "Feature", "id": item.get("id"), "geometry": exported, "properties": {"layerId": layer.get("id"), "label": item.get("label"), "confidence": item.get("confidence"), "areaHectares": item.get("areaHectares")}})
    return {"type": "FeatureCollection", "features": features}
