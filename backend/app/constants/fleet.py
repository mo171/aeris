"""What each of the twelve models actually is on this backend: its capability, its stages, where its weights come from, and what it costs to hold.

what  : `FleetRecord` per `ModelId`, the `MODEL_CAPABILITIES` and `MODEL_STAGES` mappings the frontend's
        `models.ts` states, the `VramProfile` tiers, and the residency defaults the manager works to.
where : Read by `app/models/registry.py` (which exposes it), `app/models/manager.py` (which loads and
        evicts by it) and `aeris models status`. Transcribed from `frontend/lib/constants/models.ts` for
        the capability and stage columns; the weights and footprints are ours.
how   : `constants/model_ids.py` deferred the model-to-capability mapping to "when the models are actually
        wired up rather than guessed now". This is that moment, and it is written as data because a
        mapping in code is a mapping nobody can list.

        **Two kinds of entry, and the distinction is the manager's whole job.** A *learned* model has
        weights, occupies VRAM, and can be `warming`, evicted, or `degraded` to CPU. A *deterministic engine*
        is code - the index engine, the geospatial engine, the SAR chain - and is `online` the moment the
        process is, with no residency to manage. Reporting an engine as `warming` would be theatre.

        **VRAM footprints are what a load actually costs, measured, not the size of the file.** Weights in
        fp32 plus activations at the model's working tile, on the device, after `torch.cuda.synchronize`.
        A footprint that is too small lets the manager admit a model that OOMs; too large evicts for no
        reason. The 1.6 gate is the eviction, so these numbers are load-bearing.

        The weights sources are Hugging Face Hub repositories, or a release asset at a URL pinned by its
        SHA-256. `changeformer` is HZDR-FWGEL's ChangeFormerV6 checkpoint trained on the 256-crop LEVIR-CD -
        the original wgcban architecture under `CD_model.` - and `segformer-landcover` is a SegFormer-B2
        fine-tuned on LoveDA. `dota-detector` is Ultralytics' YOLO11s-OBB trained on DOTA v1.0, **AGPL-3.0**
        (weights and the `ultralytics` package alike; the network copyleft is recorded in
        `constants/licences.py` and is a product decision before any hosted deployment). `rs-vlm` is Qwen3-VL
        (Apache-2.0) at the size `settings.vlm_size` names, with the BigEarthNet.txt LoRA adapter of
        `settings.vlm_adapter_repository` attached - `constants/vlm.py` has the variants. `grounding-dino-sam`
        is still owed. A model with no weights source reports `offline` and refuses to load, which is
        louder than a placeholder.
"""

from enum import StrEnum
from typing import Final, NamedTuple

from app.constants.model_ids import ModelCapability, ModelId
from app.constants.stages import PipelineStage
from app.constants.vlm import VLM_VARIANTS, VlmSize


class VramProfile(StrEnum):
    """The residency tiers the roadmap plans for, plus the two this laptop taught us to name."""

    CPU = "cpu"
    VRAM_4GB = "4gb"
    VRAM_8GB = "8gb"
    VRAM_16GB = "16gb"


# Total device memory at or above which a profile applies. Measured with `torch.cuda.mem_get_info`, not
# read from a name: an "8 GB" card with a desktop on it has six.
VRAM_PROFILE_THRESHOLDS_MEGABYTES: Final[tuple[tuple[int, VramProfile], ...]] = (
    (14_000, VramProfile.VRAM_16GB),
    (7_000, VramProfile.VRAM_8GB),
    (3_500, VramProfile.VRAM_4GB),
)

# The share of total device memory the manager may fill with resident models. The rest is working memory
# for the inference in flight - activations, the tile being read, CUDA's own context - and a manager that
# fills the card to the byte OOMs on the next tile rather than on the load.
VRAM_BUDGET_FRACTION: Final[float] = 0.75


class WeightsSource(NamedTuple):
    """Where a learned model's checkpoint is fetched from, pinned so a run names one artefact."""

    repository: str
    filename: str | None
    # A Hub git revision, or the SHA-256 of the file when `url` is set - either way, one artefact.
    revision: str
    # A direct download instead of the Hub, for weights published as release assets.
    url: str | None = None


class FleetRecord(NamedTuple):
    """Everything fixed about one model in the fleet."""

    model_id: ModelId
    version: str
    capability: ModelCapability
    stages: tuple[PipelineStage, ...]
    # `None` for a deterministic engine: code, not weights.
    weights: WeightsSource | None
    # What a load costs on the device, measured. Zero for an engine.
    vram_megabytes: int
    # The square tile the model was trained at and is run at; the tiler windows a scene to this.
    tile_size: int | None


