"""Encodes an RGBA array into image bytes, deterministically, and draws the colourbar a figure needs to be readable.

what  : `encode_image()`, `ImageFormat`, `draw_colourbar()` and `stack_horizontally()`.
where : Called by `services/rendering/figures.py` through `asyncio.to_thread`. The bytes it returns go to
        MinIO and to `runs/<run_id>/figures/`.
how   : **Pure, sync, Pillow and NumPy** - `architecture-context.md` §12. It takes arrays and returns
        bytes; it never chooses a ramp, a stretch or a filename.

        **Determinism is the requirement, not a nicety.** `api-contract.md` §6 rule 2: re-rendering from a
        recorded `renderSpec` must be byte-identical, because a figure the VLM reasoned over is part of the
        evidence chain and "which stretch was that drawn with" has to be answerable months later. Three
        things are done for it, and each of them is a default that would otherwise break it:

        - **No metadata.** Pillow writes no timestamp by default, but `exif`/`icc_profile` ride along from a
          source image if one is passed. Encoding is from a raw array, so there is no source to inherit from.
        - **Explicit encoder parameters.** `optimize` and `compress_level` change output bytes between
          Pillow versions if left to the default; both are pinned.
        - **Lossless WebP.** Lossy encoding is permitted by §6 rule 6 for RGB composites and is *not* used
          for anything a number is computed from - a lossy nodata edge invents pixels that are neither data
          nor nodata (§8 rule 4). Lossless is also the only mode that is reliably reproducible.

        **The colourbar is drawn here rather than by matplotlib**, for the same reason. A matplotlib
        colourbar's layout depends on font metrics, DPI and backend version, so two runs on two machines
        produce different bytes. A gradient strip and Pillow's bundled bitmap font depend on neither.
"""

import io
from enum import StrEnum

import numpy as np

from app.constants.color_ramps import COLOR_RAMP_RESOLUTION, OPAQUE_ALPHA, ColorRampId
from app.services.rendering.math.color_ramps import lookup_table

# How the colourbar is laid out. Fixed rather than proportional to the image: a colourbar that scales with
# its figure is unreadable on a small one and absurd on a large one, and fixed geometry is also what makes
# the output reproducible.
COLOURBAR_HEIGHT = 18
COLOURBAR_MARGIN = 12
COLOURBAR_LABEL_HEIGHT = 14
COLOURBAR_PANEL_HEIGHT = COLOURBAR_HEIGHT + COLOURBAR_LABEL_HEIGHT + COLOURBAR_MARGIN * 2

# The panel behind a colourbar. Opaque, because a legend drawn over transparent nodata is unreadable on
# whatever the viewer happens to composite the figure onto.
PANEL_BACKGROUND = (17, 17, 17, OPAQUE_ALPHA)
PANEL_TEXT = (221, 221, 221, OPAQUE_ALPHA)

# PNG compression. 6 is Pillow's default and is pinned so a future default change cannot alter the bytes.
PNG_COMPRESS_LEVEL = 6


class ImageFormat(StrEnum):
    """The formats a figure may be written in. `api-contract.md` §6 rule 6."""

    # Preferred. Roughly 30% smaller than PNG at the same quality, with alpha, and universally supported
    # by browsers this decade.
    WEBP = "webp"

    # The fallback, and the format for anything a number is computed from.
    PNG = "png"

    @property
    def media_type(self) -> str:
        return f"image/{self.value}"


def encode_image(
    rgba: np.ndarray,
    *,
    image_format: ImageFormat = ImageFormat.WEBP,
    lossy: bool = False,
) -> bytes:
    """Encode an RGBA array to image bytes, reproducibly.

    `lossy` is refused for PNG rather than ignored: a caller asking for lossy PNG has misunderstood
    something, and silently giving them lossless would hide it.
    """
    from PIL import Image

    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError(f"expected an (H, W, 4) RGBA array, got {rgba.shape}")
    if rgba.dtype != np.uint8:
        raise ValueError(f"expected uint8, got {rgba.dtype}")
    if lossy and image_format is ImageFormat.PNG:
        raise ValueError("PNG is always lossless; asking for lossy PNG means the caller expected WebP")

    image = Image.fromarray(rgba, mode="RGBA")
    buffer = io.BytesIO()

    if image_format is ImageFormat.WEBP:
        # `method=4` is Pillow's default effort level, pinned. `exact=True` preserves the RGB values of
        # fully transparent pixels, which matters for reproducibility: without it the encoder is free to
        # rewrite invisible pixels to whatever compresses best, and two encodes can differ in bytes that
        # nobody can see.
        image.save(
            buffer, format="WEBP", lossless=not lossy, quality=90 if lossy else 100,
            method=4, exact=True,
        )
    else:
        image.save(buffer, format="PNG", optimize=False, compress_level=PNG_COMPRESS_LEVEL)

    return buffer.getvalue()


