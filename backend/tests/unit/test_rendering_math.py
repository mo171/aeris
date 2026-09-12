"""Pins the three choices that decide what a figure appears to say - the stretch, the ramp, and what happens to nodata.

what  : Tests over `services/rendering/math/` - `stretch`, `color_ramps` and `rasterize`.
where : `tests/unit/`. No Docker, no network, no storage.
how   : `architecture-context.md` §8 rule 13 is the whole subject: *"the colour ramp and the stretch bounds
        decide what the operator - and the VLM at S14 - actually sees: widen a stretch and a drought
        disappears, narrow it and healthy crop looks stressed."*

        A wrong figure does not throw. It renders, it looks professional, and it is read by a human and by
        a vision-language model as evidence. So the tests here are about the silent choices:

        - **A fixed stretch cannot silently become a data-dependent one.** Two NDVI maps of the same field
          in different weeks are only comparable if they share a scale, and a percentile stretch per image
          makes every week look equally varied - hiding exactly the change being looked for.
        - **Nodata is transparent, never a colour.** Black reads as burnt ground over a globe and as data
          over a white report page; only transparency reads as absence.
        - **Encoding is byte-identical**, because `api-contract.md` §6 rule 2 makes re-rendering from a
          recorded spec part of the evidence chain.
"""

import numpy as np
import pytest

from app.constants.color_ramps import (
    COLOR_RAMP_RESOLUTION,
    FIXED_DOMAINS,
    MATPLOTLIB_COLORMAPS,
    ColorRampId,
)
from app.services.rendering.math.color_ramps import (
    blend_over,
    colourise,
    hex_colour_at,
    legend_entries,
    lookup_table,
)
from app.services.rendering.math.rasterize import ImageFormat, draw_colourbar, encode_image, stack_horizontally
from app.services.rendering.math.stretch import (
    StretchBounds,
    StretchMethod,
    apply_stretch,
    compute_stretch,
)

# --- Stretch ---------------------------------------------------------------------------------------------


async def test_a_fixed_stretch_ignores_the_data() -> None:
    """The property that makes two figures comparable.

    An NDVI over a drought week and an NDVI over a wet week must be drawn on the same scale, or the ramp
    itself hides the difference between them.
    """
    dry = np.array([[0.05, 0.10]], dtype=np.float32)
    wet = np.array([[0.60, 0.90]], dtype=np.float32)

    dry_bounds = compute_stretch(dry, method=StretchMethod.FIXED, fixed_domain=(-1.0, 1.0))
    wet_bounds = compute_stretch(wet, method=StretchMethod.FIXED, fixed_domain=(-1.0, 1.0))

    assert dry_bounds == wet_bounds
    # And the drawn values differ, which is the whole point - the dry week looks dry.
    assert apply_stretch(dry, dry_bounds).max() < apply_stretch(wet, wet_bounds).min()


async def test_a_fixed_stretch_without_a_domain_is_refused_not_guessed() -> None:
    """**The silent failure this guard exists for.**

    Falling back to the data's own range would give the caller a figure they believe is comparable with
    others and is not - and nothing about the image would say so.
    """
    with pytest.raises(ValueError, match="fixed stretch needs a domain"):
        compute_stretch(np.array([[0.5]], np.float32), method=StretchMethod.FIXED)


async def test_a_percentile_stretch_ignores_a_single_hot_pixel() -> None:
    """Measured on a real Sentinel-2 band: min/max 252-15747 against p2/p98 1108-3276.

    Min-max would compress the entire visible scene into a fifth of the ramp.
    """
    array = np.concatenate([np.full(998, 0.3), np.array([0.0, 1000.0])]).astype(np.float32)

    percentile = compute_stretch(array, method=StretchMethod.PERCENTILE)
    minmax = compute_stretch(array, method=StretchMethod.MIN_MAX)

    assert percentile.maximum == pytest.approx(0.3, abs=0.01)
    assert minmax.maximum == 1000.0


async def test_a_stretch_is_computed_over_observed_pixels_only() -> None:
    """NaN in, NaN out of the reduction - a stretch that includes nodata is not a range of the data."""
    array = np.array([[np.nan, 0.2, 0.8, np.nan]], dtype=np.float32)

    bounds = compute_stretch(array, method=StretchMethod.MIN_MAX)

    assert (bounds.minimum, bounds.maximum) == (pytest.approx(0.2), pytest.approx(0.8))


