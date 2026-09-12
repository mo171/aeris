"""The Phase 1.2.1 gate: three figures, each with a legend, a non-null trace step and a spec that redraws it byte-identically.

what  : Tests over `services/rendering/figures.py` and `cli/renderers/figure_writer.py`.
where : `tests/integration/`. Needs `docker compose up -d minio` - a figure that is not in storage is not
        one the frontend can load, so the upload is part of what is being tested.
how   : Small synthetic arrays rather than a real scene. What is under test is the *render contract*, and
        a 16x16 gradient exercises the stretch, the ramp, the alpha and the encoder exactly as a 10980x10980
        band does, in milliseconds instead of minutes.

        Three of these are the gate itself, and each corresponds to a rule in `api-contract.md` §6:

        - **`test_re_rendering_from_the_spec_is_byte_identical`** (rule 2). The claim the whole render spec
          exists to support - and the reproduction is actually performed, not merely field-checked.
        - **`test_a_figure_without_a_trace_step_cannot_be_built`** (rule 1). An image with no stage behind
          it is decoration, and decoration is what this product exists not to produce.
        - **`test_a_figure_is_fetchable_under_a_key_the_event_alone_can_derive`** (rule 7). The bytes never
          travel on the stream, so the event's identifiers have to be enough to find the object - which is
          exactly what breaks silently and surfaces in Phase 2 as an image that will not load.
"""

import numpy as np
import pytest
from pydantic import ValidationError

from app.cli.renderers.figure_writer import FigureWriter
from app.constants.color_ramps import ColorRampId
from app.constants.figure_kinds import FigureKind, LegendKind
from app.constants.storage import Bucket
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.lib import storage
from app.lib.exceptions import InvalidRequestError
from app.schemas.events import parse_event, serialise_event
from app.services.rendering.figures import (
    figure_object_key,
    render_from_spec,
    render_index_map,
    render_mask_overlay,
    render_rgb_composite,
)


def gradient(size: int = 32) -> np.ndarray:
    """A reflectance-shaped array with a nodata corner, so alpha is exercised."""
    array = np.linspace(0.02, 0.45, size * size).reshape(size, size).astype(np.float32)
    array[0, 0] = np.nan
    return array


def index_array(size: int = 32) -> np.ndarray:
    """An NDVI-shaped array spanning the full [-1, 1] domain, with a nodata corner."""
    array = np.linspace(-0.9, 0.9, size * size).reshape(size, size).astype(np.float32)
    array[0, 0] = np.nan
    return array


def a_run_id() -> str:
    return new_identifier(IdentifierPrefix.RUN)


def a_trace_step_id() -> str:
    return new_identifier(IdentifierPrefix.TRACE_STEP)


# --- The gate --------------------------------------------------------------------------------------------


@pytest.mark.integration
async def test_re_rendering_from_the_spec_is_byte_identical() -> None:
    """**The gate.** `api-contract.md` §6 rule 2, performed rather than asserted.

    A figure the VLM reasoned over is part of the evidence chain, so "which stretch was that drawn with"
    has to be answerable months later - and the only way to keep that honest is for the reproduction to be
    a real code path a test actually runs.
    """
    index = index_array()

    figure = await render_index_map(
        index, run_id=a_run_id(), trace_step_id=a_trace_step_id(), title="NDVI"
    )
    redrawn = await render_from_spec(index, figure.event.render_spec, label="NDVI")

    assert redrawn == figure.image_bytes, (
        "the recorded renderSpec does not reproduce the image, so it is missing something the render "
        "depends on"
    )


@pytest.mark.integration
async def test_a_figure_without_a_trace_step_cannot_be_built() -> None:
    """§6 rule 1: `traceStepId` is never null.

    Enforced by the model rather than by a reviewer - a figure renders the output of a stage, and one with
    no stage behind it is decoration.
    """
    with pytest.raises(ValidationError, match="trace_step_id|traceStepId"):
        from app.schemas.events.figure import FigureLegend, FigureReadyEvent, RenderSpec

        FigureReadyEvent(
            run_id="run_x",
            figure_id="fig_x",
            kind=FigureKind.INDEX_MAP,
            title="No stage behind this",
            image_url="/api/v1/figures/fig_x.webp",
            width=10,
            height=10,
            legend=FigureLegend(
                kind=LegendKind.CONTINUOUS, label="NDVI", color_ramp=ColorRampId.INDEX_VEGETATION
            ),
            render_spec=RenderSpec(
                stretch={"min": -1.0, "max": 1.0, "method": "fixed"},
                color_ramp=ColorRampId.INDEX_VEGETATION,
                resampling="none",
                mask_applied=False,
            ),
        )


