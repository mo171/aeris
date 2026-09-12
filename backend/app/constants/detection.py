"""What the object detector finds, how sure it must be, and how its tiles are merged - fixed sets, not code.

what  : `DOTA_CLASS_NAMES` in the checkpoint's index order, the confidence and overlap thresholds, and the
        oriented-box precision the wire carries.
where : `app/models/detection.py` checks the checkpoint's names against this; `services/detection/` reads
        the thresholds; the evaluation harness scores at `DETECTION_MATCH_IOU`.
how   : DOTA v1.0's fifteen categories (Xia et al. 2018), in the order YOLO-OBB's `names` states them.
        A class map that disagreed with the checkpoint would label every ship a plane, so the adapter
        refuses a checkpoint whose names differ rather than trusting the index.
"""

from typing import Final

DOTA_CLASS_NAMES: Final[tuple[str, ...]] = (
    "plane", "ship", "storage tank", "baseball diamond", "tennis court", "basketball court",
    "ground track field", "harbor", "bridge", "large vehicle", "small vehicle", "helicopter",
    "roundabout", "soccer ball field", "swimming pool",
)

# Below this the detector's own score is not reported as a detection. Ultralytics' default; DOTA mAP is
# published at 0.001 for the curve, but a detection the pipeline states is one it would defend.
DETECTION_CONFIDENCE_THRESHOLD: Final[float] = 0.25

# Two boxes of one class that overlap this much across a tile seam are the same object seen twice; the
# less confident one goes. Also the overlap at which a prediction counts as a hit in evaluation - the
# customary 0.5 for DOTA.
DETECTION_NMS_IOU: Final[float] = 0.5
DETECTION_MATCH_IOU: Final[float] = 0.5

# The detector's working tile and the overlap between neighbours. DOTA is tiled at 1024 with a 200-pixel
# overlap in the published protocol; 128 keeps a large vehicle whole across a seam at a third of the cost.
DETECTION_TILE_SIZE: Final[int] = 1024
DETECTION_TILE_OVERLAP: Final[int] = 128

# Pixel coordinates on the wire. A box corner to a tenth of a pixel is already more than the model knows.
BOX_COORDINATE_DECIMALS: Final[int] = 1