async def test_a_constant_array_does_not_divide_by_zero() -> None:
    """A degenerate range renders as one flat colour, which is the honest depiction of constant data."""
    bounds = compute_stretch(np.full((4, 4), 7.0, np.float32), method=StretchMethod.MIN_MAX)

    assert bounds.span > 0
    assert np.isfinite(apply_stretch(np.full((4, 4), 7.0, np.float32), bounds)).all()


async def test_an_empty_array_gives_a_usable_range() -> None:
    """An all-nodata array must render as fully transparent, not raise inside a renderer."""
    bounds = compute_stretch(np.full((4, 4), np.nan, np.float32), method=StretchMethod.PERCENTILE)

    assert bounds.span > 0


async def test_the_stretch_records_its_method_not_only_its_numbers() -> None:
    """A percentile stretch is data-dependent and a fixed one is not; only one reproduces on other data.

    `renderSpec` carries both, because the numbers alone cannot answer "would this redraw the same way".
    """
    specification = StretchBounds(-1.0, 1.0, StretchMethod.FIXED).as_render_spec()

    assert specification == {"min": -1.0, "max": 1.0, "method": "fixed"}


async def test_applying_a_stretch_clips_but_keeps_nodata_missing() -> None:
    """Clipping is correct here and nowhere in `math/` arithmetic: this is the last step before pixels,
    and a value beyond the ramp has no colour. What must not happen is a clipped value flowing back into
    a statistic - and it cannot, because this array is for display only."""
    array = np.array([[-5.0, 0.0, 5.0, np.nan]], dtype=np.float32)

    normalised = apply_stretch(array, StretchBounds(-1.0, 1.0, StretchMethod.FIXED))

    assert normalised[0, 0] == 0.0 and normalised[0, 2] == 1.0
    assert np.isnan(normalised[0, 3]), "nodata stays missing rather than clipping to an end of the ramp"


# --- Colour ramps ----------------------------------------------------------------------------------------


async def test_every_ramp_resolves_to_a_real_colormap() -> None:
    """A ramp naming a colormap that does not exist fails at render time, in a pipeline node, mid-run."""
    for ramp in ColorRampId:
        table = lookup_table(ramp)
        assert table.shape == (COLOR_RAMP_RESOLUTION, 4)
        assert table.dtype == np.uint8
        assert ramp in MATPLOTLIB_COLORMAPS


async def test_the_vegetation_ramp_runs_red_to_green() -> None:
    """The convention every agronomist already reads.

    Inverted, the product would be misread at a glance by exactly the people it is for - and nothing about
    the image would look wrong.
    """
    low = lookup_table(ColorRampId.INDEX_VEGETATION)[0]
    high = lookup_table(ColorRampId.INDEX_VEGETATION)[-1]

    assert low[0] > low[1], "the low end is red-dominant"
    assert high[1] > high[0], "the high end is green-dominant"


async def test_nodata_becomes_transparent_and_nothing_else_does() -> None:
    """**§8 rule 4 at the pixel level.** Black reads as burnt ground; white reads as cloud."""
    normalised = np.array([[0.0, 0.5, np.nan, 1.0]], dtype=np.float32)

    rgba = colourise(normalised, ColorRampId.INDEX_VEGETATION)

    assert rgba[0, 2, 3] == 0, "nodata is transparent"
    assert (rgba[0, [0, 1, 3], 3] == 255).all(), "every observed pixel is opaque"


async def test_the_colour_under_a_transparent_pixel_is_deterministic() -> None:
    """NaN cannot index a lookup table, so it is filled before indexing.

    Left to whatever the memory held, two renders of the same array would differ in bytes nobody can see -
    which breaks the byte-identical reproduction `api-contract.md` §6 rule 2 requires.
    """
    array = np.array([[np.nan, np.nan]], dtype=np.float32)

    first = colourise(array, ColorRampId.CONFIDENCE_MAGMA)
    second = colourise(array, ColorRampId.CONFIDENCE_MAGMA)

    assert np.array_equal(first, second)


async def test_the_pixel_under_a_transparent_pixel_is_a_known_value() -> None:
    """Not merely deterministic - a *specified* value, which is what makes it reproducible off this machine.

    Added after a mutation pass: replacing the NaN fill with a different constant was caught by nothing,
    because "encode the same array twice" passes for any fixed choice. The colour beneath a transparent
    pixel is invisible and is still in the file, so it has to be pinned rather than merely stable - two
    builds that disagree about it produce byte-different figures that look identical.

    Filled with 0.0, so a transparent pixel carries the ramp's low end.
    """
    array = np.array([[np.nan, 1.0]], dtype=np.float32)

    rgba = colourise(array, ColorRampId.INDEX_VEGETATION)
    low_end = lookup_table(ColorRampId.INDEX_VEGETATION)[0]

    assert rgba[0, 0, 3] == 0, "the pixel is transparent"
    assert rgba[0, 0, :3].tolist() == low_end[:3].tolist(), (
        "and its invisible colour is the ramp's low end, specifically - not whatever the fill happened to be"
    )


