"""The twelve model identifiers, and the capability vocabulary they are described with.

what  : `ModelId` (12 members) and `ModelCapability` (9 members).
where : Every claim, every trace step and `GET /models/status` carry a `ModelId`. Transcribed from
        `frontend/lib/constants/models.ts`.
how   : **One vocabulary, exactly these strings.** `api-contract.md` §7 records why: a claim that says
        `changeformer` while the fleet registry says `mdl_changeformer` makes "which model produced this
        claim, and why was it chosen" unanswerable by joining the two. That bug was already found and fixed
        once on the frontend; re-introducing it from this side would be a regression against a known defect.

        The mapping from model to capabilities is not here. It is fleet truth, established when the models
        are actually wired up (Phase 1.6, 1.7) rather than guessed now, and a wrong mapping would route a
        request to a model that cannot serve it.
"""

from enum import StrEnum


class ModelId(StrEnum):
    """A model in the AERIS fleet. The value is what appears on the wire and in every claim."""

    REMOTE_SENSING_VLM = "rs-vlm"
    GROUNDING_DINO_SAM = "grounding-dino-sam"
    CHANGEFORMER = "changeformer"
    SAR_CHANGE = "sar-change"
    SEGFORMER_LANDCOVER = "segformer-landcover"
    DOTA_DETECTOR = "dota-detector"
    INDEX_ENGINE = "index-engine"
    GEOSPATIAL_ENGINE = "geospatial-engine"
    OPTICAL_SAR_FUSION = "optical-sar-fusion"
    S2CLOUDLESS = "s2cloudless"
    CO_REGISTRATION = "co-registration"
    SAR_PREPROCESS = "sar-preprocess"


class ModelCapability(StrEnum):
    """What a model can do. Used to explain a routing decision, never to guess one."""

    VISION_LANGUAGE = "vision-language"
    GROUNDING = "grounding"
    CHANGE_DETECTION = "change-detection"
    SEGMENTATION = "segmentation"
    OBJECT_DETECTION = "object-detection"
    SPECTRAL_INDEX = "spectral-index"
    CROSS_MODAL_FUSION = "cross-modal-fusion"
    PREPROCESSING = "preprocessing"
    SPATIAL_STATISTICS = "spatial-statistics"