FLEET: Final[dict[ModelId, FleetRecord]] = {
    ModelId.CHANGEFORMER: FleetRecord(
        model_id=ModelId.CHANGEFORMER,
        version="v6-levircd256-hzdr",
        capability=ModelCapability.CHANGE_DETECTION,
        stages=(PipelineStage.S13,),
        weights=WeightsSource("HZDR-FWGEL/UCD-LEVIRCD256-ChangeFormer", "model.safetensors", "main"),
        # Measured on the RTX 3050: 157 MB of weights, 461 MB peak through a 256 tile alone; 517 MB when
        # loaded after the detector in the same process (the allocator keeps a few MB). Declared above both.
        vram_megabytes=576,
        tile_size=256,
    ),
    ModelId.SEGFORMER_LANDCOVER: FleetRecord(
        model_id=ModelId.SEGFORMER_LANDCOVER,
        version="b2-loveda-wu-pr-gw",
        capability=ModelCapability.SEGMENTATION,
        stages=(PipelineStage.S13,),
        weights=WeightsSource("wu-pr-gw/segformer-b2-finetuned-with-LoveDA", None, "main"),
        # Measured on the RTX 3050: 104 MB of weights, 556 MB peak through a 512 tile alone; 645 MB when
        # loaded after the other models in one process (allocator residue). Declared above both.
        vram_megabytes=704,
        tile_size=512,
    ),
    ModelId.SAR_CHANGE: FleetRecord(
        model_id=ModelId.SAR_CHANGE,
        version="1.6.0",
        capability=ModelCapability.CHANGE_DETECTION,
        stages=(PipelineStage.S13,),
        weights=None,
        vram_megabytes=0,
        tile_size=None,
    ),
    ModelId.INDEX_ENGINE: FleetRecord(
        ModelId.INDEX_ENGINE, "1.4.0", ModelCapability.SPECTRAL_INDEX, (PipelineStage.S12,), None, 0, None
    ),
    ModelId.GEOSPATIAL_ENGINE: FleetRecord(
        ModelId.GEOSPATIAL_ENGINE, "1.4.0", ModelCapability.SPATIAL_STATISTICS, (PipelineStage.S15,), None, 0, None
    ),
    ModelId.S2CLOUDLESS: FleetRecord(
        ModelId.S2CLOUDLESS, "1.7.3", ModelCapability.PREPROCESSING, (PipelineStage.S7,), None, 0, None
    ),
    ModelId.CO_REGISTRATION: FleetRecord(
        ModelId.CO_REGISTRATION, "1.3.0", ModelCapability.PREPROCESSING, (PipelineStage.S9,), None, 0, None
    ),
    ModelId.SAR_PREPROCESS: FleetRecord(
        ModelId.SAR_PREPROCESS, "1.3.0", ModelCapability.PREPROCESSING, (PipelineStage.S8,), None, 0, None
    ),
    ModelId.OPTICAL_SAR_FUSION: FleetRecord(
        ModelId.OPTICAL_SAR_FUSION, "0.0.0", ModelCapability.CROSS_MODAL_FUSION, (PipelineStage.S14,), None, 0, None
    ),
    ModelId.DOTA_DETECTOR: FleetRecord(
        model_id=ModelId.DOTA_DETECTOR,
        version="yolo11s-obb-dotav1",
        capability=ModelCapability.OBJECT_DETECTION,
        stages=(PipelineStage.S13, PipelineStage.S15),
        weights=WeightsSource(
            "ultralytics/assets", "yolo11s-obb.pt",
            "43fa63102922e0701501241b307420d24fc55e080816888b18bf8c6f96b1a45a",
            url="https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s-obb.pt",
        ),
        # Measured on the RTX 3050: 79 MB of weights, 225 MB peak through a 1024 tile. Declared with margin.
        vram_megabytes=320,
        tile_size=1024,
    ),
    # No weights source yet - see the header. Each reports `offline` and refuses to load.
    ModelId.GROUNDING_DINO_SAM: FleetRecord(
        ModelId.GROUNDING_DINO_SAM, "0.0.0", ModelCapability.GROUNDING, (PipelineStage.S13,), None, 0, None
    ),
    # The 2B base as the default record; `models/registry.py` swaps in the configured variant and adapter.
    ModelId.REMOTE_SENSING_VLM: FleetRecord(
        model_id=ModelId.REMOTE_SENSING_VLM,
        version=VLM_VARIANTS[VlmSize.SMALL_2B].version,
        capability=ModelCapability.VISION_LANGUAGE,
        stages=(PipelineStage.S14, PipelineStage.S16),
        weights=WeightsSource(VLM_VARIANTS[VlmSize.SMALL_2B].repository, None, VLM_VARIANTS[VlmSize.SMALL_2B].revision),
        vram_megabytes=VLM_VARIANTS[VlmSize.SMALL_2B].vram_megabytes,
        tile_size=None,
    ),
}

MODEL_CAPABILITIES: Final[dict[ModelId, ModelCapability]] = {
    model_id: record.capability for model_id, record in FLEET.items()
}
MODEL_STAGES: Final[dict[ModelId, tuple[PipelineStage, ...]]] = {
    model_id: record.stages for model_id, record in FLEET.items()
}

# Engines are code and have no residency; learned models have weights and live in the manager's budget.
DETERMINISTIC_ENGINES: Final[frozenset[ModelId]] = frozenset(
    model_id for model_id, record in FLEET.items() if record.weights is None and record.version != "0.0.0"
)
LEARNED_MODELS: Final[frozenset[ModelId]] = frozenset(
    model_id for model_id, record in FLEET.items() if record.weights is not None
)

# How many inference latencies a model keeps for `medianLatencyMs`. Enough to be a median, few enough
# that a model that sped up after a warm cache is reported as it is now rather than as it was.
LATENCY_WINDOW: Final[int] = 32

# The version string the wire carries for a learned model that could not be placed on any device.
UNAVAILABLE_VERSION: Final[str] = "0.0.0"
