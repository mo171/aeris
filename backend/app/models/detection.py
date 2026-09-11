"""Runs YOLO11-OBB over an RGB image and returns the oriented boxes it found, with the model's score on each.

what  : `YoloObbAdapter` - `predict()` for an image of any size, windowed at 1024 and merged by rotated
        NMS across the seams - and `load_yolo_obb()`, the loader the manager calls.
where : Leased from `app/models/manager.py` by `services/detection/detector.py`; 1.10's S13 node reads the
        boxes and the 1.5 builder turns them into evidence.
how   : Ultralytics' YOLO11s-OBB trained on DOTA v1.0 (fifteen aerial classes, published test mAP50 79.5),
        served through the `ultralytics` package - **AGPL-3.0, weights and package alike**; the fleet
        record and `constants/licences.py` carry that. Pure PyTorch, no compiled operators: the reason
        this route works on a laptop where the mmrotate detectors do not.

        **The package reads a NumPy array as BGR.** That is OpenCV's convention and not this backend's,
        which is RGB everywhere from the band stack down; the adapter reverses the channel axis before
        handing over, and a test scores the two orders against DOTA8 truth to prove which is right.
        Letterboxing to the working tile, the confidence threshold and the within-tile NMS are the
        package's; the merge *across* tiles is ours (`services/detection/math/oriented_boxes.py`),
        because a vehicle on a seam is two half-boxes to the model and one object to the answer. A box
        that touches a window's interior edge and is narrower than the overlap is a cut object that the
        neighbouring window sees whole, so it is dropped before the merge (measured: without this a 2×2
        mosaic of one crop returned 10 boxes for 8 objects). One wider than the overlap is kept on both
        sides and left to NMS - a ground track field on a seam may still come out twice.

        Pixels the caller marks unobserved (NaN) are fed as black and a box whose centre falls on them is
        dropped: the model was not shown ground there, so it has not detected anything there.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.constants.detection import (
    DETECTION_CONFIDENCE_THRESHOLD,
    DETECTION_NMS_IOU,
    DETECTION_TILE_OVERLAP,
    DOTA_CLASS_NAMES,
)
from app.constants.fleet import FLEET
from app.constants.model_ids import ModelId
from app.models.loader import fetch_weights
from app.services.detection.math.oriented_boxes import OrientedBox, suppress_overlaps
from app.services.imagery.math.windowing import TileWindow, plan_tile_grid

logger = logging.getLogger(__name__)

# How close to a window edge, in pixels, a box has to come to count as cut by it.
EDGE_MARGIN = 2


@dataclass(frozen=True, slots=True)
class DetectionPrediction:
    """Every box the detector stands behind, in the image's own pixel coordinates."""

    boxes: list[OrientedBox]
    class_names: tuple[str, ...]


class YoloObbAdapter:
    """One resident YOLO-OBB on one device."""

    def __init__(self, module: object, device: str) -> None:
        self._module = module
        self.device = device
        self.tile_size = FLEET[ModelId.DOTA_DETECTOR].tile_size or 1024

    def predict(self, image: np.ndarray) -> DetectionPrediction:
        """Oriented boxes for an (H, W, 3) 8-bit RGB array, windowed at the model's tile and merged."""
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"An RGB image is (H, W, 3); got {image.shape}.")
        height, width = image.shape[:2]
        as_float = image.astype(np.float32)
        unobserved = ~np.isfinite(as_float).all(axis=2)
        pixels = np.nan_to_num(as_float, nan=0.0).clip(0, 255).astype(np.uint8)

        windows = plan_tile_grid(width=width, height=height, tile_size=self.tile_size, overlap=DETECTION_TILE_OVERLAP)
        boxes: list[OrientedBox] = []
        for window in windows:
            for box in self._predict_tile(pixels[window.as_slices()]):
                if not _cut_by_window(box, window, width=width, height=height):
                    boxes.append(box.offset(window.column_offset, window.row_offset))
        if len(windows) > 1:
            boxes = suppress_overlaps(boxes, iou_threshold=DETECTION_NMS_IOU)
        boxes = [box for box in boxes if not _centre_unobserved(box, unobserved)]
        return DetectionPrediction(boxes=boxes, class_names=DOTA_CLASS_NAMES)

    def _predict_tile(self, tile: np.ndarray) -> list[OrientedBox]:
        """The package's own pipeline over one window: letterbox, forward, threshold, NMS."""
        result = self._module.predict(  # type: ignore[attr-defined]
            np.ascontiguousarray(tile[:, :, ::-1]),
            imgsz=self.tile_size,
            conf=DETECTION_CONFIDENCE_THRESHOLD,
            device=self.device,
            verbose=False,
        )[0]
        if result.obb is None or len(result.obb) == 0:
            return []
        corners = result.obb.xyxyxyxy.cpu().numpy().astype(np.float32)
        scores = result.obb.conf.cpu().numpy()
        classes = result.obb.cls.cpu().numpy().astype(int)
        return [OrientedBox(int(c), float(s), k) for c, s, k in zip(classes, scores, corners, strict=True)]


def _cut_by_window(box: OrientedBox, window: TileWindow, *, width: int, height: int) -> bool:
    """A box against an edge the window shares with a neighbour, small enough that the neighbour holds it whole."""
    low = box.corners.min(axis=0)
    high = box.corners.max(axis=0)
    extent = high - low
    edges = (
        (low[0] <= EDGE_MARGIN and window.column_offset > 0, extent[0]),
        (high[0] >= window.width - EDGE_MARGIN and window.column_offset + window.width < width, extent[0]),
        (low[1] <= EDGE_MARGIN and window.row_offset > 0, extent[1]),
        (high[1] >= window.height - EDGE_MARGIN and window.row_offset + window.height < height, extent[1]),
    )
    return any(touching and span < DETECTION_TILE_OVERLAP for touching, span in edges)


def _centre_unobserved(box: OrientedBox, unobserved: np.ndarray) -> bool:
    row, column = box.corners.mean(axis=0)[::-1]
    row = min(max(int(row), 0), unobserved.shape[0] - 1)
    column = min(max(int(column), 0), unobserved.shape[1] - 1)
    return bool(unobserved[row, column])


async def load_yolo_obb(device: str) -> YoloObbAdapter:
    """Fetch the release asset, build the model on the device, check it predicts the DOTA classes."""
    record = FLEET[ModelId.DOTA_DETECTOR]
    assert record.weights is not None
    checkpoint = await fetch_weights(record.weights)
    import asyncio

    module = await asyncio.to_thread(_build, checkpoint, device)
    return YoloObbAdapter(module, device)


def _build(checkpoint: Path, device: str) -> object:
    from ultralytics import YOLO, settings

    # No telemetry, no settings sync, no attempt to fetch anything the record did not pin.
    settings.update(sync=False)
    module = YOLO(checkpoint, task="obb")
    names = tuple(module.names[index] for index in range(len(module.names)))
    if names != DOTA_CLASS_NAMES:
        raise ValueError(f"The checkpoint predicts {names}, not the DOTA classes this adapter names.")
    module.to(device)
    logger.info("yolo-obb built", extra={"checkpoint": str(checkpoint), "device": device, "classes": len(names)})
    return module
