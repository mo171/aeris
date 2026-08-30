"""The kinds of image the backend renders, and the kinds of legend those images carry.

what  : `FigureKind` and `LegendKind`.
where : Carried by every `figure-ready` event (`api-contract.md` §6) and read by
        `app/services/rendering/` when it is built in Phase 1.2.1. The decision to render server-side at all
        is ADR-004.
how   : A figure is **not** a tile. A tile is a fragment draped on the globe in EPSG:3857, with no legend and
        no annotation, composited by the browser. A figure is one self-contained picture that carries its own
        colourbar, can draw boxes and labels, can place two dates side by side, and needs no WebGL context.
        Both ship, and neither substitutes for the other.

        `LegendKind` exists because the legend travels as **data**, not only as pixels. A colourbar may also be
        drawn into the image, but the machine-readable legend is mandatory: a scene of coloured geometry that
        never says what the colours mean is a picture, not evidence. `CONTINUOUS` carries a domain,
        `CATEGORICAL` and `BINARY` carry entries.

        This module is the vocabulary only. The named colour ramps and their domains arrive in Phase 1.2.1
        with the renderer that draws them, so that the list describes what is actually drawable.
"""

from enum import StrEnum


class FigureKind(StrEnum):
    """What a rendered figure shows. One kind per figure, chosen by the stage that produced the data."""

    RGB_COMPOSITE = "rgb-composite"
    INDEX_MAP = "index-map"
    MASK_OVERLAY = "mask-overlay"
    DETECTION_OVERLAY = "detection-overlay"
    COMPARISON = "comparison"
    HISTOGRAM = "histogram"
    SAR_BACKSCATTER = "sar-backscatter"


class LegendKind(StrEnum):
    """How a figure's legend is structured. Determines whether `domain` or `entries` is populated."""

    CONTINUOUS = "continuous"
    CATEGORICAL = "categorical"
    BINARY = "binary"