async def test_a_legend_entry_is_a_hex_colour_the_frontend_can_draw() -> None:
    """The frontend draws its own swatches and has no colormap implementation of its own."""
    entries = legend_entries(ColorRampId.MASK_AMBER, {0.0: "Background", 0.9: "Detected"})

    assert [entry["label"] for entry in entries] == ["Background", "Detected"]
    for entry in entries:
        assert entry["color"].startswith("#") and len(entry["color"]) == 7
    assert hex_colour_at(ColorRampId.MASK_AMBER, 0.0) != hex_colour_at(ColorRampId.MASK_AMBER, 1.0)


async def test_blending_an_overlay_preserves_the_base_transparency() -> None:
    """A mask drawn over a scene must not make the scene's nodata margin opaque.

    Otherwise the composite claims ground where the sensor saw nothing - which is the figure equivalent of
    treating nodata as zero.
    """
    base = np.zeros((2, 2, 4), dtype=np.uint8)
    base[..., 3] = [[255, 0], [255, 0]]
    overlay = np.zeros((2, 2, 4), dtype=np.uint8)
    overlay[..., 0] = 255
    overlay[..., 3] = 255

    blended = blend_over(base, overlay)

    assert blended[..., 3].tolist() == [[255, 0], [255, 0]], "alpha comes from the base alone"
    assert blended[0, 0, 0] == 255, "the visible pixel took the overlay's colour"


async def test_blending_mismatched_shapes_is_refused() -> None:
    """A mask drawn over a differently-shaped base marks the wrong ground."""
    with pytest.raises(ValueError, match="must match"):
        blend_over(np.zeros((2, 2, 4), np.uint8), np.zeros((3, 3, 4), np.uint8))


# --- Encoding --------------------------------------------------------------------------------------------


async def test_encoding_is_byte_identical_across_calls() -> None:
    """**The 1.2.1 gate's reproduction claim, at the encoder.**

    `api-contract.md` §6 rule 2: re-rendering from a recorded `renderSpec` must be byte-identical, because
    a figure the VLM reasoned over is part of the evidence chain. Every encoder parameter is pinned for
    this - `optimize`, `compress_level`, `method` and `exact` all change output bytes if left to a default
    that a library version can move.
    """
    rgba = np.zeros((16, 16, 4), dtype=np.uint8)
    rgba[..., 1] = np.arange(16, dtype=np.uint8)[:, None]
    rgba[..., 3] = 255

    for image_format in (ImageFormat.WEBP, ImageFormat.PNG):
        first = encode_image(rgba, image_format=image_format)
        second = encode_image(rgba, image_format=image_format)
        assert first == second, f"{image_format.value} encoding is not reproducible"


async def test_encoding_preserves_the_colour_of_invisible_pixels() -> None:
    """What `exact=True` buys, and why it is set.

    libwebp is free to rewrite the RGB of fully transparent pixels to whatever compresses best. That is
    invisible on screen and fatal to `api-contract.md` §6 rule 2: two encoders, or two versions of one
    encoder, would produce byte-different files from the same array.

    Added after a mutation pass - dropping `exact=True` was caught by nothing, because encoding the same
    array twice in one process is stable either way.
    """
    import io

    from PIL import Image

    rgba = np.zeros((8, 8, 4), dtype=np.uint8)
    rgba[..., 0] = 200
    rgba[..., 1] = 100
    rgba[..., 2] = 50
    rgba[..., 3] = 0  # entirely invisible, and its colour must still survive

    decoded = np.asarray(
        Image.open(io.BytesIO(encode_image(rgba, image_format=ImageFormat.WEBP))).convert("RGBA")
    )

    assert np.array_equal(decoded, rgba), (
        "the encoder rewrote pixels nobody can see, so the same array no longer produces the same bytes"
    )


async def test_lossless_encoding_round_trips_every_pixel() -> None:
    """Lossless means lossless. §6 rule 6 forbids lossy for anything a number is computed from - a lossy
    nodata edge invents pixels that are neither data nor nodata."""
    import io

    from PIL import Image

    rng = np.random.default_rng(0)
    rgba = rng.integers(0, 256, size=(16, 16, 4), dtype=np.uint8)

    for image_format in (ImageFormat.WEBP, ImageFormat.PNG):
        decoded = np.asarray(
            Image.open(io.BytesIO(encode_image(rgba, image_format=image_format))).convert("RGBA")
        )
        assert np.array_equal(decoded, rgba), f"{image_format.value} lost pixels"


