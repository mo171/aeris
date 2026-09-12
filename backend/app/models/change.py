"""Runs ChangeFormerV6 over a co-registered image pair and returns the probability that each pixel changed.

what  : `ChangeFormerAdapter` - `predict()` for one pair of any size, windowed at the model's 256-pixel
        tile and stitched - and `load_changeformer()`, the loader the manager calls.
where : Leased from `app/models/manager.py` by `services/change_detection/detector.py`. The architecture
        is `app/models/vendor/changeformer_v6.py`; the checkpoint is `constants/fleet.py`'s.
how   : **The model is a function of two RGB tiles in the range its training used, and nothing else** -
        and that range was measured, not read off the paper. The original ChangeFormer loader normalises
        to [-1, 1] (mean 0.5, std 0.5); HZDR's checkpoint was trained through their own loader, and on
        the LEVIR-CD test crops it scores **F1 0.82 on RGB in [0, 1]**, 0.21 on [-1, 1], 0.19 on ImageNet
        mean/std and 0.42 on BGR. Every wrong convention produces a plausible-looking mask, which is why
        the evaluation harness exists and why `INPUT_MEAN` and `INPUT_STD` are stated once, here, with
        the numbers that chose them.

        Larger inputs are windowed with the S11 grid (`imagery/math/windowing.py`) at 256 with the fleet
        overlap and stitched with the edge-weighted blend, so a Sentinel-2 subset runs through the same
        code path as a benchmark crop. A pair that is not the same shape is refused: change detection on
        two grids is the comparison §8 rule 2 exists to prevent, and the residual gate in
        `services/change_detection/comparison.py` runs before this is ever called.

        The output is the softmax probability of the change class, float32 on [0, 1], NaN where either
        input was NaN - the model never sees nodata as a colour.

        Sync methods, called through `asyncio.to_thread` by the service (`code-standards.md` §7): a forward
        pass blocks for its whole duration, and pretending otherwise would stall the voice stream.
"""

import logging
from pathlib import Path

import numpy as np

from app.constants.fleet import FLEET
from app.constants.model_ids import ModelId
from app.constants.raster import INFERENCE_TILE_OVERLAP
from app.models.loader import fetch_weights
from app.services.imagery.math.windowing import plan_tile_grid, stitch_windows

logger = logging.getLogger(__name__)

# What the checkpoint's training loader did to an 8-bit RGB crop: /255, and nothing else. Measured - see
# the header; the paper's [-1, 1] convention scores a quarter of this on the same crops.
INPUT_MEAN = 0.0
INPUT_STD = 1.0
CHECKPOINT_PREFIX = "CD_model."
TILE_OVERLAP = min(INFERENCE_TILE_OVERLAP, 32)


class ChangeFormerAdapter:
    """One resident ChangeFormerV6 on one device."""

    def __init__(self, module: object, device: str) -> None:
        self._module = module
        self.device = device
        self.tile_size = FLEET[ModelId.CHANGEFORMER].tile_size or 256

    def predict(self, before: np.ndarray, after: np.ndarray) -> np.ndarray:
        """Change probability per pixel for a pair of (H, W, 3) RGB arrays on the same grid.

        Accepts 8-bit integers or floats already on [0, 1]. Windowed when larger than the tile, so the
        model always sees the resolution and extent it was trained at.
        """
        if before.shape != after.shape or before.ndim != 3 or before.shape[2] != 3:
            raise ValueError(
                f"A pair must be two (H, W, 3) arrays on one grid; got {before.shape} and {after.shape}."
            )
        height, width = before.shape[:2]
        unobserved = ~(np.isfinite(before).all(axis=2) & np.isfinite(after).all(axis=2))

        windows = plan_tile_grid(width=width, height=height, tile_size=self.tile_size, overlap=TILE_OVERLAP)
        predictions = [self._predict_tile(before[w.as_slices()], after[w.as_slices()]) for w in windows]
        probability = stitch_windows(
            windows, predictions, shape=(height, width), tile_size=self.tile_size, overlap=TILE_OVERLAP
        )
        probability[unobserved] = np.nan
        return probability

    def _predict_tile(self, before: np.ndarray, after: np.ndarray) -> np.ndarray:
        import torch

        tile_height, tile_width = before.shape[:2]
        # A window at the raster's edge can be smaller than the tile; the grid never pads, so the model is
        # given what there is, which its convolutions accept, and the output is cut to the same size.
        x1 = self._to_tensor(before)
        x2 = self._to_tensor(after)
        with torch.inference_mode():
            outputs = self._module(x1, x2)
            logits = outputs[-1] if isinstance(outputs, (list, tuple)) else outputs
            probability = torch.softmax(logits, dim=1)[0, 1]
        return probability[:tile_height, :tile_width].float().cpu().numpy()

    def _to_tensor(self, image: np.ndarray) -> object:
        import torch

        values = image.astype(np.float32, copy=False)
        if np.issubdtype(image.dtype, np.integer):
            values = values / 255.0
        values = np.nan_to_num(values, nan=0.0)
        normalised = (values - INPUT_MEAN) / INPUT_STD
        tensor = torch.from_numpy(np.ascontiguousarray(normalised.transpose(2, 0, 1)))[None]
        return tensor.to(self.device)


async def load_changeformer(device: str) -> ChangeFormerAdapter:
    """Fetch the checkpoint, build the vendored architecture, load the weights, move to the device."""
    record = FLEET[ModelId.CHANGEFORMER]
    assert record.weights is not None
    checkpoint = await fetch_weights(record.weights)
    import asyncio

    module = await asyncio.to_thread(_build, checkpoint, device)
    return ChangeFormerAdapter(module, device)


def _build(checkpoint: Path, device: str) -> object:
    import torch
    from safetensors.torch import load_file

    from app.models.vendor.changeformer_v6 import ChangeFormerV6

    module = ChangeFormerV6(input_nc=3, output_nc=2, decoder_softmax=False, embed_dim=256)
    tensors = load_file(str(checkpoint))
    state = {
        key.removeprefix(CHECKPOINT_PREFIX): value
        for key, value in tensors.items()
        if key.startswith(CHECKPOINT_PREFIX)
    }
    missing, unexpected = module.load_state_dict(state, strict=False)
    if missing or unexpected:
        # Strict, in effect: a checkpoint that does not fit the architecture is not "mostly loaded".
        raise ValueError(
            f"ChangeFormerV6 and {checkpoint.name} disagree: {len(missing)} parameters missing, "
            f"{len(unexpected)} unexpected. First missing: {missing[:3]}; first unexpected: {unexpected[:3]}."
        )
    module.eval()
    module.to(torch.device(device))
    logger.info("changeformer built", extra={"checkpoint": str(checkpoint), "device": device, "tensors": len(state)})
    return module