def draw_colourbar(
    rgba: np.ndarray,
    *,
    ramp: ColorRampId,
    domain: tuple[float, float],
    label: str,
) -> np.ndarray:
    """Append a labelled colourbar panel below an image.

    Drawn into the picture **as well as** carried as data on the event. `api-contract.md` §6 rule 3 makes
    the machine-readable legend mandatory; this is for the case the rule exists to survive - the figure
    pasted into a slide deck, screenshotted into a report, or handed to the VLM at S14, all of which lose
    the event and keep the pixels.
    """
    from PIL import Image, ImageDraw, ImageFont

    height, width = rgba.shape[:2]
    panel = Image.new("RGBA", (width, COLOURBAR_PANEL_HEIGHT), PANEL_BACKGROUND)

    # The gradient, built from the same lookup table the image was coloured with - so the bar cannot
    # disagree with the picture above it.
    table = lookup_table(ramp)
    positions = (np.linspace(0.0, 1.0, max(1, width - COLOURBAR_MARGIN * 2))
                 * (COLOR_RAMP_RESOLUTION - 1)).round().astype(np.uint16)
    strip = np.tile(table[positions], (COLOURBAR_HEIGHT, 1, 1))
    strip[..., 3] = OPAQUE_ALPHA
    panel.paste(Image.fromarray(strip, mode="RGBA"), (COLOURBAR_MARGIN, COLOURBAR_MARGIN))

    draw = ImageDraw.Draw(panel)
    # Pillow's bundled bitmap font. Deliberately not a system font: a system font is present on one machine
    # and absent on another, which breaks both reproducibility and the render.
    font = ImageFont.load_default()
    text_y = COLOURBAR_MARGIN + COLOURBAR_HEIGHT + 2
    draw.text((COLOURBAR_MARGIN, text_y), f"{domain[0]:g}", fill=PANEL_TEXT, font=font)
    draw.text((width // 2 - len(label) * 3, text_y), label, fill=PANEL_TEXT, font=font)
    draw.text((width - COLOURBAR_MARGIN - 30, text_y), f"{domain[1]:g}", fill=PANEL_TEXT, font=font)

    composed = np.zeros((height + COLOURBAR_PANEL_HEIGHT, width, 4), dtype=np.uint8)
    composed[:height] = rgba
    composed[height:] = np.asarray(panel)
    return composed


def draw_discrete_legend(
    rgba: np.ndarray,
    *,
    entries: list[tuple[str, str]],
    label: str,
) -> np.ndarray:
    """Append a discrete categorical/binary legend panel below an image."""
    from PIL import Image, ImageDraw, ImageFont

    height, width = rgba.shape[:2]
    # Use a slightly taller panel if needed, but COLOURBAR_PANEL_HEIGHT works well.
    panel = Image.new("RGBA", (width, COLOURBAR_PANEL_HEIGHT), PANEL_BACKGROUND)
    draw = ImageDraw.Draw(panel)
    font = ImageFont.load_default()

    # Draw the main label centered at the top
    # Default font is roughly 6px wide per char
    label_w = len(label) * 6
    draw.text((width // 2 - label_w // 2, COLOURBAR_MARGIN), label, fill=PANEL_TEXT, font=font)

    # Draw swatches centered horizontally below the title
    if entries:
        gap_between_entries = 24
        swatch_size = 18
        swatch_gap = 8
        
        entry_widths = [swatch_size + swatch_gap + len(text) * 6 for _, text in entries]
        total_entries_width = sum(entry_widths) + gap_between_entries * (len(entries) - 1)
        
        current_x = width // 2 - total_entries_width // 2
        y_pos = COLOURBAR_MARGIN + 18
        
        for (color_hex, text), e_width in zip(entries, entry_widths):
            color_hex = color_hex.lstrip("#")
            r = int(color_hex[0:2], 16)
            g = int(color_hex[2:4], 16)
            b = int(color_hex[4:6], 16)
            a = int(color_hex[6:8], 16) if len(color_hex) >= 8 else 255
            
            draw.rectangle(
                [current_x, y_pos, current_x + swatch_size, y_pos + swatch_size],
                fill=(r, g, b, a)
            )
            
            draw.text((current_x + swatch_size + swatch_gap, y_pos + 2), text, fill=PANEL_TEXT, font=font)
            
            current_x += e_width + gap_between_entries

    composed = np.zeros((height + COLOURBAR_PANEL_HEIGHT, width, 4), dtype=np.uint8)
    composed[:height] = rgba
    composed[height:] = np.asarray(panel)
    return composed


def stack_horizontally(panels: list[np.ndarray], *, gap: int = 8) -> np.ndarray:
    """Place images side by side - T1 | T2 | change, the strongest single figure this system produces.

    Panels must share a height. Resizing one to fit would change its pixel scale silently, and a
    comparison whose two halves are at different scales is the thing a comparison exists to prevent.
    """
    if not panels:
        raise ValueError("nothing to stack")
    heights = {panel.shape[0] for panel in panels}
    if len(heights) != 1:
        raise ValueError(
            f"panels have heights {sorted(heights)}. A comparison whose halves are at different scales "
            "misrepresents both; resample them onto one grid before composing."
        )

    height = panels[0].shape[0]
    total_width = sum(panel.shape[1] for panel in panels) + gap * (len(panels) - 1)
    composed = np.zeros((height, total_width, 4), dtype=np.uint8)

    offset = 0
    for panel in panels:
        composed[:, offset : offset + panel.shape[1]] = panel
        offset += panel.shape[1] + gap
    return composed
