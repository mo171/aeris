"""Carries a rendered image to the operator as evidence rather than decoration - with its legend, its provenance and enough to redraw it.

what  : `FigureReadyEvent`, `FigureLegend`, `LegendEntry` and `RenderSpec`.
where : Emitted by `services/rendering/figures.py` on the analysis and assistant streams. Consumed by
        `cli/renderers/figure_writer.py` in Phase 1, and by the frontend's figure panel in Phase 2.
how   : `api-contract.md` §6, and its eight rules are what shapes every field below. Three of them are
        enforced by the model itself rather than left to a caller to remember.

        **`traceStepId` is never null** (rule 1). It is required, and Pydantic refuses the event without
        it. A figure renders the output of a stage; an image with no stage behind it is decoration, and
        decoration is what this product exists not to produce.

        **`renderSpec` is complete enough to reproduce the image** (rule 2). Not a description of the
        render - the *inputs* to it. Bands, stretch bounds and method, ramp, resampling, CRS, and whether
        the mask was applied. `architecture-context.md` §8 rule 13 is why: widen a stretch and a drought
        disappears, so a figure the VLM reasoned over needs its stretch answerable months later.

        **`legend` is data, not pixels** (rule 3). A colourbar may also be drawn into the image - and is -
        but the machine-readable legend is mandatory, because the drawn one cannot be relabelled, searched
        or read by anything but a human. The frontend's own note, quoted in the contract: *a scene of
        coloured geometry that never says what the colours mean is a picture, not evidence.*

        **The image bytes never travel on the stream** (rule 7). `imageUrl` points at storage. A base64
        payload in an SSE frame stalls the stream the trace UI depends on, and the trace is the product's
        credibility signal.
"""

from typing import Literal

from pydantic import Field

from app.constants.color_ramps import ColorRampId
from app.constants.events import AnalysisEventType
from app.constants.figure_kinds import FigureKind, LegendKind
from app.schemas.events.base import StreamEvent


class LegendEntry(StreamEvent):
    """One swatch of a categorical or binary legend."""

    # `#rrggbb`. Hex rather than a ramp position, because the frontend draws the swatch and would
    # otherwise need its own copy of the colormap.
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    label: str


class FigureLegend(StreamEvent):
    """What the colours in a figure mean, as data.

    `domain` for continuous figures, `entries` for categorical and binary ones. Both are declared and both
    are nullable, because Zod's `.nullable()` means "present and possibly null" - dropping the unused one
    with `exclude_none=True` makes the frontend reject the whole event (measured in Phase 0.7).
    """

    kind: LegendKind
    label: str
    color_ramp: ColorRampId

    # `[minimum, maximum]` - the stretch the ramp was spread across. Null for categorical legends.
    domain: list[float] | None = None

    entries: list[LegendEntry] | None = None


class RenderSpec(StreamEvent):
    """Everything needed to redraw this exact image.

    Not documentation. `api-contract.md` §6 rule 2 requires that re-rendering from this spec is
    byte-identical, and `tests/integration/test_figures.py` checks it by doing exactly that.
    """

    scene_ids: list[str] = Field(default_factory=list)

    # Which bands went in, in the order they were combined. `["B08", "B04"]` for NDVI says which is the
    # numerator - and swapping them produces a valid-looking map of the wrong thing.
    bands: list[str] = Field(default_factory=list)

    # `{"min": ..., "max": ..., "method": ...}`. The method matters as much as the numbers: a percentile
    # stretch is data-dependent and a fixed one is not, so only one of them reproduces on other data.
    stretch: dict[str, float | str]

    color_ramp: ColorRampId

    # `architecture-context.md` §8 rule 6 - nearest for categorical rasters and masks, bilinear or cubic
    # for continuous. Recorded because interpolating a class label invents classes, and a figure drawn
    # with the wrong one is wrong in a way only this field reveals.
    resampling: str

    crs: str | None = None

    # How much the source raster was decimated on the way in. **Not in `api-contract.md`'s example, and
    # added here because rule 2 demands completeness and the example is not complete without it.**
    #
    # A figure is a picture for a person, not a raster: a 10980x10980 scene rendered at full resolution is
    # a 480 MB image nobody can open. So figures are drawn from a decimated read - and the factor is part
    # of the render, because two decimations of the same scene produce visibly different images and one of
    # them cannot be reproduced from a spec that does not say which was used.
    #
    # `figure-ready` is agreed and not yet implemented on the frontend (§6), so extending the spec now is
    # a change to a contract nobody parses yet rather than a breaking one.
    decimation: int = Field(default=1, ge=1)

    # Whether the cloud and shadow mask had been applied before the array was rendered (§8 rule 1). Index
    # values over cloud are not meaningful, so a figure drawn without the mask shows the atmosphere.
    mask_applied: bool


class FigureReadyEvent(StreamEvent):
    """`figure-ready`. One finished image, emitted the moment it exists."""

    type: Literal[AnalysisEventType.FIGURE_READY] = AnalysisEventType.FIGURE_READY
    run_id: str
    figure_id: str
    kind: FigureKind

    title: str

    # Built from claim objects, never written by the language model (§6 rule 4). A figure is a third
    # rendering of a validated result, never a fourth source of facts.
    caption: str | None = None

    image_url: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    # **Never null** - §6 rule 1. Required, so the model refuses the event rather than the reviewer
    # catching it.
    trace_step_id: str

    # Which claims this figure supports. Empty is allowed and means a diagnostic figure - a histogram
    # explaining a threshold, a co-registration residual - which supports no claim and is still worth
    # showing.
    claim_ids: list[str] = Field(default_factory=list)

    legend: FigureLegend
    render_spec: RenderSpec

    # At most one per run (§6 rule 8): the figure the reference surface shows without being asked. More
    # than one primary means the run did not decide what it was answering.
    is_primary: bool = False
