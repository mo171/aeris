"""The VQA scorer: closed answers by first token, boxes by overlap, captions by ROUGE-L, types averaged not pooled."""

import pytest

from app.services.evaluation.math.text_scores import VqaScore, box_iou, exact_match, parse_normalised_box, rouge_l


def test_closed_answers_match_on_the_first_token_after_cleaning() -> None:
    assert exact_match("Yes, there is arable land.", "yes")
    assert exact_match("(c)", "c") and not exact_match("d) Coniferous", "c")
    assert not exact_match("", "yes")


def test_boxes_parse_in_the_bigearthnet_txt_form_and_overlap_correctly() -> None:
    assert parse_normalised_box("[0.54 0.0, 0.74 0.1]") == (0.54, 0.0, 0.74, 0.1)
    assert parse_normalised_box("The box is 0.5 0.5, 0.2 0.2 roughly") == (0.2, 0.2, 0.5, 0.5)
    assert parse_normalised_box("no box") is None
    assert box_iou((0, 0, 1, 1), (0.5, 0, 1.5, 1)) == pytest.approx(1 / 3)
    assert box_iou((0, 0, 1, 1), (2, 2, 3, 3)) == 0.0


def test_rouge_l_is_lcs_f1() -> None:
    assert rouge_l("the cat sat on the mat", "the cat sat on the mat") == pytest.approx(1.0)
    assert rouge_l("a b c", "x y z") == 0.0
    assert rouge_l("the cat", "the cat sat") == pytest.approx(2 * 1.0 * (2 / 3) / (1.0 + 2 / 3))


def test_overall_averages_types_so_a_flood_of_yes_no_cannot_hide_the_boxes() -> None:
    score = VqaScore()
    for _ in range(100):
        score.record("binary", "yes", "yes")
    score.record("bounding box", "[0 0, 1 1]", "[0.9 0.9, 1 1]")
    assert score.accuracy("binary") == 1.0 and score.accuracy("bounding box") == 0.0
    assert score.overall == pytest.approx(0.5)
    assert score.accuracy("mcq") is None
