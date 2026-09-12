"""Reads oriented-box ground truth in the two formats DOTA is published in, into the one box type the detector emits.

what  : `read_yolo_obb_labels()` - `class x1 y1 ... x4 y4`, normalised to the image (DOTA8, any YOLO
        export); `read_dota_labels()` - DOTA's `labelTxt`: `x1 y1 ... x4 y4 class difficult` in pixels.
where : The evaluation harness. Both return `OrientedBox`es with confidence 1.0, the truth's own certainty.
how   : Class names map through `DOTA_CLASS_NAMES`; a name the checkpoint does not predict is refused
        rather than dropped, because a silently dropped class scores the detector on a benchmark it was
        not given. `labelTxt` files begin with two metadata lines (`imagesource`, `gsd`) that are skipped.
"""

import asyncio
from pathlib import Path

import numpy as np

from app.constants.detection import DOTA_CLASS_NAMES
from app.lib.exceptions import InvalidRequestError
from app.services.detection.math.oriented_boxes import OrientedBox


async def read_yolo_obb_labels(path: Path, *, width: int, height: int) -> list[OrientedBox]:
    """Normalised YOLO-OBB rows scaled to the image's pixel size."""
    return await asyncio.to_thread(_read_yolo, path, width, height)


async def read_dota_labels(path: Path) -> list[OrientedBox]:
    """DOTA `labelTxt` rows, already in pixels."""
    return await asyncio.to_thread(_read_dota, path)


def _read_yolo(path: Path, width: int, height: int) -> list[OrientedBox]:
    boxes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) < 9:
            continue
        corners = np.asarray(fields[1:9], dtype=np.float32).reshape(4, 2) * np.array([width, height], dtype=np.float32)
        boxes.append(OrientedBox(int(fields[0]), 1.0, corners))
    return boxes


def _read_dota(path: Path) -> list[OrientedBox]:
    boxes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) < 9 or fields[0] in {"imagesource:", "gsd:"}:
            continue
        name = fields[8].replace("-", " ")
        if name not in DOTA_CLASS_NAMES:
            raise InvalidRequestError(
                f"{path.name} labels a '{name}', which the detector does not predict.",
                details={"path": str(path), "className": name},
            )
        corners = np.asarray(fields[:8], dtype=np.float32).reshape(4, 2)
        boxes.append(OrientedBox(DOTA_CLASS_NAMES.index(name), 1.0, corners))
    return boxes
