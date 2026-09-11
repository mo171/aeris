"""Names the seven spectral indices, what each one is made of, and what its numbers mean - so no service invents a band or a threshold.

what  : `SpectralIndex`, the band roles each index consumes in formula order, the EVI and SAVI
        coefficients, the interpretation bands that turn a value into a word, and the phrase table that
        turns an operator's question into an index and a value range.
where : Read by `services/spectral/` (S12) and by the S15 node that thresholds an index into a mask.
        Transcribed from `frontend/lib/constants/overlays/spectral-indices.ts`, which is itself transcribed
        from PDF §3.3 (pp.12-13). The ids are the frontend's `SPECTRAL_INDEX_IDS`, exactly.
how   : **The interpretation bands are the load-bearing part.** "Unhealthy vegetation" has to become a
        number range somewhere, and if that happens inside a service it happens differently in two
        services. Here it is stated once, cited to the document both sides were specified against, and
        the frontend's legend and the backend's mask agree on what 0.3 means.

        `QUERY_TARGETS` is the deterministic half of routing (PDF p.24): a phrase chooses an index and a
        range from a table. Phase 1.8 replaces the phrase match with a classifier and keeps the table -
        a wrong phrase match is visible and recoverable, a hallucinated threshold is neither.

        Coefficients are stated with their source. EVI's are MODIS-derived and empirical (PDF §3.3.2);
        SAVI's `L = 0.5` is "typical" rather than correct (§3.3.3), and both are carried into the result
        so a report can say which were used.
"""

from enum import StrEnum
from typing import Final, NamedTuple

from app.constants.raster import BandRole


class SpectralIndex(StrEnum):
    """One of the seven closed-form indices. The value is the frontend's `SpectralIndexId`."""

    NDVI = "ndvi"
    EVI = "evi"
    SAVI = "savi"
    NDWI = "ndwi"
    MNDWI = "mndwi"
    NDBI = "ndbi"
    NBR = "nbr"


# Index -> the band roles its formula consumes, in the order the formula names them. The formula asks for
# roles, and the sensor table (`constants/raster.py`) answers with a band, which is what keeps the
# arithmetic sensor-agnostic: NDVI is (NIR - RED) / (NIR + RED) on any instrument that has both.
INDEX_BAND_ROLES: Final[dict[SpectralIndex, tuple[BandRole, ...]]] = {
    SpectralIndex.NDVI: (BandRole.NEAR_INFRARED, BandRole.RED),
    SpectralIndex.EVI: (BandRole.NEAR_INFRARED, BandRole.RED, BandRole.BLUE),
    SpectralIndex.SAVI: (BandRole.NEAR_INFRARED, BandRole.RED),
    SpectralIndex.NDWI: (BandRole.GREEN, BandRole.NEAR_INFRARED),
    SpectralIndex.MNDWI: (BandRole.GREEN, BandRole.SHORTWAVE_INFRARED_1),
    SpectralIndex.NDBI: (BandRole.SHORTWAVE_INFRARED_1, BandRole.NEAR_INFRARED),
    SpectralIndex.NBR: (BandRole.NEAR_INFRARED, BandRole.SHORTWAVE_INFRARED_2),
}

# Every index is drawn over its algebraic domain rather than its own extremes (constants/color_ramps.py,
# FIXED_DOMAINS): two dates are only comparable on one scale.
INDEX_DOMAIN: Final[tuple[float, float]] = (-1.0, 1.0)

# EVI = G * (NIR - RED) / (NIR + C1*RED - C2*BLUE + L). MODIS coefficients, PDF §3.3.2 equation (2).
EVI_GAIN: Final[float] = 2.5
EVI_RED_COEFFICIENT: Final[float] = 6.0
EVI_BLUE_COEFFICIENT: Final[float] = 7.5
EVI_CANOPY_BACKGROUND: Final[float] = 1.0

# SAVI = (1 + L) * (NIR - RED) / (NIR + RED + L). PDF §3.3.3 equation (3) calls 0.5 "typical", and the
# frontend's limitations text calls it "a typical value, not a correct one" - carried into every result.
SAVI_SOIL_BRIGHTNESS: Final[float] = 0.5


class InterpretationBand(NamedTuple):
    """One readable range of an index. `lower` inclusive, `upper` exclusive except at the domain's top."""

    lower: float
    upper: float
    label: str


