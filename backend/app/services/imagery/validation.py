"""Refuses a scene that would produce a confident wrong number, and says which measurement made it refuse.

what  : `QualityReport`, `RasterProblem`, `assess_raster()` and `require_analysable()`. Stages S4-S5.
where : Called by the ingest node after `metadata.inspect_raster`, and by Phase 1.4 before any index is
        computed.
how   : `architecture-context.md` §8 opens with "a confident wrong number is worse than an error". This
        file is where that becomes a refusal.

        **Measurement and policy are separated, and the separation is the design.** `math/` returns
        numbers and never decides; this module compares those numbers against the thresholds in
        `constants/raster.py` and decides. That is what lets a threshold be argued about without touching
        the arithmetic, and what lets the arithmetic be tested against arrays whose answers are known.

        **Severity, not a boolean.** A scene 60% covered in cloud is not the same as a scene with no CRS.
        The first is a judgement call the operator may want to override for a demo; the second cannot be
        placed on the globe at all and nothing downstream can proceed. `Severity.REFUSES` is what
        `require_analysable` raises on; `Severity.WARNS` is reported and carried into the trace, so it
        reaches the report rather than being swallowed.

        **The read is decimated.** A full 10 m band is 120 megapixels and 240 MB; reading all of it to
        answer "is this mostly nodata" is minutes for a figure that a regular decimated sample gives to
        within a fraction of a percent. Regular rather than random, so the same scene reports the same
        numbers twice - a quality report that moves between runs cannot be used to decide whether the
        scene changed or the measurement did.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import rasterio
from rasterio.enums import Resampling

from app.constants.raster import (
    MAXIMUM_NODATA_FRACTION,
    MINIMUM_DISTINCT_VALUES,
    QUALITY_SAMPLE_MAXIMUM_PIXELS,
    ProcessingLevel,
)
from app.lib.exceptions import ConflictError
from app.services.imagery.math.quality_statistics import (
    BandStatistics,
    decimation_step_for,
    measure_band,
)
from app.services.imagery.metadata import RasterMetadata

logger = logging.getLogger(__name__)


class Severity(StrEnum):
    """How much a problem matters.

    Two levels rather than a boolean, because the two demand different behaviour and collapsing them means
    either refusing on things a demo could live with, or proceeding on things that cannot work at all.
    """

    # Reported, carried into the trace and into the report. The operator decides.
    WARNS = "warns"

    # Nothing downstream can proceed. `require_analysable` raises.
    REFUSES = "refuses"


@dataclass(frozen=True, slots=True)
class RasterProblem:
    """One thing wrong with a scene, with the measurement that found it."""

    code: str
    severity: Severity
    message: str

    # The number that triggered it, and the limit it crossed. Present so the message is never the only
    # record: "62% nodata" is actionable and "too much nodata" is not.
    measured: float | None = None
    limit: float | None = None


@dataclass(frozen=True, slots=True)
class QualityReport:
    """What S4-S5 found. Produced for every scene, including good ones."""

    metadata: RasterMetadata
    statistics: BandStatistics
    problems: list[RasterProblem] = field(default_factory=list)

    # How much the read was decimated to produce `statistics`. Recorded because every figure above was
    # measured over a sample, and a caller quoting them should be able to say over what.
    decimation_step: int = 1

    @property
    def refusals(self) -> list[RasterProblem]:
        return [problem for problem in self.problems if problem.severity is Severity.REFUSES]

    @property
    def warnings(self) -> list[RasterProblem]:
        return [problem for problem in self.problems if problem.severity is Severity.WARNS]

    @property
    def is_analysable(self) -> bool:
        """Whether anything downstream may proceed. Warnings do not block; refusals do."""
        return not self.refusals


async def assess_raster(metadata: RasterMetadata) -> QualityReport:
    """S4-S5: measure a scene and list what is wrong with it. Never raises on a bad scene.

    Returning a report rather than raising is deliberate: `aeris ingest --inspect` has to be able to
    describe a broken file, and an operator debugging a failed download needs the numbers more than they
    need an exception.
    """
    statistics, step = await asyncio.to_thread(_measure_decimated, metadata)

    problems: list[RasterProblem] = []
    problems.extend(_check_georeferencing(metadata))
    problems.extend(_check_coverage(statistics))
    problems.extend(_check_information_content(statistics))
    problems.extend(_check_processing_level(metadata))

    report = QualityReport(
        metadata=metadata, statistics=statistics, problems=problems, decimation_step=step
    )

    logger.info(
        "raster assessed",
        extra={
            "path": str(metadata.path),
            "analysable": report.is_analysable,
            "refusals": [problem.code for problem in report.refusals],
            "warnings": [problem.code for problem in report.warnings],
            "nodata_fraction": round(statistics.nodata_fraction, 4),
        },
    )
    return report


async def require_analysable(metadata: RasterMetadata) -> QualityReport:
    """Assess, and raise if anything refuses.

    The form every pipeline node uses. `ConflictError` rather than `InvalidRequestError`: the request is
    well formed, and it is the *state of the data* that forbids the action - the same distinction
    `require_trainable` draws in `services/datasets/catalogue.py`.
    """
    report = await assess_raster(metadata)
    if not report.is_analysable:
        reasons = "; ".join(problem.message for problem in report.refusals)
        raise ConflictError(
            f"{metadata.path.name} cannot be analysed: {reasons}",
            details={
                "path": str(metadata.path),
                "codes": [problem.code for problem in report.refusals],
            },
        )
    return report


def _measure_decimated(metadata: RasterMetadata) -> tuple[BandStatistics, int]:
    """Read a decimated sample and measure it. Sync - it is what `to_thread` is handed."""
    step = decimation_step_for(
        width=metadata.width, height=metadata.height, maximum_pixels=QUALITY_SAMPLE_MAXIMUM_PIXELS
    )

    with rasterio.open(metadata.path) as source:
        sampled_width = max(1, metadata.width // step)
        sampled_height = max(1, metadata.height // step)
        # **Nearest, always, even for continuous data.** This read is for *measuring*, not for display:
        # averaging during decimation would smooth away exactly the extremes the percentiles exist to find,
        # and would blend nodata into its neighbours - turning a hard edge into a band of plausible values
        # that are neither data nor nodata (§8 rule 4).
        array = source.read(
            1, out_shape=(sampled_height, sampled_width), resampling=Resampling.nearest
        )

    return measure_band(array.astype(np.float64, copy=False), metadata.nodata), step


def _check_georeferencing(metadata: RasterMetadata) -> list[RasterProblem]:
    """The checks that decide whether the scene can be placed on the Earth at all."""
    problems: list[RasterProblem] = []

    if not metadata.has_usable_crs:
        # The failure that costs a day when it is not caught. A GeoTIFF with no CRS opens cleanly, reads
        # cleanly, and reprojects to nothing - the tile server emits empty tiles with no error anywhere,
        # so the symptom is a blank map rather than a message.
        problems.append(
            RasterProblem(
                code="NO_CRS",
                severity=Severity.REFUSES,
                message=(
                    "The raster declares no coordinate reference system, so it cannot be reprojected or "
                    "placed on the globe. Tiles would render empty with no error."
                ),
            )
        )
    elif not metadata.is_projected:
        # Degrees, not metres. Usable for display and never for area: §8 rule 3 requires an equal-area
        # projection for hectares, and a degree is a different distance at every latitude.
        problems.append(
            RasterProblem(
                code="GEOGRAPHIC_CRS",
                severity=Severity.WARNS,
                message=(
                    f"{metadata.crs} is geographic, so its units are degrees. Any area computed from it "
                    "must reproject to an equal-area CRS first (architecture-context.md §8 rule 3)."
                ),
            )
        )

    if metadata.nodata is None:
        # Not a refusal - plenty of valid rasters cover their full extent. But every downstream mask has to
        # treat *nothing* as nodata, which is a different and stronger claim than "the nodata value is 0".
        problems.append(
            RasterProblem(
                code="NO_NODATA_VALUE",
                severity=Severity.WARNS,
                message=(
                    "The raster declares no nodata value. Every pixel will be treated as valid; if the "
                    "scene has empty margins they will be measured as data."
                ),
            )
        )

    return problems


def _check_coverage(statistics: BandStatistics) -> list[RasterProblem]:
    """How much of the raster actually carries data."""
    if statistics.is_empty:
        return [
            RasterProblem(
                code="NO_VALID_PIXELS",
                severity=Severity.REFUSES,
                message="Every pixel is nodata. Nothing can be measured from this raster.",
                measured=1.0,
                limit=MAXIMUM_NODATA_FRACTION,
            )
        ]

    if statistics.nodata_fraction > MAXIMUM_NODATA_FRACTION:
        return [
            RasterProblem(
                code="EXCESSIVE_NODATA",
                severity=Severity.REFUSES,
                message=(
                    f"{statistics.nodata_fraction:.1%} of the raster is nodata. Statistics over the "
                    f"remainder would be reported as though they described the whole area."
                ),
                measured=statistics.nodata_fraction,
                limit=MAXIMUM_NODATA_FRACTION,
            )
        ]

    return []


def _check_information_content(statistics: BandStatistics) -> list[RasterProblem]:
    """Whether the raster carries information, or is a plausible-looking constant."""
    if statistics.is_empty:
        return []

    if statistics.distinct_value_count < MINIMUM_DISTINCT_VALUES:
        return [
            RasterProblem(
                code="CONSTANT_RASTER",
                severity=Severity.REFUSES,
                message=(
                    f"The raster holds essentially one value ({statistics.minimum:g}). That is a failed "
                    "download or a band read at the wrong index - it renders as a flat image and produces "
                    "a uniform index map, which reads as a finding rather than a fault."
                ),
                measured=float(statistics.distinct_value_count),
                limit=float(MINIMUM_DISTINCT_VALUES),
            )
        ]

    return []


def _check_processing_level(metadata: RasterMetadata) -> list[RasterProblem]:
    """Whether band arithmetic is permitted on this scene at all.

    `architecture-context.md` §8 rule 5. A warning rather than a refusal here, because S4 does not know
    whether an index is going to be computed - Phase 1.4 refuses at the point the arithmetic is asked for,
    which is where the refusal is actionable.
    """
    if metadata.processing_level is ProcessingLevel.UNKNOWN:
        return [
            RasterProblem(
                code="UNKNOWN_PROCESSING_LEVEL",
                severity=Severity.WARNS,
                message=(
                    "The processing level could not be read from the path. Band arithmetic is refused on "
                    "an unknown level: an index over uncorrected digital numbers is a different quantity "
                    "wearing the same name (architecture-context.md §8 rule 5)."
                ),
            )
        ]

    if metadata.processing_level is ProcessingLevel.L1C:
        return [
            RasterProblem(
                code="UNCORRECTED_REFLECTANCE",
                severity=Severity.WARNS,
                message=(
                    "This is L1C top-of-atmosphere radiance, not surface reflectance. Indices computed "
                    "over it are not comparable with L2A, and a temporal pair mixing the two produces a "
                    "change map of the atmosphere."
                ),
            )
        ]

    return []
