"""Tests the seven index formulae and the thresholding kernels against values computed by hand.

what  : One hand-checked value per formula, the masking rules each formula shares, the two failure modes
        EVI and SAVI carry on their own, and the range/summary semantics that keep unobserved pixels out
        of every mask and every statistic.
where : Unit suite for `services/spectral/math/`; plain arrays, no files, no infrastructure.
how   : `code-standards.md` §11 - a test that pins whatever the code returns proves nothing. Every
        expected value below is arithmetic a reviewer can redo on paper from the PDF's equations (§3.3).
"""

import numpy as np
import pytest

from app.constants.spectral import INTERPRETATION_BANDS, SpectralIndex
from app.services.spectral.math.index_formulae import FORMULAE, evi, mndwi, nbr, ndbi, ndvi, ndwi, savi
from app.services.spectral.math.thresholds import otsu_threshold, summarise, within_range


def array(*values: float) -> np.ndarray:
    return np.array(values, dtype=np.float32).reshape(1, -1)


# ── The formulae, by hand ────────────────────────────────────────────────────────────────────────


def test_ndvi_by_hand() -> None:
    # (0.6 - 0.2) / (0.6 + 0.2) = 0.5 ; (0.1 - 0.3) / 0.4 = -0.5
    assert ndvi(array(0.6, 0.1), array(0.2, 0.3)).tolist() == [pytest.approx([0.5, -0.5])]


def test_evi_by_hand() -> None:
    # 2.5 * (0.5 - 0.1) / (0.5 + 6*0.1 - 7.5*0.05 + 1) = 1.0 / 1.725 = 0.579710...
    assert evi(array(0.5), array(0.1), array(0.05))[0, 0] == pytest.approx(1.0 / 1.725, rel=1e-6)


def test_savi_by_hand() -> None:
    # 1.5 * (0.5 - 0.1) / (0.5 + 0.1 + 0.5) = 0.6 / 1.1 = 0.545454...
    assert savi(array(0.5), array(0.1))[0, 0] == pytest.approx(0.6 / 1.1, rel=1e-6)


def test_ndwi_is_positive_over_water_and_negative_over_canopy() -> None:
    # Water: green 0.08, nir 0.02 -> +0.6. Canopy: green 0.06, nir 0.42 -> -0.75.
    assert ndwi(array(0.08, 0.06), array(0.02, 0.42)).tolist() == [pytest.approx([0.6, -0.75])]


def test_mndwi_ndbi_nbr_by_hand() -> None:
    # MNDWI (0.09 - 0.01) / 0.10 = 0.8 ; NDBI (0.3 - 0.2) / 0.5 = 0.2 ; NBR (0.4 - 0.1) / 0.5 = 0.6
    assert mndwi(array(0.09), array(0.01))[0, 0] == pytest.approx(0.8)
    assert ndbi(array(0.3), array(0.2))[0, 0] == pytest.approx(0.2)
    assert nbr(array(0.4), array(0.1))[0, 0] == pytest.approx(0.6)


def test_every_index_has_a_formula_and_the_formula_takes_its_declared_bands() -> None:
    from app.constants.spectral import INDEX_BAND_ROLES

    for index in SpectralIndex:
        formula = FORMULAE[index]
        bands = [np.full((2, 2), 0.3, dtype=np.float32) for _ in INDEX_BAND_ROLES[index]]
        assert formula(*bands).shape == (2, 2)


# ── Masking rules shared by every formula ────────────────────────────────────────────────────────


def test_nodata_propagates_as_nan_through_evi_and_savi() -> None:
    result_evi = evi(array(np.nan, 0.5), array(0.1, 0.1), array(0.05, 0.05))
    result_savi = savi(array(0.5, 0.5), array(np.nan, 0.1))

    assert np.isnan(result_evi[0, 0]) and np.isfinite(result_evi[0, 1])
    assert np.isnan(result_savi[0, 0]) and np.isfinite(result_savi[0, 1])


def test_negative_reflectance_is_masked_not_computed() -> None:
    """The 1.2 finding, applied to the two formulae 1.2 did not cover: a negative band is an artefact."""
    assert np.isnan(evi(array(0.5), array(-0.01), array(0.05))[0, 0])
    assert np.isnan(savi(array(-0.02), array(0.1))[0, 0])


