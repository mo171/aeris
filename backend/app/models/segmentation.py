"""Runs a land-cover SegFormer over an RGB image and returns a class per pixel with the probability behind it.

what  : `SegFormerAdapter` - `predict()` for an image of any size, windowed at 512 and stitched per class -
        and `load_segformer()`, the loader the manager calls. `CLASS_NAMES` is what the checkpoint predicts.
where : Leased from `app/models/manager.py`; the S13 segmentation service (1.10 wires the node) reads the
        class map and the 1.5 builder turns any class's mask into evidence.
how   : SegFormer-B2 fine-tuned on LoveDA (Wang et al. 2021: seven land-cover classes over 0.3 m urban and
        rural scenes, plus an `Ignore` label the loss skipped), served through `transformers`. The
        checkpoint's own `preprocessor_config.json` states its input convention - a rescale to [0, 1]
        and ImageNet mean and standard deviation - and the adapter reads that file and applies exactly
        that, resizing nothing: the model is fed 512-pixel windows at native resolution and its
        quarter-resolution logits are upsampled back to the window, then stitched class by class with
        the edge-weighted blend. The library's image processor is not used: it would add torchvision for
        a subtraction and a division whose constants are in a file this adapter already reads.

        **The `Ignore` class is never predicted.** It is the label LoveDA uses for unannotated pixels, and
        a model asked over 8 classes will put probability on it; taking the argmax over the seven real
        classes is what makes every pixel a land cover rather than an absence of annotation.

        `confidence` is the softmax probability of the winning class - the model's own certainty per pixel,
        stated as such. A class map without it cannot say which fields were a coin toss.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.constants.fleet import FLEET
from app.constants.model_ids import ModelId
from app.constants.raster import INFERENCE_TILE_OVERLAP
from app.constants.segmentation import LOVEDA_CLASS_NAMES, SEGMENTATION_IGNORE_LABEL
from app.models.loader import fetch_repository
from app.services.imagery.math.windowing import plan_tile_grid, stitch_windows

logger = logging.getLogger(__name__)

# LoveDA's label order, as the checkpoint's `id2label` states it. Index is the class id. One source
# (`constants/segmentation.py`), so the node that names a class and the adapter that predicts it agree.
IGNORE_LABEL = SEGMENTATION_IGNORE_LABEL
CLASS_NAMES = LOVEDA_CLASS_NAMES


@dataclass(frozen=True, slots=True)
class SegmentationPrediction:
    """A class per pixel and the probability the model gave that class."""

    class_map: np.ndarray
    confidence: np.ndarray
    class_names: tuple[str, ...]


class SegFormerAdapter:
    """One resident SegFormer on one device."""

    def __init__(
        self, module: object, device: str, *, image_mean: tuple[float, ...], image_std: tuple[float, ...]
    ) -> None:
        self._module = module
        self.device = device
        self.image_mean = np.asarray(image_mean, dtype=np.float32)
        self.image_std = np.asarray(image_std, dtype=np.float32)
        self.tile_size = FLEET[ModelId.SEGFORMER_LANDCOVER].tile_size or 512

    def predict(self, image: np.ndarray) -> SegmentationPrediction:
        """Land cover for an (H, W, 3) 8-bit RGB array, windowed at the model's tile."""
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"An RGB image is (H, W, 3); got {image.shape}.")
        height, width = image.shape[:2]
        unobserved = ~np.isfinite(image.astype(np.float32)).all(axis=2)

        windows = plan_tile_grid(width=width, height=height, tile_size=self.tile_size, overlap=INFERENCE_TILE_OVERLAP)
        per_window = [self._predict_tile(image[w.as_slices()]) for w in windows]
        class_count = per_window[0].shape[0]
        stitched = np.stack(
            [
                stitch_windows(
                    windows, [p[index] for p in per_window],
                    shape=(height, width), tile_size=self.tile_size, overlap=INFERENCE_TILE_OVERLAP,
                )
                for index in range(class_count)
            ]
        )
        stitched[IGNORE_LABEL] = -np.inf
        class_map = stitched.argmax(axis=0).astype(np.int16)
        confidence = np.take_along_axis(stitched, class_map[None].astype(np.int64), axis=0)[0].astype(np.float32)
        class_map[unobserved] = IGNORE_LABEL
        confidence[unobserved] = np.nan
        return SegmentationPrediction(class_map=class_map, confidence=confidence, class_names=CLASS_NAMES)

    def _predict_tile(self, tile: np.ndarray) -> np.ndarray:
        """Per-class probabilities for one window, upsampled to the window's own size."""
        import torch

        tile_height, tile_width = tile.shape[:2]
        pixels = np.nan_to_num(tile.astype(np.float32), nan=0.0)
        if np.issubdtype(tile.dtype, np.integer) or pixels.max() > 1.0:
            pixels = pixels / 255.0
        normalised = (pixels - self.image_mean) / self.image_std
        pixel_values = torch.from_numpy(np.ascontiguousarray(normalised.transpose(2, 0, 1)))[None].to(self.device)
        with torch.inference_mode():
            logits = self._module(pixel_values=pixel_values).logits
            logits = torch.nn.functional.interpolate(
                logits, size=(tile_height, tile_width), mode="bilinear", align_corners=False
            )
            probabilities = torch.softmax(logits, dim=1)[0]
        return probabilities.float().cpu().numpy()


async def load_segformer(device: str) -> SegFormerAdapter:
    """Fetch the repository snapshot and build the model and its processor on the device."""
    record = FLEET[ModelId.SEGFORMER_LANDCOVER]
    assert record.weights is not None
    snapshot = await fetch_repository(record.weights)
    import asyncio

    module, mean, std = await asyncio.to_thread(_build, snapshot, device)
    return SegFormerAdapter(module, device, image_mean=mean, image_std=std)


def _build(snapshot: Path, device: str) -> tuple[object, tuple[float, ...], tuple[float, ...]]:
    import torch
    from transformers import SegformerForSemanticSegmentation

    module = SegformerForSemanticSegmentation.from_pretrained(snapshot)
    labels = tuple(module.config.id2label[index] for index in range(len(module.config.id2label)))
    if labels != CLASS_NAMES:
        raise ValueError(f"The checkpoint predicts {labels}, not the LoveDA classes this adapter names.")
    preprocessing = json.loads((snapshot / "preprocessor_config.json").read_text(encoding="utf-8"))
    if not preprocessing.get("do_normalize", False):
        raise ValueError("The checkpoint's preprocessor states no normalisation; this adapter assumes one.")
    module.eval()
    module.to(torch.device(device))
    logger.info("segformer built", extra={"snapshot": str(snapshot), "device": device, "classes": len(labels)})
    return module, tuple(preprocessing["image_mean"]), tuple(preprocessing["image_std"])