# Index -> its interpretation bands, contiguous and covering [-1, 1]. The labels are the frontend's, so a
# mask named "Sparse vegetation" here is the same thing the legend calls "Sparse vegetation" there.
INTERPRETATION_BANDS: Final[dict[SpectralIndex, tuple[InterpretationBand, ...]]] = {
    SpectralIndex.NDVI: (
        InterpretationBand(-1.0, 0.0, "Water"),
        InterpretationBand(0.0, 0.2, "Bare or built"),
        InterpretationBand(0.2, 0.4, "Sparse vegetation"),
        InterpretationBand(0.4, 1.0, "Dense healthy vegetation"),
    ),
    SpectralIndex.EVI: (
        InterpretationBand(-1.0, 0.2, "Non-vegetated"),
        InterpretationBand(0.2, 0.5, "Moderate vigour"),
        InterpretationBand(0.5, 1.0, "High vigour"),
    ),
    SpectralIndex.SAVI: (
        InterpretationBand(-1.0, 0.1, "Bare"),
        InterpretationBand(0.1, 0.35, "Sparse cover"),
        InterpretationBand(0.35, 1.0, "Established cover"),
    ),
    SpectralIndex.NDWI: (
        InterpretationBand(-1.0, 0.0, "Land"),
        InterpretationBand(0.0, 0.3, "Wet or mixed"),
        InterpretationBand(0.3, 1.0, "Open water"),
    ),
    SpectralIndex.MNDWI: (
        InterpretationBand(-1.0, 0.0, "Land"),
        InterpretationBand(0.0, 0.3, "Shallow or turbid"),
        InterpretationBand(0.3, 1.0, "Open water"),
    ),
    SpectralIndex.NDBI: (
        InterpretationBand(-1.0, -0.1, "Vegetated or water"),
        InterpretationBand(-0.1, 0.1, "Mixed"),
        InterpretationBand(0.1, 1.0, "Built-up likelihood"),
    ),
    # Single-date NBR has no accepted class breaks; burn severity is a property of the pre/post
    # *difference* (PDF §3.3.7, dNBR), which needs the temporal graph. One band, so a map can still be
    # drawn and read, and no phrase below targets it.
    SpectralIndex.NBR: (InterpretationBand(-1.0, 1.0, "Normalised burn ratio"),),
}


class QueryTarget(NamedTuple):
    """What a phrase asks for: an index, and the value range the mask should cover."""

    index: SpectralIndex
    lower: float
    upper: float
    label: str


# Phrase -> target. Matched as a whole phrase, longest match first, case-insensitively, so "unhealthy
# vegetation" wins over "vegetation" when both are present. Ranges are unions of the interpretation bands
# above, never numbers invented here.
QUERY_TARGETS: Final[dict[str, QueryTarget]] = {
    "unhealthy vegetation": QueryTarget(SpectralIndex.NDVI, 0.2, 0.4, "Sparse vegetation"),
    "stressed vegetation": QueryTarget(SpectralIndex.NDVI, 0.2, 0.4, "Sparse vegetation"),
    "sparse vegetation": QueryTarget(SpectralIndex.NDVI, 0.2, 0.4, "Sparse vegetation"),
    "healthy vegetation": QueryTarget(SpectralIndex.NDVI, 0.4, 1.0, "Dense healthy vegetation"),
    "dense vegetation": QueryTarget(SpectralIndex.NDVI, 0.4, 1.0, "Dense healthy vegetation"),
    "vegetation": QueryTarget(SpectralIndex.NDVI, 0.2, 1.0, "Vegetation"),
    "vegetation cover": QueryTarget(SpectralIndex.SAVI, 0.1, 1.0, "Vegetation cover"),
    "vegetation vigour": QueryTarget(SpectralIndex.EVI, 0.2, 1.0, "Vegetation vigour"),
    "open water": QueryTarget(SpectralIndex.NDWI, 0.3, 1.0, "Open water"),
    "water bodies": QueryTarget(SpectralIndex.NDWI, 0.0, 1.0, "Water"),
    "water": QueryTarget(SpectralIndex.NDWI, 0.0, 1.0, "Water"),
    "flood extent": QueryTarget(SpectralIndex.MNDWI, 0.0, 1.0, "Water"),
    "flood": QueryTarget(SpectralIndex.MNDWI, 0.0, 1.0, "Water"),
    "built-up": QueryTarget(SpectralIndex.NDBI, 0.1, 1.0, "Built-up likelihood"),
    "built up": QueryTarget(SpectralIndex.NDBI, 0.1, 1.0, "Built-up likelihood"),
    "buildings": QueryTarget(SpectralIndex.NDBI, 0.1, 1.0, "Built-up likelihood"),
    "urban": QueryTarget(SpectralIndex.NDBI, 0.1, 1.0, "Built-up likelihood"),
}

# A bare index name in a question ("show me the ndwi") draws the map with no mask target.
INDEX_NAMES: Final[dict[str, SpectralIndex]] = {member.value: member for member in SpectralIndex}

# The versions the `index-engine` and `geospatial-engine` model ids carry on trace steps and, from 1.5, on
# claims. Bumped when a formula, a coefficient or the area method changes, because a claim made under
# the old version is not the same measurement.
INDEX_ENGINE_VERSION: Final[str] = "1.4.0"
GEOSPATIAL_ENGINE_VERSION: Final[str] = "1.4.0"