def test_evi_masks_the_pixels_where_its_own_denominator_collapses() -> None:
    """Bright blue drives `nir + 6*red - 7.5*blue + 1` through zero; the ratio there is not vegetation."""
    # Denominator: 0.1 + 0.3 - 7.5*0.19 + 1 = -0.025 -> masked. Same bands with blue 0.05 -> +1.025, kept.
    result = evi(array(0.1, 0.1), array(0.05, 0.05), array(0.19, 0.05))

    assert np.isnan(result[0, 0])
    assert np.isfinite(result[0, 1])


def test_an_index_outside_its_domain_is_masked_rather_than_clipped() -> None:
    """SAVI over a specular pixel: 1.5 * (1.8 - 0.0) / (1.8 + 0.0 + 0.5) = 1.174 > 1. Not a reading."""
    result = savi(array(1.8, 0.5), array(0.0, 0.1))

    assert np.isnan(result[0, 0])
    assert result[0, 1] == pytest.approx(0.6 / 1.1, rel=1e-6)


def test_bands_on_different_grids_are_refused() -> None:
    with pytest.raises(ValueError, match="share a grid"):
        evi(np.zeros((4, 4), np.float32), np.zeros((4, 4), np.float32), np.zeros((2, 2), np.float32))
    with pytest.raises(ValueError, match="share a grid"):
        savi(np.zeros((4, 4), np.float32), np.zeros((4, 5), np.float32))


def test_formulae_return_float32() -> None:
    for formula, count in ((ndvi, 2), (evi, 3), (savi, 2)):
        assert formula(*[np.full((2, 2), 0.3, dtype=np.float64)] * count).dtype == np.float32


# ── Thresholds ───────────────────────────────────────────────────────────────────────────────────


def test_a_range_is_closed_below_open_above_and_closed_at_the_top_of_the_domain() -> None:
    index = array(0.2, 0.39, 0.4, 1.0, np.nan)

    assert within_range(index, 0.2, 0.4).tolist() == [[True, True, False, False, False]]
    assert within_range(index, 0.4, 1.0).tolist() == [[False, False, True, True, False]]


def test_an_unobserved_pixel_is_never_detected() -> None:
    """`nan < 0.2` is False in NumPy, which would make every cloud pixel "bare ground" in a mask."""
    detected = within_range(array(np.nan, np.nan), -1.0, 1.0)

    assert not detected.any()


def test_otsu_splits_a_bimodal_index_between_its_modes() -> None:
    index = np.concatenate([np.full(500, 0.1), np.full(500, 0.7), [np.nan] * 10]).astype(np.float32)

    threshold = otsu_threshold(index)

    assert 0.1 < threshold < 0.7


def test_otsu_refuses_a_constant_index() -> None:
    with pytest.raises(ValueError, match="two distinct"):
        otsu_threshold(np.full((4, 4), 0.3, dtype=np.float32))


def test_summary_counts_only_observed_pixels_and_covers_the_domain() -> None:
    index = array(-0.5, 0.1, 0.3, 0.5, 0.9, np.nan, np.nan)

    summary = summarise(index, INTERPRETATION_BANDS[SpectralIndex.NDVI])

    assert summary.observed_count == 5
    assert summary.total_count == 7
    assert summary.observed_fraction == pytest.approx(5 / 7)
    assert summary.mean == pytest.approx((-0.5 + 0.1 + 0.3 + 0.5 + 0.9) / 5)
    assert summary.median == pytest.approx(0.3)
    assert summary.band_fractions == {
        "Water": pytest.approx(1 / 5),
        "Bare or built": pytest.approx(1 / 5),
        "Sparse vegetation": pytest.approx(1 / 5),
        "Dense healthy vegetation": pytest.approx(2 / 5),
    }
    assert sum(summary.band_fractions.values()) == pytest.approx(1.0)


def test_summary_of_a_fully_obscured_scene_reports_nothing_observed_rather_than_failing() -> None:
    summary = summarise(np.full((3, 3), np.nan, dtype=np.float32), INTERPRETATION_BANDS[SpectralIndex.NDVI])

    assert summary.observed_count == 0
    assert summary.observed_fraction == 0.0
    assert np.isnan(summary.mean)
    assert all(fraction == 0.0 for fraction in summary.band_fractions.values())


def test_every_interpretation_table_is_contiguous_over_the_domain() -> None:
    """A gap between bands is a value no label can read; an overlap is a value two labels claim."""
    for index, bands in INTERPRETATION_BANDS.items():
        assert bands[0].lower == -1.0, index
        assert bands[-1].upper == 1.0, index
        for previous, following in zip(bands, bands[1:], strict=False):
            assert previous.upper == following.lower, index