@pytest.mark.integration
async def test_a_figure_is_fetchable_under_a_key_the_event_alone_can_derive() -> None:
    """§6 rule 7: the image bytes never travel on the stream.

    So the event's identifiers must be enough to find the object. Derived here exactly as
    `figure_writer.py` derives it - if the two ever disagree, the frontend gets an image that will not load
    and nothing upstream reports a problem.
    """
    figure = await render_index_map(
        index_array(), run_id=a_run_id(), trace_step_id=a_trace_step_id(), title="NDVI"
    )
    event = figure.event

    suffix = event.image_url.rsplit(".", 1)[-1]
    key = figure_object_key(event.run_id, event.figure_id, suffix)
    payload = await storage.get_object(Bucket.FIGURES, key)

    assert payload == figure.image_bytes


@pytest.mark.integration
async def test_the_figure_writer_puts_a_run_s_figures_on_disk(tmp_path, monkeypatch) -> None:
    """What makes the capability exercisable in Phase 1 with no browser and no route.

    The writer *downloads* rather than being handed the bytes - the same thing the frontend will do - so a
    figure uploaded under an unreachable key fails here rather than in a browser in Phase 2.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "pipeline_journal_directory", tmp_path)

    run_id = a_run_id()
    figure = await render_index_map(
        index_array(), run_id=run_id, trace_step_id=a_trace_step_id(), title="NDVI"
    )

    writer = FigureWriter(run_id)
    await writer(figure.event)

    assert len(writer.written) == 1
    assert writer.written[0].read_bytes() == figure.image_bytes
    assert writer.written[0].parent.name == "figures"


# --- The three figure kinds ------------------------------------------------------------------------------


@pytest.mark.integration
async def test_an_index_map_is_drawn_over_its_fixed_domain() -> None:
    """A normalised index is always drawn over [-1, 1], never over its own extremes.

    Two figures are only comparable if they share a scale; stretching each to its own data makes every
    image look equally varied and hides the change between them.
    """
    figure = await render_index_map(
        index_array(), run_id=a_run_id(), trace_step_id=a_trace_step_id(), title="NDVI"
    )

    assert figure.event.render_spec.stretch == {"min": -1.0, "max": 1.0, "method": "fixed"}
    assert figure.event.legend.domain == [-1.0, 1.0]
    assert figure.event.legend.kind is LegendKind.CONTINUOUS
    # The colourbar panel is appended, so the figure is taller than the array it renders.
    assert figure.event.height > 32


@pytest.mark.integration
async def test_an_index_map_with_no_fixed_domain_is_refused() -> None:
    """A ramp without a domain would be stretched to its own data, producing an incomparable figure.

    Refused rather than silently falling back, because the caller believes they are getting a comparable
    image and nothing about the result would say otherwise.
    """
    with pytest.raises(InvalidRequestError, match="no fixed domain"):
        await render_index_map(
            index_array(),
            run_id=a_run_id(),
            trace_step_id=a_trace_step_id(),
            title="Backscatter",
            ramp=ColorRampId.SAR_GRAYSCALE,
        )


@pytest.mark.integration
async def test_a_composite_is_transparent_where_any_band_is_missing() -> None:
    """A pixel with two of three bands is not a colour - it is a colour with one channel invented."""
    red, green, blue = gradient(), gradient(), gradient()
    blue[5, 5] = np.nan  # missing in one band only

    figure = await render_rgb_composite(
        red, green, blue, run_id=a_run_id(), trace_step_id=a_trace_step_id(), title="True colour"
    )

    assert figure.rgba[5, 5, 3] == 0, "one missing band makes the pixel transparent"
    assert figure.rgba[0, 0, 3] == 0, "the shared nodata corner is transparent too"
    assert figure.rgba[20, 20, 3] == 255


@pytest.mark.integration
async def test_a_composite_records_every_bands_stretch() -> None:
    """Three bands are stretched independently, so a spec recording one of the three cannot redraw it.

    They are stretched separately because their dynamic ranges genuinely differ; a shared stretch produces
    a colour cast, which on a true-colour image reads as a property of the ground.
    """
    figure = await render_rgb_composite(
        gradient(), gradient() * 0.5, gradient() * 0.25,
        run_id=a_run_id(), trace_step_id=a_trace_step_id(), title="True colour",
    )

    stretch = figure.event.render_spec.stretch
    assert stretch["method"] == "percentile"
    assert str(stretch["perBand"]).count(";") == 2, "one entry per band"


@pytest.mark.integration
async def test_a_mask_overlay_tints_only_what_the_mask_marks() -> None:
    """The check that catches an inverted mask - which renders as a professional-looking wrong answer.

    Measured on a real scene: 17.1% of pixels tinted, exactly matching the mask, and zero outside it.
    """
    base = np.zeros((32, 32, 4), dtype=np.uint8)
    base[..., :3] = 128
    base[..., 3] = 255
    mask = np.zeros((32, 32), dtype=bool)
    mask[8:16, 8:16] = True

    figure = await render_mask_overlay(
        mask, base, run_id=a_run_id(), trace_step_id=a_trace_step_id(),
        title="Vegetation", label="NDVI > 0.3",
    )

    tinted = (figure.rgba[..., :3] != base[..., :3]).any(axis=-1)
    assert np.array_equal(tinted, mask), "the tint must fall exactly on the mask and nowhere else"
    assert figure.event.legend.kind is LegendKind.BINARY
    # §8 rule 6 - a mask holds class labels, so interpolating between 0 and 1 invents a class.
    assert figure.event.render_spec.resampling == "nearest"


@pytest.mark.integration
async def test_a_mask_of_the_wrong_shape_is_refused() -> None:
    """A mask drawn over a differently-shaped base marks the wrong ground."""
    base = np.zeros((32, 32, 4), dtype=np.uint8)

    with pytest.raises(ValueError, match="marks the wrong ground"):
        await render_mask_overlay(
            np.zeros((16, 16), dtype=bool), base,
            run_id=a_run_id(), trace_step_id=a_trace_step_id(), title="x", label="y",
        )


# --- The wire --------------------------------------------------------------------------------------------


@pytest.mark.integration
async def test_a_figure_event_survives_the_wire_round_trip() -> None:
    """camelCase out, the same event back. The two rules 0.7 measured: `by_alias` and `mode="json"`."""
    figure = await render_index_map(
        index_array(), run_id=a_run_id(), trace_step_id=a_trace_step_id(), title="NDVI"
    )

    payload = serialise_event(figure.event)

    assert payload["type"] == "figure-ready"
    assert "traceStepId" in payload and "renderSpec" in payload
    assert "trace_step_id" not in payload
    assert payload["legend"]["colorRamp"] == "index-vegetation"

    assert parse_event(payload) == figure.event


@pytest.mark.integration
async def test_a_nullable_legend_field_stays_present_when_it_is_null() -> None:
    """Zod's `.nullable()` means "present and possibly null".

    Dropping the unused one with `exclude_none=True` makes the frontend reject the whole event - measured
    against `nextCursor` in Phase 0.7, and the same rule applies here to `domain` and `entries`.
    """
    figure = await render_index_map(
        index_array(), run_id=a_run_id(), trace_step_id=a_trace_step_id(), title="NDVI"
    )

    payload = serialise_event(figure.event)

    assert "entries" in payload["legend"], "a continuous legend still declares its (null) entries"
    assert payload["legend"]["entries"] is None


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/integration/test_figures.py -q -p no:warnings              2026-08-31
#
#   ............                                                             [100%]
#   12 passed in 2.14s
#
# Needs `docker compose up -d minio`.
#
# **The gate, end to end**, from the four-band Sentinel-2 subset in notebooks/01_remote_sensing/data:
#
#   $ uv run aeris figures notebooks/01_remote_sensing/data --level L2A
#
#   rgb-composite   1066x1120  2518 KB   legend categorical  ramp true-color
#   index-map       1066x1176  1444 KB   legend continuous   ramp index-vegetation  domain [-1, 1]
#   mask-overlay    1066x1120  2554 KB   legend binary       ramp mask-amber        resampling nearest
#   vegetated: 17.1% of the scene
#
#   re-rendering the index map from its recorded renderSpec... byte-identical  1,478,754 bytes
#   3 figures written to runs/<run_id>/figures/
#
# Each carries a non-null traceStepId, a machine-readable legend and a complete renderSpec; each is in
# MinIO and on disk. The index map is 56 px taller than its array because the colourbar panel is appended.
#
# The mask overlay was checked numerically rather than by eye, after a contact sheet made it look as though
# the tint fell on water: 17.1% of pixels tinted, exactly matching the mask, **zero outside it**, mean NDVI
# 0.428 inside against 0.009 outside. Amber over green vegetation simply reads brown at thumbnail scale.
#
# Checked by mutation:
#
#   G  an index map stretched to its own data      -> 2 tests FAILED, including the byte-identical gate
#   H  a composite opaque where a band is missing  -> test_a_composite_is_transparent_where_any_band_is
#                                                     _missing FAILED
#   I  the mask overlay inverted                   -> test_a_mask_overlay_tints_only_what_the_mask_marks
#                                                     FAILED
#   J  the mask resampling claim becomes bilinear  -> the same test FAILED
#   L  per-band stretch dropped from the spec      -> test_a_composite_records_every_bands_stretch FAILED
#
# G is the one worth noting: stretching an index to its own data breaks the *reproduction* test as well as
# the domain test, because a data-dependent stretch cannot be redrawn from a spec on a different array.
#
# All mutated files were restored and byte-compared against their originals.
