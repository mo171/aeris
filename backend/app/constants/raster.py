"""Names the band, format and quality vocabularies the raster engine works in, so no service invents a threshold or a band index.

what  : `SpectralBand`, `BandRole`, `ProcessingLevel`, the Sentinel-2 band table, the COG profile, the
        tiling defaults and the quality thresholds.
where : Read by `services/imagery/` (S1-S6, S11), and from 1.4 by the spectral index engine, which asks
        this file which band is red rather than being told `B04` by a caller.
how   : Three groups of constants, each of which exists because getting it wrong produces a plausible
        number rather than an error.

        **The band table.** `B04` is red on Sentinel-2 and band 3 on Landsat; a hardcoded index is how an
        NDVI silently becomes an NDWI. Every band here carries its centre wavelength and its native
        resolution, because `architecture-context.md` §8 rule 6 makes resampling method depend on what the
        band *is*, and a 20 m band read as though it were 10 m is off by a factor of two in area.

        **The COG profile.** A Cloud-Optimised GeoTIFF is an ordinary GeoTIFF whose tiles and overviews are
        arranged so a reader can fetch one tile with one HTTP range request. Get the internal tile size or
        the overview levels wrong and it still opens, still renders, and costs forty round trips per tile -
        the failure is a slow globe, not a broken one, which is why the profile is stated once here.

        **The quality thresholds.** `architecture-context.md` §8 rule 4: nodata is never zero. These are the
        limits at which S4/S5 refuse rather than warn, and they are configuration-shaped values kept as
        constants because they are properties of the *domain* - what fraction of cloud makes a scene
        useless is not a per-machine setting.
"""

from enum import StrEnum
from typing import Final


class ProcessingLevel(StrEnum):
    """How far a scene has been processed. Checked at S3 and carried through every later stage.

    `architecture-context.md` §8 rule 5: band arithmetic runs on calibrated reflectance, never on digital
    numbers. An NDVI over L1C top-of-atmosphere values is a different quantity wearing the same name - and
    nothing in the pixels says which one it is, so the level is read from metadata and carried in state.
    """

    # Sentinel-2 top-of-atmosphere radiance. Uncorrected for the atmosphere.
    L1C = "L1C"

    # Sentinel-2 surface reflectance, atmospherically corrected. What indices may be computed on.
    L2A = "L2A"

    # Sentinel-1 Ground Range Detected, radiometrically terrain corrected.
    GRD = "GRD"

    # Read from a file that declares no level - a plain GeoTIFF someone uploaded. Not an error, but every
    # index over it is a refusal until a human says what it is.
    UNKNOWN = "unknown"


class BandRole(StrEnum):
    """What a band is *for*, independent of which satellite produced it.

    The indirection that keeps `math/` sensor-agnostic: an NDVI is `(NIR - RED) / (NIR + RED)` whatever
    instrument the bands came from, so the arithmetic asks for `RED` and the sensor table answers `B04`.
    Hardcoding `B04` into the index engine is what makes it silently wrong on Landsat.
    """

    COASTAL = "coastal"
    BLUE = "blue"
    GREEN = "green"
    RED = "red"
    RED_EDGE_1 = "red-edge-1"
    RED_EDGE_2 = "red-edge-2"
    RED_EDGE_3 = "red-edge-3"
    NEAR_INFRARED = "nir"
    NARROW_NEAR_INFRARED = "narrow-nir"
    WATER_VAPOUR = "water-vapour"
    SHORTWAVE_INFRARED_1 = "swir-1"
    SHORTWAVE_INFRARED_2 = "swir-2"

    # Sentinel-2's scene classification layer: a categorical raster, so it is resampled with nearest
    # neighbour and never interpolated (§8 rule 6 - interpolating a class label invents classes).
    SCENE_CLASSIFICATION = "scl"

    # SAR polarisations. Not reflectance and not comparable to optical bands in any arithmetic.
    VV = "vv"
    VH = "vh"


class SpectralBand(StrEnum):
    """Sentinel-2 band identifiers, as the products name them."""

    B01 = "B01"
    B02 = "B02"
    B03 = "B03"
    B04 = "B04"
    B05 = "B05"
    B06 = "B06"
    B07 = "B07"
    B08 = "B08"
    B8A = "B8A"
    B09 = "B09"
    B11 = "B11"
    B12 = "B12"
    SCL = "SCL"


