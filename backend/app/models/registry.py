"""Names every model in the fleet and how this process loads it - the one table the manager and the CLI read.

what  : `LOADERS`, mapping each learned `ModelId` to the loader that builds its adapter on a device;
        `describe()` for one model's fleet record.
where : `app/models/manager.py`'s `get_manager()` builds the process-wide manager from `LOADERS`;
        `aeris models` reads `describe()`. The fixed facts - versions, weights, footprints - are
        `constants/fleet.py`; this module is the binding of those facts to code.
how   : A model with a fleet record and no loader is refused by the manager with a message naming the
        gap, which is what a registry is for: the twelve ids are the frontend's vocabulary, and the fleet
        must be able to say, for every one of them, whether it can be served here and why not.
"""

from typing import Final

from app.constants.fleet import FLEET, FleetRecord
from app.constants.model_ids import ModelId
from app.models.change import load_changeformer
from app.models.manager import Loader
from app.models.segmentation import load_segformer

LOADERS: Final[dict[ModelId, Loader]] = {
    ModelId.CHANGEFORMER: load_changeformer,
    ModelId.SEGFORMER_LANDCOVER: load_segformer,
}


def describe(model_id: ModelId) -> FleetRecord:
    return FLEET[model_id]
