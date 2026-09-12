"""Tests the change-detection kernels against counts and ratios worked out by hand.

what  : Change-class scoring (the four counts, the four ratios, summing across samples, unobserved
        pixels excluded), the log-ratio detector and its two-sided threshold.
where : Unit suite for `services/change_detection/math/`; arrays only.
how   : `code-standards.md` §11. The wrong answer scoring holds off is accuracy - a mask of nothing on
        LEVIR-CD is 95% accurate - so the ratios are checked on a grid small enough to count on paper.
"""

import numpy as np
import pytest

from app.services.change_detection.math.change_statistics import ChangeScore, change_fraction, score_mask
from app.services.change_detection.math.log_ratio import log_ratio_decibels, threshold_log_ratio


def test_the_four_counts_and_four_ratios_by_hand() -> None:
    #  truth:      predicted:
    #  1 1 0 0     1 0 0 0      TP=1 (0,0); FN=1 (0,1); FP=1 (1,3); TN=13
    #  0 0 0 0     0 0 0 1
    #  0 0 0 0     0 0 0 0
    #  0 0 0 0     0 0 0 0
    truth = np.zeros((4, 4), dtype=bool)
    truth[0, :2] = True
    predicted = np.zeros((4, 4), dtype=bool)
    predicted[0, 0] = predicted[1, 3] = True

    score = score_mask(predicted, truth)

    assert (score.true_positives, score.false_positives, score.false_negatives, score.true_negatives) == (1, 1, 1, 13)
    assert score.precision == pytest.approx(0.5)
    assert score.recall == pytest.approx(0.5)
    assert score.f1 == pytest.approx(0.5)
    assert score.iou == pytest.approx(1 / 3)


def test_unobserved_pixels_are_in_no_count() -> None:
    """A cloud over a new building is not a miss, and a cloud over nothing is not a correct rejection."""
    truth = np.array([[True, False], [False, False]])
    predicted = np.array([[False, False], [True, False]])
    observed = np.array([[False, True], [False, True]])

    score = score_mask(predicted, truth, observed)

    assert (score.true_positives, score.false_positives, score.false_negatives, score.true_negatives) == (0, 0, 0, 2)


def test_scores_sum_as_counts_not_as_ratios() -> None:
    """Two crops: one perfect and empty, one half right. A mean of F1s says 0.5-ish; the counts say 2/3."""
    empty = score_mask(np.zeros((2, 2), bool), np.zeros((2, 2), bool))
    half = score_mask(np.array([[True, False], [False, False]]), np.array([[True, True], [False, False]]))

    total = empty + half

    assert empty.f1 == 0.0
    assert half.f1 == pytest.approx(2 / 3)
    assert total.f1 == pytest.approx(2 / 3), "the empty crop must not drag the score down by averaging"


def test_an_empty_prediction_over_an_empty_truth_scores_zero_without_dividing_by_zero() -> None:
    score = ChangeScore(0, 0, 0, 16)

    assert (score.precision, score.recall, score.f1, score.iou) == (0.0, 0.0, 0.0, 0.0)


def test_change_fraction_is_over_observed_pixels_only() -> None:
    mask = np.array([[True, False, False, False]])
    observed = np.array([[True, True, False, False]])

    assert change_fraction(mask, observed) == pytest.approx(0.5)
    assert change_fraction(mask, np.zeros_like(observed)) == 0.0


def test_log_ratio_is_symmetric_in_decibels() -> None:
    """A doubling is +3.01 dB and a halving is -3.01 dB: the same distance from zero, opposite signs."""
    before = np.array([[1.0, 2.0, 1.0]], dtype=np.float32)
    after = np.array([[2.0, 1.0, 1.0]], dtype=np.float32)

    ratio = log_ratio_decibels(before, after)

    assert ratio[0, 0] == pytest.approx(10 * np.log10(2), abs=1e-4)
    assert ratio[0, 1] == pytest.approx(-10 * np.log10(2), abs=1e-4)
    assert ratio[0, 2] == pytest.approx(0.0, abs=1e-6)


def test_log_ratio_is_nan_where_either_date_is_unobserved_or_non_positive() -> None:
    before = np.array([[np.nan, 1.0, 0.0, 1.0]], dtype=np.float32)
    after = np.array([[1.0, np.nan, 1.0, -1.0]], dtype=np.float32)

    ratio = log_ratio_decibels(before, after)

    assert np.isnan(ratio).all()


def test_threshold_separates_increase_from_decrease_and_never_marks_nan() -> None:
    ratio = np.array([[3.5, -3.5, 2.9, np.nan]], dtype=np.float32)

    increase, decrease = threshold_log_ratio(ratio, 3.0)

    assert increase.tolist() == [[True, False, False, False]]
    assert decrease.tolist() == [[False, True, False, False]]


def test_a_non_positive_threshold_is_refused() -> None:
    with pytest.raises(ValueError, match="positive"):
        threshold_log_ratio(np.zeros((1, 1), np.float32), 0.0)