# Band -> (role, centre wavelength in nm, native ground resolution in metres).
#
# The resolution column is the load-bearing one. B04 and B08 are 10 m; B11 and B12 are 20 m; B01 and B09 are
# 60 m. An index combining across those must resample first, and a 20 m band read as though it were 10 m
# reports half the ground distance per pixel - so every area it produces is wrong by four.
SENTINEL2_BANDS: Final[dict[SpectralBand, tuple[BandRole, int, int]]] = {
    SpectralBand.B01: (BandRole.COASTAL, 443, 60),
    SpectralBand.B02: (BandRole.BLUE, 490, 10),
    SpectralBand.B03: (BandRole.GREEN, 560, 10),
    SpectralBand.B04: (BandRole.RED, 665, 10),
    SpectralBand.B05: (BandRole.RED_EDGE_1, 705, 20),
    SpectralBand.B06: (BandRole.RED_EDGE_2, 740, 20),
    SpectralBand.B07: (BandRole.RED_EDGE_3, 783, 20),
    SpectralBand.B08: (BandRole.NEAR_INFRARED, 842, 10),
    SpectralBand.B8A: (BandRole.NARROW_NEAR_INFRARED, 865, 20),
    SpectralBand.B09: (BandRole.WATER_VAPOUR, 945, 60),
    SpectralBand.B11: (BandRole.SHORTWAVE_INFRARED_1, 1610, 20),
    SpectralBand.B12: (BandRole.SHORTWAVE_INFRARED_2, 2190, 20),
    SpectralBand.SCL: (BandRole.SCENE_CLASSIFICATION, 0, 20),
}

# Role -> the Sentinel-2 band that fills it. Derived rather than written twice, so the two cannot disagree.
SENTINEL2_BAND_FOR_ROLE: Final[dict[BandRole, SpectralBand]] = {
    role: band for band, (role, _, _) in SENTINEL2_BANDS.items()
}

# --- Reflectance scaling (`architecture-context.md` §8 rule 5) --------------------------------------------
#
# L2A stores reflectance as an integer: `reflectance = (digital_number - OFFSET) / SCALE`. The offset arrived
# with processing baseline 04.00 (2022-01-25) and is zero before it.
#
# MEASURED on a real scene (`notebooks/02_data_exploration/01_sentinel2_l2a.ipynb`): forgetting the offset
# moves the vegetated fraction of a 1024x1024 window from 75.1% to 61.4% - 13.7 points, mean |dNDVI| 0.185.
# Both maps look like NDVI maps, which is why this is a constant with a citation rather than a magic number.
REFLECTANCE_SCALE: Final[float] = 10_000.0
REFLECTANCE_OFFSET: Final[float] = 1_000.0
REFLECTANCE_OFFSET_BASELINE: Final[str] = "04.00"

# --- COG profile ------------------------------------------------------------------------------------------
#
# A Cloud-Optimised GeoTIFF is an ordinary GeoTIFF arranged so one tile costs one HTTP range request. Every
# value below decides whether that holds; get one wrong and the file still opens, still renders, and costs
# forty round trips per tile - a slow globe rather than a broken one, which is the harder failure to notice.

# 512 rather than GDAL's 256 default. TiTiler serves 256-pixel web tiles, and a 512 internal tile means one
# read covers four web tiles at the matching zoom. Larger wastes bandwidth on a partial read; smaller
# multiplies requests.
COG_BLOCK_SIZE: Final[int] = 512

# DEFLATE, not LZW or JPEG. Lossless, which masks require (§8 rule 4 - a lossy nodata edge invents pixels
# that are neither data nor nodata), and universally readable. JPEG would halve the size of an RGB composite
# and is forbidden for anything a number is computed from.
COG_COMPRESSION: Final[str] = "DEFLATE"

# Horizontal differencing before compression. Roughly halves the size of continuous rasters like an index
# map, and must NOT be applied to floating point without `PREDICTOR=3` - so the writer chooses by dtype.
COG_PREDICTOR_INTEGER: Final[int] = 2
COG_PREDICTOR_FLOAT: Final[int] = 3

# Overview levels, as decimation factors. Eight levels take a 10980-pixel scene down to ~43 pixels, which is
# what lets a globe zoomed out to the whole tile read one small overview rather than decimating 120 megapixels.
COG_OVERVIEW_LEVELS: Final[int] = 8

# Averaging for continuous data. Categorical rasters override this with nearest - `architecture-context.md`
# §8 rule 6, because an averaged class label is a class that does not exist.
COG_OVERVIEW_RESAMPLING: Final[str] = "average"
COG_OVERVIEW_RESAMPLING_CATEGORICAL: Final[str] = "nearest"

