"""Turns a named ramp into a lookup table, and a normalised array into RGBA pixels with nodata transparent.

what  : `lookup_table()`, `colourise()`, `legend_entries()` and `hex_colour_at()`.
where : Called by `services/rendering/figures.py` and `overlays.py` through `asyncio.to_thread`.
how   : **Pure, sync, NumPy only** - `architecture-context.md` §12. Nothing here opens a file or chooses
        a ramp; it is handed a name and an array and returns pixels.

        **matplotlib is used for its colormaps and for nothing else.** No figure is created, no `Agg`
        canvas, no `savefig`. `plt.get_cmap(name)(x)` is a pure lookup into perceptually-tested colour
        data, and that data is genuinely worth not reimplementing - hand-picking control points for a
        diverging ramp is how a product ends up with a midpoint that reads as a value.

        Composition is Pillow and NumPy instead, and the reason is the 1.2.1 gate: **re-rendering from a
        recorded `renderSpec` must be byte-identical.** A matplotlib figure writes a `Software` tag into
        its PNG and its layout depends on font metrics, DPI and backend version; an RGBA array encoded by
        Pillow with fixed parameters depends on none of those. Determinism is a requirement here, not a
        preference, because `api-contract.md` §6 rule 2 makes the render spec part of the evidence chain.

        **Nodata is transparent, and this is where that happens.** A NaN in the input becomes alpha 0 in
        the output. Black would read as burnt ground over a globe and as data over a white report page;
        white would read as cloud. Only transparency reads as absence.
"""

import numpy as np

from app.constants.color_ramps import (
    COLOR_RAMP_RESOLUTION,
    MATPLOTLIB_COLORMAPS,
    OPAQUE_ALPHA,
    TRANSPARENT_ALPHA,
    ColorRampId,
)

# Built once per ramp on first use. A lookup table is 256x4 bytes and constructing it costs a matplotlib
# colormap evaluation; a figure with several bands would otherwise rebuild the same table per band.
_LOOKUP_TABLES: dict[ColorRampId, np.ndarray] = {}


def lookup_table(ramp: ColorRampId) -> np.ndarray:
    """The ramp as a `(256, 4)` uint8 table, RGBA, cached.

    Returned as a copy-free cached array on purpose - callers index it, never mutate it. Making a defensive
    copy per call would allocate a table per figure for no benefit.
    """
    cached = _LOOKUP_TABLES.get(ramp)
    if cached is not None:
        return cached

    # Imported here rather than at module scope: matplotlib pulls in a large dependency tree, and a
    # process that never renders a figure - `aeris doctor`, a dataset listing - should not pay for it.
    from matplotlib import colormaps

    colormap = colormaps[MATPLOTLIB_COLORMAPS[ramp]]
    samples = np.linspace(0.0, 1.0, COLOR_RAMP_RESOLUTION)
    table = (np.asarray(colormap(samples)) * 255.0).round().astype(np.uint8)

    _LOOKUP_TABLES[ramp] = table
    return table


def colourise(
    normalised: np.ndarray,
    ramp: ColorRampId,
    *,
    alpha: int = OPAQUE_ALPHA,
) -> np.ndarray:
    """Map a `[0, 1]` array onto RGBA, with NaN fully transparent.

    Expects the output of `apply_stretch` - already normalised and clipped. Taking raw values here would
    mean this function silently choosing a stretch, which is the decision §8 rule 13 requires be explicit
    and recorded.
    """
    table = lookup_table(ramp)

    valid = np.isfinite(normalised)
    # NaN would become a garbage index. Filled with 0 before indexing and then made transparent below, so
    # the value under a transparent pixel is deterministic rather than whatever the memory held.
    indices = np.where(valid, normalised, 0.0)
    indices = (indices * (COLOR_RAMP_RESOLUTION - 1)).round().astype(np.uint16)

    rgba = table[indices].copy()
    rgba[..., 3] = np.where(valid, alpha, TRANSPARENT_ALPHA)
    return rgba


def hex_colour_at(ramp: ColorRampId, position: float) -> str:
    """One colour from a ramp as `#rrggbb`, for a legend entry.

    Hex because that is what the frontend's legend component takes, and because a legend entry that
    carried a matplotlib name would need the frontend to own a colormap implementation.
    """
    table = lookup_table(ramp)
    index = int(round(np.clip(position, 0.0, 1.0) * (COLOR_RAMP_RESOLUTION - 1)))
    red, green, blue = table[index][:3]
    return f"#{red:02x}{green:02x}{blue:02x}"


def legend_entries(
    ramp: ColorRampId, labels: dict[float, str]
) -> list[dict[str, str]]:
    """Turn positions on a ramp into the `legend.entries` a categorical or binary figure carries.

    `api-contract.md` §6 rule 3, quoting the frontend: *a scene of coloured geometry that never says what
    the colours mean is a picture, not evidence.* A continuous figure carries a domain instead and passes
    `entries: null`.
    """
    return [
        {"color": hex_colour_at(ramp, position), "label": label}
        for position, label in sorted(labels.items())
    ]


def blend_over(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    """Composite `overlay` onto `base` using the overlay's alpha. Both RGBA uint8, same shape.

    Standard source-over alpha compositing, written out rather than delegated to Pillow so it stays pure
    and testable: the result of blending a known colour at a known alpha over a known base is arithmetic
    a person can check.

    The base's own alpha is preserved. Blending a mask over a scene must not make the scene's nodata
    margin opaque - the composite is transparent wherever the base was, whatever the overlay says.
    """
    if base.shape != overlay.shape:
        raise ValueError(f"base is {base.shape} and overlay is {overlay.shape}; they must match")

    overlay_alpha = (overlay[..., 3:4].astype(np.float32)) / 255.0
    blended = base.astype(np.float32)
    blended[..., :3] = (
        overlay[..., :3].astype(np.float32) * overlay_alpha
        + blended[..., :3] * (1.0 - overlay_alpha)
    )
    # Alpha from the base alone, deliberately - see the docstring.
    blended[..., 3] = base[..., 3]
    return blended.round().astype(np.uint8)
