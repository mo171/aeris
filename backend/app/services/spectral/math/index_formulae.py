"""The seven index formulae over reflectance arrays, each refusing to return a value its own physics says is meaningless.

what  : `ndvi`, `evi`, `savi`, `ndwi`, `mndwi`, `ndbi`, `nbr`, and `FORMULAE` mapping each `SpectralIndex`
        to its function. Arrays in, one float32 array out, NaN wherever the value is not a measurement.
where : Called by `services/spectral/indices.py` through `asyncio.to_thread`, after the cloud mask has
        already been applied to the inputs (§8 rule 1 - the mask reaches the bands, not the result).
how   : **Pure, sync, NumPy only** (`architecture-context.md` §12). This module knows reflectance arrays
        and coefficients; which bands fill each argument is the service's decision.

        Five of the seven are one operation - `(high - low) / (high + low)` - and that operation lives in
        `services/imagery/math/indices.py` because Phase 1.2 found and fixed the [-337, +347] bug there,
        and a formula is written once (`architecture-context.md` §12 reason 4). It is imported rather than
        copied; a sibling `math/` module is the one project import a `math/` module may make.

        EVI and SAVI are not normalised differences and carry their own failure modes:

        - **EVI is unbounded, by design of its denominator.** `nir + 6*red - 7.5*blue + 1` goes to zero
          and negative over bright, blue-heavy surfaces - snow, cloud edge, bare sand - and MODIS flags
          exactly those pixels rather than reporting them. Here they are masked to NaN, and so is any
          result outside [-1, 1]: a value the index's own interpretation table cannot read is not a
          reading. Masked, never clipped (§8 rule 4).
        - **SAVI exceeds 1 only when reflectance exceeds 1**, which is a specular or saturated pixel, not
          vegetation. Same treatment.
        - **Negative reflectance is masked in every formula**, for the reason 1.2 measured: it is an
          atmospheric-correction artefact over dark ground, and every ratio over it is unbounded.

        The coefficients are the document's (`constants/spectral.py`), passed as defaults so a caller
        that wants SAVI's `L` for a different soil says so at the call and it is recorded in the result.
"""

from collections.abc import Callable
from typing import Final

import numpy as np

from app.constants.raster import MINIMUM_INDEX_DENOMINATOR
from app.constants.spectral import (
    EVI_BLUE_COEFFICIENT,
    EVI_CANOPY_BACKGROUND,
    EVI_GAIN,
    EVI_RED_COEFFICIENT,
    INDEX_DOMAIN,
    SAVI_SOIL_BRIGHTNESS,
    SpectralIndex,
)
from app.services.imagery.math.indices import normalised_difference


def ndvi(near_infrared: np.ndarray, red: np.ndarray) -> np.ndarray:
    """(NIR - RED) / (NIR + RED). PDF §3.3.1."""
    return normalised_difference(near_infrared, red)


def ndwi(green: np.ndarray, near_infrared: np.ndarray) -> np.ndarray:
    """(GREEN - NIR) / (GREEN + NIR). McFeeters; PDF §3.3.4."""
    return normalised_difference(green, near_infrared)


def mndwi(green: np.ndarray, shortwave_infrared_1: np.ndarray) -> np.ndarray:
    """(GREEN - SWIR1) / (GREEN + SWIR1). Xu; PDF §3.3.5."""
    return normalised_difference(green, shortwave_infrared_1)


def ndbi(shortwave_infrared_1: np.ndarray, near_infrared: np.ndarray) -> np.ndarray:
    """(SWIR1 - NIR) / (SWIR1 + NIR). Zha; PDF §3.3.6."""
    return normalised_difference(shortwave_infrared_1, near_infrared)


def nbr(near_infrared: np.ndarray, shortwave_infrared_2: np.ndarray) -> np.ndarray:
    """(NIR - SWIR2) / (NIR + SWIR2). Key & Benson; PDF §3.3.7."""
    return normalised_difference(near_infrared, shortwave_infrared_2)


def evi(
    near_infrared: np.ndarray,
    red: np.ndarray,
    blue: np.ndarray,
    *,
    gain: float = EVI_GAIN,
    red_coefficient: float = EVI_RED_COEFFICIENT,
    blue_coefficient: float = EVI_BLUE_COEFFICIENT,
    canopy_background: float = EVI_CANOPY_BACKGROUND,
) -> np.ndarray:
    """G * (NIR - RED) / (NIR + C1*RED - C2*BLUE + L). Huete; PDF §3.3.2 equation (2)."""
    _require_one_grid(near_infrared, red, blue)
    denominator = near_infrared + red_coefficient * red - blue_coefficient * blue + canopy_background
    with np.errstate(divide="ignore", invalid="ignore"):
        index = gain * (near_infrared - red) / denominator
    return _finish(index, denominator, near_infrared, red, blue)


def savi(
    near_infrared: np.ndarray,
    red: np.ndarray,
    *,
    soil_brightness: float = SAVI_SOIL_BRIGHTNESS,
) -> np.ndarray:
    """(1 + L) * (NIR - RED) / (NIR + RED + L). Huete; PDF §3.3.3 equation (3)."""
    _require_one_grid(near_infrared, red)
    denominator = near_infrared + red + soil_brightness
    with np.errstate(divide="ignore", invalid="ignore"):
        index = (1.0 + soil_brightness) * (near_infrared - red) / denominator
    return _finish(index, denominator, near_infrared, red)


def _require_one_grid(*bands: np.ndarray) -> None:
    shapes = {band.shape for band in bands}
    if len(shapes) != 1:
        raise ValueError(
            f"Bands must share a grid: got {sorted(shapes)}. Bands at different resolutions have to be "
            "resampled onto one grid before any index is computed."
        )


def _finish(index: np.ndarray, denominator: np.ndarray, *bands: np.ndarray) -> np.ndarray:
    """Mask everything that is not a measurement: unphysical inputs, a collapsed denominator, a value
    outside the domain. NaN is the masked state throughout (§8 rule 4)."""
    unphysical = np.zeros(index.shape, dtype=bool)
    for band in bands:
        with np.errstate(invalid="ignore"):
            unphysical |= band < 0.0
    with np.errstate(invalid="ignore"):
        collapsed = ~np.isfinite(denominator) | (denominator < MINIMUM_INDEX_DENOMINATOR)
        low, high = INDEX_DOMAIN
        outside = (index < low) | (index > high)
    index = index.astype(np.float32, copy=True)
    index[unphysical | collapsed | outside] = np.nan
    return index


# Index -> its function. The positional order of each function's parameters is `INDEX_BAND_ROLES[index]`.
FORMULAE: Final[dict[SpectralIndex, Callable[..., np.ndarray]]] = {
    SpectralIndex.NDVI: ndvi,
    SpectralIndex.EVI: evi,
    SpectralIndex.SAVI: savi,
    SpectralIndex.NDWI: ndwi,
    SpectralIndex.MNDWI: mndwi,
    SpectralIndex.NDBI: ndbi,
    SpectralIndex.NBR: nbr,
}
