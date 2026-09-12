"""Oriented-box geometry and the label readers: overlap, suppression, matching, and both DOTA formats."""

import numpy as np
import pytest

from app.lib.exceptions import InvalidRequestError
from app.services.detection.labels import read_dota_labels, read_yolo_obb_labels
from app.services.detection.math.oriented_boxes import (
    DetectionScore,
    OrientedBox,
    match_boxes,
    polygon_iou,
    suppress_overlaps,
)


def box(x: float, y: float, w: float, h: float, angle_degrees: float = 0.0, cls: int = 0, conf: float = 1.0) -> OrientedBox:
    theta = np.deg2rad(angle_degrees)
    rotation = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    corners = np.array([[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]]) @ rotation.T
    return OrientedBox(cls, conf, (corners + [x, y]).astype(np.float32))


def test_iou_of_a_rotated_box_is_measured_on_the_polygon_not_its_envelope() -> None:
    a = box(0, 0, 100, 10)
    assert polygon_iou(a.polygon, box(0, 0, 100, 10, angle_degrees=90).polygon) == pytest.approx(10 * 10 / (2 * 1000 - 100))
    assert polygon_iou(a.polygon, a.polygon) == pytest.approx(1.0)
    assert polygon_iou(a.polygon, box(500, 500, 10, 10).polygon) == 0.0


def test_suppression_keeps_the_most_confident_of_a_same_class_overlap_and_never_crosses_classes() -> None:
    weaker = box(0, 0, 40, 20, conf=0.6)
    stronger = box(2, 1, 40, 20, conf=0.9)
    other_class = box(2, 1, 40, 20, cls=1, conf=0.3)
    kept = suppress_overlaps([weaker, stronger, other_class], iou_threshold=0.5)
    assert kept == [stronger, other_class]


def test_matching_claims_each_truth_once_and_sums_before_ratios() -> None:
    truths = [box(0, 0, 40, 20), box(100, 100, 40, 20, cls=2)]
    predictions = [box(1, 0, 40, 20, conf=0.9), box(1, 0, 40, 20, conf=0.8), box(100, 100, 40, 20, cls=1, conf=0.9)]
    score = match_boxes(predictions, truths, iou_threshold=0.5)
    assert (score.true_positives, score.false_positives, score.false_negatives) == (1, 2, 1)
    total = score + DetectionScore(3, 0, 0)
    assert total.precision == pytest.approx(4 / 6) and total.recall == pytest.approx(4 / 5)
    assert DetectionScore(0, 0, 0).f1 == 0.0


async def test_yolo_obb_labels_scale_to_the_image_and_dota_labels_map_names(tmp_path) -> None:
    yolo = tmp_path / "a.txt"
    yolo.write_text("1 0.0 0.0 0.5 0.0 0.5 0.25 0.0 0.25\n")
    [read] = await read_yolo_obb_labels(yolo, width=200, height=400)
    assert read.class_index == 1 and read.corners.tolist() == [[0, 0], [100, 0], [100, 100], [0, 100]]

    dota = tmp_path / "b.txt"
    dota.write_text("imagesource:GoogleEarth\ngsd:0.1\n10 10 50 10 50 30 10 30 storage-tank 0\n")
    [read] = await read_dota_labels(dota)
    assert read.class_index == 2 and read.corners[2].tolist() == [50, 30]

    dota.write_text("0 0 1 0 1 1 0 1 container-crane 0\n")
    with pytest.raises(InvalidRequestError, match="container crane"):
        await read_dota_labels(dota)
