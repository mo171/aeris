"""What the globe can draw, and how it draws it.

what  : `LayerKind`, `LayerRenderMode`.
where : Carried by every `layer-ready` event - the event the frontend's own notes call the single most
        important line in the analysis contract, because the viewer draws a layer the moment it exists rather
        than waiting for the run to finish. Transcribed from the frontend's investigation schema.
how   : `LayerKind` is what the data *is*; `LayerRenderMode` is how Cesium presents it. They are separate
        because the same polygon layer is draped for one question and extruded for another.

        `EXTRUDED` is the mode that carries the product's argument: change polygons extruded by `magnitude`
        let an operator *feel* the size of a change instead of reading a number (`api-contract.md` §8 rule 6).
        That is why every evidence polygon is required to carry `magnitude` in the first place.

        Note what is not here: tiles are described by TileJSON, not by this vocabulary, and a rendered figure
        is not a layer at all (`api-contract.md` §6 and §8, ADR-004). A layer goes on the globe; a figure is a
        self-contained picture that carries its own legend.
"""

from enum import StrEnum


class LayerKind(StrEnum):
    """What a layer contains."""

    RASTER_TILES = "raster-tiles"
    RASTER_MASK = "raster-mask"
    POLYGON_VECTOR = "polygon-vector"
    POINT_VECTOR = "point-vector"
    BBOX_VECTOR = "bbox-vector"
    HEATMAP_SURFACE = "heatmap-surface"


class LayerRenderMode(StrEnum):
    """How the globe presents a layer."""

    DRAPED = "draped"
    EXTRUDED = "extruded"
    CLASSIFIED = "classified"
    HEATMAP = "heatmap"
