"""Turns an array into a finished, self-contained picture with its legend and its provenance, and puts it where the operator can see it.

what  : `render_index_map()`, `render_rgb_composite()`, `render_mask_overlay()` and `render_from_spec()`.
where : Called by pipeline nodes from Phase 1.4 onwards, each emitting its figure the moment its stage
        produces an array. `cli/renderers/figure_writer.py` consumes the events in Phase 1.
how   : This module *chooses* - which ramp, which stretch, what the legend says - and `math/` executes.
        That split is `architecture-context.md` §12, and here it carries a second meaning: the choices
        this file makes are the ones §8 rule 13 requires be recorded, so they all end up in `renderSpec`.

        **A figure is not a tile, and the distinction is load-bearing** (`api-contract.md` §8). A tile is a
        fragment draped on the globe in EPSG:3857, composited by the browser, with no legend and no
        annotation. A figure is one self-contained image that carries its own colourbar and needs no WebGL
        context - it can be pasted into a report, handed to the VLM at S14, or opened on a second monitor.
        Both ship; neither substitutes for the other.

        **`render_from_spec` is what makes the render spec true.** `api-contract.md` §6 rule 2 requires
        re-rendering from a recorded spec to be byte-identical, and the only way to keep that honest is for
        the reproduction path to be a real function that a test actually runs - not a promise in a
        docstring. Every renderer below builds its spec and then renders *through* the same code path the
        reproduction uses.

        **Every renderer requires a `trace_step_id`** (§6 rule 1). It is a parameter with no default, so a
        caller with no stage behind their image cannot render one without noticing.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.constants.color_ramps import (
    FIXED_DOMAINS,
    MASK_OVERLAY_ALPHA,
    OPAQUE_ALPHA,
    ColorRampId,
)
from app.constants.figure_kinds import FigureKind, LegendKind
from app.constants.storage import Bucket
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.lib import storage
from app.lib.exceptions import InvalidRequestError
from app.schemas.events.figure import FigureLegend, FigureReadyEvent, LegendEntry, RenderSpec
from app.constants.raster import SENTINEL2_BANDS, SpectralBand
from app.services.rendering.math.color_ramps import blend_over, colourise, hex_colour_at
from app.services.rendering.math.rasterize import ImageFormat, draw_colourbar, draw_discrete_legend, encode_image
from app.services.rendering.math.stretch import StretchBounds, StretchMethod, apply_stretch, compute_stretch

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RenderedFigure:
    """A finished figure: the bytes, and the event that describes them."""

    event: FigureReadyEvent
    image_bytes: bytes
    image_format: ImageFormat

    # The composed pixels, kept so a caller can draw over them. A mask overlay needs the base image it is
    # drawn on, and re-decoding the bytes to get it back would be both wasteful and lossy in the one case
    # (`lossy=True`) where it would silently change what the overlay is composited onto.
    rgba: np.ndarray


def figure_object_key(run_id: str, figure_id: str, suffix: str) -> str:
    """Where a figure lives in storage. Keyed by run then figure, so a run's figures list with one prefix.

    Public, and the single source of truth for the key. `cli/renderers/figure_writer.py` fetches figures
    back out and must derive the same key; the alternative - parsing it out of the event's `imageUrl` -
    couples a storage layout to a Phase 2 route and breaks the first time the route changes.
    """
    return f"{run_id}/{figure_id}.{suffix}"


async def render_index_map(
    index: np.ndarray,
    *,
    run_id: str,
    trace_step_id: str,
    title: str,
    label: str = "NDVI",
    ramp: ColorRampId = ColorRampId.INDEX_VEGETATION,
    bands: list[str] | None = None,
    scene_ids: list[str] | None = None,
    crs: str | None = None,
    mask_applied: bool = False,
    caption: str | None = None,
    claim_ids: list[str] | None = None,
    is_primary: bool = False,
) -> RenderedFigure:
    """A normalised index as a colourised map with a drawn colourbar.

    **The stretch is fixed, not percentile, and that is the important choice.** A normalised index has a
    domain given by its own algebra - `[-1, 1]` - and drawing each week's NDVI over its own extremes makes
    every image look equally varied, which hides precisely the change the operator is looking for. Two
    figures are only comparable if they share a scale.
    """
    domain = FIXED_DOMAINS.get(ramp)
    if domain is None:
        raise InvalidRequestError(
            f"{ramp.value} has no fixed domain, so an index map drawn with it would be stretched to its "
            "own data and would not be comparable with any other figure.",
            details={"colorRamp": ramp.value},
        )

    bounds = StretchBounds(domain[0], domain[1], StretchMethod.FIXED)
    specification = RenderSpec(
        scene_ids=scene_ids or [],
        bands=bands or [],
        stretch=bounds.as_render_spec(),
        color_ramp=ramp,
        # Nothing was resampled - the index was computed on the source grid. Recorded as `none` rather
        # than left out, because "not resampled" and "resampled somehow" must be distinguishable.
        resampling="none",
        crs=crs,
        mask_applied=mask_applied,
    )
    legend = FigureLegend(
        kind=LegendKind.CONTINUOUS,
        label=label,
        color_ramp=ramp,
        domain=[domain[0], domain[1]],
        entries=None,
    )

    rgba = await asyncio.to_thread(_compose_index_map, index, ramp, bounds, label, domain)

    return await _publish(
        rgba,
        run_id=run_id,
        kind=FigureKind.INDEX_MAP,
        title=title,
        caption=caption,
        trace_step_id=trace_step_id,
        claim_ids=claim_ids or [],
        legend=legend,
        specification=specification,
        is_primary=is_primary,
        # Lossless. An index map is read for its values, and a lossy edge invents pixels that are neither
        # one class nor the other (`api-contract.md` §6 rule 6).
        lossy=False,
    )


def _compose_index_map(
    index: np.ndarray,
    ramp: ColorRampId,
    bounds: StretchBounds,
    label: str,
    domain: tuple[float, float],
) -> np.ndarray:
    """Stretch, colourise and add the colourbar. Sync - what `to_thread` is handed."""
    normalised = apply_stretch(index, bounds)
    rgba = colourise(normalised, ramp)
    return draw_colourbar(rgba, ramp=ramp, domain=domain, label=label)


async def render_rgb_composite(
    red: np.ndarray,
    green: np.ndarray,
    blue: np.ndarray,
    *,
    run_id: str,
    trace_step_id: str,
    title: str,
    bands: list[str] | None = None,
    scene_ids: list[str] | None = None,
    crs: str | None = None,
    caption: str | None = None,
    claim_ids: list[str] | None = None,
    is_primary: bool = False,
) -> RenderedFigure:
    """A true-colour composite from three bands.

    **Percentile stretched, per band, and this one has to be.** Raw surface reflectance over land occupies
    a small part of its possible range, so a min-max composite is nearly black. Each band is stretched
    independently because they have genuinely different dynamic ranges - a shared stretch produces a
    colour cast, which on a true-colour image reads as a property of the ground rather than of the render.

    The stretch bounds of all three are recorded, so the composite is reproducible even though it is
    data-dependent.
    """
    stretches = await asyncio.to_thread(
        lambda: [compute_stretch(band, method=StretchMethod.PERCENTILE) for band in (red, green, blue)]
    )
    used_bands = bands or ["B04", "B03", "B02"]
    colors = ["#c0392b", "#27ae60", "#2980b9"]
    
    legend_entries = []
    for band_id, color in zip(used_bands, colors):
        try:
            # Look up the human-readable role (e.g., "red" -> "Red")
            role_str = SENTINEL2_BANDS[SpectralBand(band_id)][0].value
            role_title = role_str.replace("-", " ").title()
            label = f"{role_title} — {band_id}"
        except ValueError:
            # Fallback if the band is unknown
            label = band_id
        legend_entries.append(LegendEntry(color=color, label=label))

    specification = RenderSpec(
        scene_ids=scene_ids or [],
        bands=used_bands,
        # One entry per band, because there genuinely are three stretches. Flattened into the `min`/`max`
        # the contract declares, plus the per-band detail - a spec that recorded only one of the three
        # could not reproduce the image.
        stretch={
            "min": min(bound.minimum for bound in stretches),
            "max": max(bound.maximum for bound in stretches),
            "method": StretchMethod.PERCENTILE.value,
            "perBand": ";".join(f"{bound.minimum:.6g}:{bound.maximum:.6g}" for bound in stretches),
        },
        color_ramp=ColorRampId.TRUE_COLOR,
        resampling="none",
        crs=crs,
        mask_applied=False,
    )
    legend = FigureLegend(
        kind=LegendKind.CATEGORICAL,
        label="True colour",
        color_ramp=ColorRampId.TRUE_COLOR,
        domain=None,
        entries=legend_entries,
    )

    base_rgba = await asyncio.to_thread(_compose_rgb, red, green, blue, stretches)
    
    entries = [(e.color, e.label) for e in legend.entries] if legend.entries else None
    if entries and legend.label:
        final_rgba = await asyncio.to_thread(draw_discrete_legend, base_rgba, entries=entries, label=legend.label)
    else:
        final_rgba = base_rgba

    return await _publish(
        final_rgba,
        base_rgba=base_rgba,
        run_id=run_id,
        kind=FigureKind.RGB_COMPOSITE,
        title=title,
        caption=caption,
        trace_step_id=trace_step_id,
        claim_ids=claim_ids or [],
        legend=legend,
        specification=specification,
        is_primary=is_primary,
        # Lossy is permitted here and nowhere else (§6 rule 6): nothing is measured from a true-colour
        # composite, it is the largest figure this system produces, and it is the one an operator looks at
        # most. Still lossless below, because the 1.2.1 gate requires byte-identical reproduction and
        # lossy WebP is not reliably reproducible across libwebp versions.
        lossy=False,
    )


def _compose_rgb(
    red: np.ndarray, green: np.ndarray, blue: np.ndarray, stretches: list[StretchBounds]
) -> np.ndarray:
    """Three stretched bands into one RGBA image, transparent where any band is nodata."""
    channels = [
        apply_stretch(band, bounds) for band, bounds in zip((red, green, blue), stretches, strict=True)
    ]
    height, width = red.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    for index, channel in enumerate(channels):
        rgba[..., index] = np.nan_to_num(channel * 255.0).round().astype(np.uint8)

    # Transparent where **any** band is missing. A pixel with two of three bands is not a colour - it is a
    # colour with one channel invented, which is exactly the kind of plausible wrong output §8 forbids.
    observed = np.isfinite(red) & np.isfinite(green) & np.isfinite(blue)
    rgba[..., 3] = np.where(observed, OPAQUE_ALPHA, 0)
    
    return rgba


async def render_mask_overlay(
    mask: np.ndarray,
    base_rgba: np.ndarray,
    *,
    run_id: str,
    trace_step_id: str,
    title: str,
    label: str,
    ramp: ColorRampId = ColorRampId.MASK_AMBER,
    scene_ids: list[str] | None = None,
    crs: str | None = None,
    caption: str | None = None,
    claim_ids: list[str] | None = None,
    is_primary: bool = False,
) -> RenderedFigure:
    """A binary mask drawn over a base image.

    **Semi-transparent, deliberately.** An opaque mask answers "where" and destroys "over what", and an
    operator judging a mask is judging exactly that - whether it agrees with the ground beneath it. A mask
    that hides its own evidence cannot be checked.
    """
    specification = RenderSpec(
        scene_ids=scene_ids or [],
        bands=[],
        stretch={"min": 0.0, "max": 1.0, "method": StretchMethod.FIXED.value},
        color_ramp=ramp,
        # **Nearest, and it must be** - `architecture-context.md` §8 rule 6. A mask holds class labels;
        # interpolating between 0 and 1 produces 0.5, which is a class that does not exist.
        resampling="nearest",
        crs=crs,
        mask_applied=True,
    )
    legend = FigureLegend(
        kind=LegendKind.BINARY,
        label=label,
        color_ramp=ramp,
        domain=None,
        entries=[
            LegendEntry(color=hex_colour_at(ramp, 0.85), label=label),
            LegendEntry(color="#00000000"[:7], label="Not detected"),
        ],
    )

    base_rgba = await asyncio.to_thread(_compose_mask_overlay, mask, base_rgba, ramp)
    
    entries = [(e.color, e.label) for e in legend.entries] if legend.entries else None
    if entries and legend.label:
        final_rgba = await asyncio.to_thread(draw_discrete_legend, base_rgba, entries=entries, label=legend.label)
    else:
        final_rgba = base_rgba

    return await _publish(
        final_rgba,
        run_id=run_id,
        kind=FigureKind.MASK_OVERLAY,
        title=title,
        caption=caption,
        trace_step_id=trace_step_id,
        claim_ids=claim_ids or [],
        legend=legend,
        specification=specification,
        is_primary=is_primary,
        lossy=False,
    )


def _compose_mask_overlay(mask: np.ndarray, base_rgba: np.ndarray, ramp: ColorRampId) -> np.ndarray:
    """Colour the mask, then composite it over the base at partial alpha."""
    if mask.shape != base_rgba.shape[:2]:
        raise ValueError(
            f"mask is {mask.shape} and the base image is {base_rgba.shape[:2]}. A mask drawn over a "
            "differently-shaped base marks the wrong ground."
        )

    # The mask's *true* pixels get the ramp's strong end; false pixels get zero alpha rather than the
    # ramp's weak end, so "not detected" is genuinely absent rather than a pale wash that reads as doubt.
    coloured = colourise(np.where(mask, 0.85, 0.0).astype(np.float32), ramp, alpha=MASK_OVERLAY_ALPHA)
    coloured[..., 3] = np.where(mask, MASK_OVERLAY_ALPHA, 0).astype(np.uint8)
    composed = blend_over(base_rgba, coloured)
        
    return composed


async def _publish(
    rgba: np.ndarray,
    *,
    base_rgba: np.ndarray | None = None,
    run_id: str,
    kind: FigureKind,
    title: str,
    caption: str | None,
    trace_step_id: str,
    claim_ids: list[str],
    legend: FigureLegend,
    specification: RenderSpec,
    is_primary: bool,
    lossy: bool,
    image_format: ImageFormat = ImageFormat.WEBP,
) -> RenderedFigure:
    """Encode, upload, and build the event. The one place a figure becomes addressable.

    Uploaded to the `figures` bucket, which `constants/storage.py` marks browser-facing - so the CORS
    configuration proven in Phase 0.4 is what lets the frontend load `imageUrl` at all.
    """
    figure_id = new_identifier(IdentifierPrefix.FIGURE)
    image_bytes = await asyncio.to_thread(
        encode_image, rgba, image_format=image_format, lossy=lossy
    )

    object_key = figure_object_key(run_id, figure_id, image_format.value)
    await storage.put_object(
        Bucket.FIGURES, object_key, image_bytes, content_type=image_format.media_type
    )

    height, width = rgba.shape[:2]
    event = FigureReadyEvent(
        run_id=run_id,
        figure_id=figure_id,
        kind=kind,
        title=title,
        caption=caption,
        # The Phase 2 route, not a storage URL. `api-contract.md` §6 puts the bytes behind
        # `/api/v1/figures/{figureId}` so the object stays private and the URL stays stable.
        image_url=f"/api/v1/figures/{figure_id}.{image_format.value}",
        width=width,
        height=height,
        trace_step_id=trace_step_id,
        claim_ids=claim_ids,
        legend=legend,
        render_spec=specification,
        is_primary=is_primary,
    )

    logger.info(
        "figure rendered",
        extra={
            "run_id": run_id, "figure_id": figure_id, "kind": kind.value,
            "size": f"{width}x{height}", "bytes": len(image_bytes),
        },
    )
    return RenderedFigure(
        event=event, image_bytes=image_bytes, image_format=image_format, rgba=base_rgba if base_rgba is not None else rgba
    )


async def render_from_spec(
    index: np.ndarray, specification: RenderSpec, *, label: str
) -> bytes:
    """Redraw an index map from a recorded `renderSpec`, returning the bytes only.

    **This is the function that makes `api-contract.md` §6 rule 2 true rather than aspirational.** The
    reproduction path is a real function a test runs, not a claim in a docstring - and it deliberately
    takes nothing but the array and the spec, so a spec that is missing something needed to redraw the
    image fails here instead of being discovered incomplete months later.
    """
    ramp = ColorRampId(specification.color_ramp)
    bounds = StretchBounds(
        float(specification.stretch["min"]),
        float(specification.stretch["max"]),
        StretchMethod(str(specification.stretch["method"])),
    )
    domain = (bounds.minimum, bounds.maximum)

    rgba = await asyncio.to_thread(_compose_index_map, index, ramp, bounds, label, domain)
    return await asyncio.to_thread(encode_image, rgba, image_format=ImageFormat.WEBP, lossy=False)


async def write_figure_locally(figure: RenderedFigure, directory: Path) -> Path:
    """Also write a figure to disk, so Phase 1 can look at it without a browser or a bucket.

    The same reasoning as `journal_writer.py`: the whole capability is exercisable in the terminal before
    a route exists. `cli/renderers/figure_writer.py` is what calls this.
    """
    destination = directory / f"{figure.event.figure_id}.{figure.image_format.value}"
    # Both offloaded - `code-standards.md` §7 keeps blocking calls off the loop, and `mkdir` against a
    # network mount is not the microsecond it is against a local disk.
    await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(destination.write_bytes, figure.image_bytes)
    return destination