# What a float raster uses to mean "no data". NaN rather than a sentinel like -9999: a sentinel is a real
# number that survives arithmetic and can be averaged into a result, whereas NaN propagates. §8 rule 4.
NODATA_FLOAT: Final[float] = float("nan")

# The web mercator CRS every tile is served in. Stated as a constant because the string form matters -
# `EPSG:3857` is what rasterio and TiTiler both expect, and `EPSG:900913` is the deprecated synonym that
# some tools still emit.
WEB_MERCATOR_CRS: Final[str] = "EPSG:3857"
GEOGRAPHIC_CRS: Final[str] = "EPSG:4326"

# --- Tiling for inference (S11) ---------------------------------------------------------------------------
#
# Distinct from the COG's internal tiling above, which is for *reading*. This is the window grid a specialist
# model runs over.

# 512 matches what most remote-sensing segmentation and change models were trained at.
INFERENCE_TILE_SIZE: Final[int] = 512

# Tiles overlap, and this is why: a convolutional model has a receptive field, so its predictions near a
# window edge are made with missing context and are systematically worse. Without overlap those errors land
# in a grid pattern across the output - visible as seams in a change mask, and countable as false positives.
# 64 pixels is an eighth of the tile, enough to cover the receptive field of the models in the PDF's table.
INFERENCE_TILE_OVERLAP: Final[int] = 64

# --- Quality thresholds (S4-S5) ---------------------------------------------------------------------------
#
# Where the pipeline refuses rather than warns. Domain properties, not per-machine settings, which is why
# they are constants and not configuration: what fraction of cloud makes a scene useless does not vary
# between developer laptops.

# Above this fraction of nodata a scene is refused. A window that is two-thirds empty produces statistics
# over the third that is not, reported as though they described the whole area.
MAXIMUM_NODATA_FRACTION: Final[float] = 0.5

# Above this, a scene is refused for index work. Not a warning: `architecture-context.md` §8 rule 1 says
# index values over cloud are not meaningful, so a mostly-cloudy scene yields a mostly-meaningless map.
MAXIMUM_CLOUD_FRACTION: Final[float] = 0.8

# A raster whose values are all identical carries no information and is usually a failed download or a
# misread band. Checked by histogram rather than by eye, because it renders as a plausible flat image.
#
# **A count, not a fraction, and that correction came from a failing test.** The first version compared
# `distinct / valid` against 1e-6 - which is scale-dependent, and therefore nearly useless: a constant
# raster has exactly `1 / N` distinct values, so a 20x20 constant scene scores 0.0025 and passes, while
# the same fault in a 10980x10980 scene scores 8e-9 and fails. The threshold silently only applied to
# rasters over a million pixels. Constancy is a scale-free property and is counted directly.
MINIMUM_DISTINCT_VALUES: Final[int] = 2

# Bounds a reflectance value may take after scaling. Outside this the scaling was wrong - the offset was
# applied twice, or not at all. Slightly wider than [0, 1] because genuine specular returns exceed 1.
REFLECTANCE_VALID_RANGE: Final[tuple[float, float]] = (-0.2, 2.0)

# The smallest denominator a normalised-difference index may be computed over.
#
# **Measured, after getting this wrong.** The first NDVI this pipeline produced ranged [-337, +347] over a
# real scene, against a mathematical range of [-1, +1] - and it wrote a perfectly valid COG that renders as
# a plausible map. The cause: `(NIR - RED) / (NIR + RED)` is unbounded as the denominator approaches zero,
# and after the L2A offset is subtracted, dark pixels have small and occasionally negative reflectance, so
# their sum crosses zero. 0.055% of pixels were affected - few enough to miss by eye, more than enough to
# set the colour scale of every figure drawn from the array.
#
# 1e-4 in reflectance units is one part in ten thousand: below it the two bands are indistinguishable from
# black and the ratio between them is noise, not vegetation. Masked rather than clipped, because a clipped
# value is a number nobody measured (§8 rule 4).
MINIMUM_INDEX_DENOMINATOR: Final[float] = 1e-4

# A normalised-difference index is bounded by its own algebra. A value outside this range is not unusual
# data; it is a bug in the arithmetic, and `imagery/math/indices.py` raises rather than writing it.
NORMALISED_INDEX_RANGE: Final[tuple[float, float]] = (-1.0, 1.0)

# How many pixels the quality statistics sample. A full 10980x10980 band is 120 megapixels; reading all of
# it to answer "is this mostly nodata" costs 240 MB and minutes. A regular decimated read answers the same
# question to within a fraction of a percent - and decimated, not random, so the answer is reproducible.
QUALITY_SAMPLE_MAXIMUM_PIXELS: Final[int] = 4_000_000