async def test_an_encoded_figure_keeps_its_alpha() -> None:
    """`api-contract.md` §6 rule 6 - always with an alpha channel, so nodata is transparent."""
    import io

    from PIL import Image

    rgba = np.zeros((8, 8, 4), dtype=np.uint8)
    rgba[..., 3] = 128

    decoded = Image.open(io.BytesIO(encode_image(rgba, image_format=ImageFormat.WEBP)))

    assert decoded.mode == "RGBA"


async def test_lossy_png_is_refused_rather_than_silently_ignored() -> None:
    """A caller asking for lossy PNG has misunderstood something; giving them lossless would hide it."""
    with pytest.raises(ValueError, match="always lossless"):
        encode_image(
            np.zeros((4, 4, 4), np.uint8), image_format=ImageFormat.PNG, lossy=True
        )


async def test_a_non_rgba_array_is_refused() -> None:
    """A 3-channel array would encode without alpha, and nodata would render as a colour."""
    with pytest.raises(ValueError, match="RGBA"):
        encode_image(np.zeros((4, 4, 3), np.uint8))


async def test_a_colourbar_is_appended_without_touching_the_image() -> None:
    """The drawn colourbar is for the figure pasted into a slide deck, which loses the event and keeps the
    pixels. The machine-readable legend stays mandatory regardless (§6 rule 3)."""
    rgba = np.full((32, 64, 4), 200, dtype=np.uint8)

    composed = draw_colourbar(rgba, ramp=ColorRampId.INDEX_VEGETATION, domain=(-1.0, 1.0), label="NDVI")

    assert composed.shape[1] == 64, "the width is unchanged"
    assert composed.shape[0] > 32, "the panel is appended below"
    assert np.array_equal(composed[:32], rgba), "the image itself is untouched"


async def test_panels_of_different_heights_cannot_be_stacked() -> None:
    """A comparison whose halves are at different scales misrepresents both - which is the thing a
    comparison exists to prevent."""
    with pytest.raises(ValueError, match="different scales"):
        stack_horizontally([np.zeros((10, 10, 4), np.uint8), np.zeros((20, 10, 4), np.uint8)])


async def test_every_fixed_domain_belongs_to_a_real_ramp() -> None:
    """A domain keyed to a ramp that does not exist would never be applied, and the index map drawn with
    that ramp would silently fall back to a data-dependent stretch."""
    for ramp in FIXED_DOMAINS:
        assert ramp in ColorRampId
        low, high = FIXED_DOMAINS[ramp]
        assert low < high


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/unit/test_rendering_math.py -q -p no:warnings              2026-08-31
#
#   .........................                                                [100%]
#   25 passed in 0.64s
#
# No Docker, no network, no storage. Every number is one a person can check by hand.
#
# Checked by mutation, against this file and tests/integration/test_figures.py together:
#
#   A  a fixed stretch falls back to the data          -> test_a_fixed_stretch_without_a_domain_is_refused
#                                                         _not_guessed FAILED
#   B  nodata is coloured instead of transparent       -> test_nodata_becomes_transparent_and_nothing_else
#                                                         _does FAILED
#   C  a different fill under transparent pixels       -> test_the_pixel_under_a_transparent_pixel_is_a
#                                                         _known_value FAILED
#   E  WebP loses `exact=True`                         -> 2 tests FAILED
#   F  a blend takes alpha from the overlay            -> test_blending_an_overlay_preserves_the_base
#                                                         _transparency FAILED
#   K  the render spec drops its stretch method        -> 3 tests FAILED
#
#   D  PNG encoder parameters left to Pillow's default -> *** NOT CAUGHT, and not catchable in-process ***
#
# **D is recorded rather than papered over.** `optimize` and `compress_level` change the encoded bytes
# between Pillow *versions*; within one version they are stable, so encoding the same array twice in one
# process is identical either way. Pinning them guards cross-version drift, and no in-process test can
# observe that. The same category as `_require_in_range` in Phase 1.2 - a guard against a future change,
# proven by reasoning rather than by a test that cannot exist.
#
# C and E survived the FIRST mutation pass, and both were real gaps: "encode the same array twice" passes
# for any deterministic choice, so it proved stability without proving *which* value. Two tests were added -
# the invisible pixel's colour is now pinned to a specific value, and a lossless round-trip proves the
# encoder does not rewrite pixels nobody can see.
#
# All mutated files were restored and byte-compared against their originals.
