"""Defines scientific thresholds for cloud, registration, and SAR preprocessing.

what  : Domain thresholds and raster resampling names for Phase 1.3 preprocessing.
where : Used by ``services/preprocessing/``; callers may select a method, but do not invent thresholds.
how   : These values are fixed scientific policy rather than machine configuration. A residual is measured
        in pixels on the analysis grid, so it remains meaningful before a later stage converts it to metres.
"""

from typing import Final

# s2cloudless reports cloud likelihood on [0, 1]. Its documented 0.4 default is kept explicit so the mask
# and its evidence record cannot silently drift apart.
CLOUD_PROBABILITY_THRESHOLD: Final[float] = 0.4

# A temporal comparison is invalid once independently measured local translations disagree by half a pixel.
# This is deliberately a refusal threshold: confidence cannot repair a comparison with uncertain geometry.
MAXIMUM_COREGISTRATION_RESIDUAL_PIXELS: Final[float] = 0.5

# Local phase correlation needs enough texture to distinguish a translation from periodic or flat imagery.
COREGISTRATION_TILE_SIZE_PIXELS: Final[int] = 128
COREGISTRATION_MINIMUM_VALID_TILES: Final[int] = 4

# Lee filtering is applied in linear power, never dB. A 5x5 window suppresses single-pixel speckle while
# retaining the 10 m spatial detail Phase 1 analyses need.
LEE_FILTER_WINDOW_SIZE: Final[int] = 5
SAR_POWER_EPSILON: Final[float] = 1e-10

# The Lee filter's threshold between speckle and structure is speckle's own coefficient of variation,
# 1/sqrt(L). It is therefore a property of the *product*, not of the filter: 4.4 is the documented
# equivalent number of looks for Sentinel-1 IW GRDH. A wrong value here does not fail - it quietly decides
# how much real texture gets smoothed away, so it is passed explicitly rather than defaulted inside math/.
SENTINEL1_IW_GRD_EQUIVALENT_LOOKS: Final[float] = 4.4

# The display domain for SAR backscatter, in dB, for both Sentinel-1 polarisations.
#
# **Fixed, for the same reason a normalised index is drawn over [-1, 1] (Phase 1.2.1).** Two dates stretched
# to their own percentiles are not comparable, and a comparison is the entire reason a radar time series
# exists. The range covers calm water near -25 dB through vegetation around -10 dB to urban double-bounce
# above 0 dB, so nothing of interest saturates.
SAR_BACKSCATTER_DECIBEL_DOMAIN: Final[tuple[float, float]] = (-25.0, 5.0)
