"""What the globe can draw, and how it draws it.

what  : `LayerKind`, `LayerRenderMode`, `ComparatorSide`, and the defaults a layer is emitted with.
where : Carried by every `layer-ready` event - the event the frontend's own notes call the single most
        important line in the analysis contract, because the viewer draws a layer the moment it exists rather
        than waiting for the run to finish. Transcribed from the frontend's investigation schema.
how   : `LayerKind` is what the data *is*; `LayerRenderMode` is how Cesium presents it. They are separate
        because the same polygon layer is draped for one question and extruded for another.

        `EXTRUDED` is the mode that carries the product's argument: change polygons extruded by `magnitude`
        let an operator *feel* the size of a change instead of reading a number (`api-contract.md` §8 rule 6).
        That is why every evidence polygon is required to carry `magnitude` in the first place.

        `ComparatorSide` is interface state the backend has no opinion about - which pane a layer is drawn
        in - and it is here because `evidenceLayerSchema` requires it on every layer. A single-scene run
        emits `BOTH`: a layer that belongs to neither date is drawn wherever the operator is looking.

        Note what is not here: tiles are described by TileJSON, not by this vocabulary, and a rendered figure
        is not a layer at all (`api-contract.md` §6 and §8, ADR-004). A layer goes on the globe; a figure is a
        self-contained picture that carries its own legend.
"""

from enum import StrEnum
from typing import Final


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


class ComparatorSide(StrEnum):
    """Which comparator pane draws a layer. `BOTH` for anything that is not tied to one date."""

    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"


# The opacity a layer is emitted at. Matches the frontend catalogue's defaults for surfaces (index maps)
# and regions (masks and polygons); the operator adjusts it, the backend only chooses the starting point.
SURFACE_LAYER_OPACITY: Final[float] = 0.78
REGION_LAYER_OPACITY: Final[float] = 0.6
