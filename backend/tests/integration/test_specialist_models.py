"""The Phase 1.6 gate on real weights: ChangeFormer scored on LEVIR-CD, and two models evicting each other within a budget.

what  : Shape, range and invariant tests for the two resident models; the LEVIR-CD score; the
        back-to-back eviction with `warming` observed; a footprint measurement against the declared one;
        the SAR log-ratio service on a synthetic pair.
where : `tests/integration`. Needs torch (CUDA if there is one, CPU otherwise - the tests do not care
        which, only `test_declared_footprints` skips without a device), Redis for the load lock, and the
        network on first run: the checkpoints and the LEVIR-CD test split are fetched into `data/`.
how   : `code-standards.md` §11: *model inference is tested for shape, range and invariants, not for
        exact outputs.* The one number pinned is the benchmark score, and it is pinned below what was
        measured (recorded at the bottom) so a regression fails and a different GPU's rounding does not.
"""

import asyncio

import numpy as np
import pytest
import pytest_asyncio

from app.constants.datasets import DatasetId, DatasetSplit
from app.constants.fleet import FLEET
from app.constants.model_ids import ModelId
from app.constants.scenes import Polarisation
from app.constants.statuses import ModelHealth
from app.models.loader import Device, detect_device
from app.models.manager import ModelManager, get_manager, reset_manager
from app.models.registry import LOADERS
from app.services.change_detection.detector import detect_change
from app.services.change_detection.sar_change import detect_sar_change
from app.services.datasets.acquisition import fetch_hub_split
from app.services.datasets.loader import split_directory
from app.services.evaluation.change_detection import evaluate_change_detection
from app.services.preprocessing.sar_calibration import SarPreprocessingResult

pytestmark = pytest.mark.integration

# Measured: F1 0.789 on the first 128 test crops, 0.823 on all 2,048 (recorded below). Pinned below the
# subset's score so the test catches a wrong input convention or a broken load - those score 0.19 to
# 0.42 on the same crops - and not a GPU's rounding.
MINIMUM_LEVIR_F1 = 0.75
EVALUATION_SAMPLES = 128


# Module-scoped and on the session loop: the storage and Redis clients are bound to the loop that opened them.
@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def manager() -> ModelManager:
    manager = await get_manager()
    yield manager
    await reset_manager()


def synthetic_pair(seed: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """A textured 'before' and an 'after' with a bright rectangle painted on: an unambiguous change."""
    generator = np.random.default_rng(seed)
    before = generator.integers(60, 120, size=(256, 256, 3), dtype=np.uint8)
    after = before.copy()
    after[64:160, 96:200] = 235
    return before, after


async def test_changeformer_predicts_a_probability_map_with_the_right_shape_range_and_nodata(manager: ModelManager) -> None:
    before, after = synthetic_pair()
    before = before.astype(np.float32) / 255.0
    before[:8, :8] = np.nan

    result = await detect_change(before, after.astype(np.float32) / 255.0, manager=manager)

    assert result.probability.shape == (256, 256) and result.probability.dtype == np.float32
    observed = np.isfinite(result.probability)
    assert not observed[:8, :8].any(), "nodata in one date is unobserved in the result"
    assert observed[8:, 8:].all()
    assert ((result.probability[observed] >= 0.0) & (result.probability[observed] <= 1.0)).all()
    assert result.model_id is ModelId.CHANGEFORMER and result.model_version == FLEET[ModelId.CHANGEFORMER].version
    assert result.confidence is not None and 0.5 <= result.confidence <= 1.0
    assert result.latency_ms >= 0


async def test_changeformer_sees_more_change_in_a_changed_pair_than_an_identical_one(manager: ModelManager) -> None:
    """The invariant a change model must satisfy whatever it was trained on."""
    before, after = synthetic_pair()

    identical = await detect_change(before, before, manager=manager)
    changed = await detect_change(before, after, manager=manager)

    assert float(np.nanmean(changed.probability)) > float(np.nanmean(identical.probability))
    assert changed.changed_fraction > identical.changed_fraction


async def test_a_pair_on_two_grids_is_refused(manager: ModelManager) -> None:
    before, after = synthetic_pair()
    with pytest.raises(ValueError, match="one grid"):
        await detect_change(before, after[:128], manager=manager)


async def test_a_larger_scene_is_windowed_and_stitched_without_seams_of_nan(manager: ModelManager) -> None:
    generator = np.random.default_rng(5)
    before = generator.integers(60, 120, size=(400, 520, 3), dtype=np.uint8)
    after = before.copy()
    after[100:300, 100:300] = 240

    result = await detect_change(before, after, manager=manager)

    assert result.probability.shape == (400, 520)
    assert np.isfinite(result.probability).all(), "every pixel is covered by at least one window"
    assert result.mask[150:250, 150:250].mean() > result.mask[:80, :80].mean()


async def test_the_gate_changeformer_scores_on_levir_cd_test_crops(manager: ModelManager) -> None:
    """Change mask plus area statistics on LEVIR-CD test pairs, scored against ground truth."""
    if not split_directory(DatasetId.LEVIR_CD, DatasetSplit.TEST).exists():
        await fetch_hub_split(DatasetId.LEVIR_CD, DatasetSplit.TEST)

    report = await evaluate_change_detection(manager=manager, limit=EVALUATION_SAMPLES)

    assert report.samples == EVALUATION_SAMPLES
    assert report.score.f1 >= MINIMUM_LEVIR_F1, (
        f"F1 {report.score.f1:.3f} on the change class - a broken load or the wrong input convention "
        "scores 0.19 to 0.42 on these crops, the measured checkpoint 0.79"
    )
    assert report.score.iou >= 0.65
    assert report.truth_hectares > 0 and report.predicted_hectares > 0
    # Areas at 0.5 m: within a third of each other when the mask is right, orders apart when it is not.
    assert 0.66 < report.predicted_hectares / report.truth_hectares < 1.5


async def test_segformer_predicts_a_land_cover_class_per_pixel(manager: ModelManager) -> None:
    generator = np.random.default_rng(7)
    image = generator.integers(0, 255, size=(300, 340, 3), dtype=np.uint8)

    async with manager.lease(ModelId.SEGFORMER_LANDCOVER) as model:
        prediction = await asyncio.to_thread(model.predict, image)

    assert prediction.class_map.shape == (300, 340)
    assert prediction.confidence.shape == (300, 340)
    classes = set(np.unique(prediction.class_map).tolist())
    assert 0 not in classes, "the Ignore label is never predicted"
    assert classes <= set(range(1, 8))
    assert ((prediction.confidence >= 0.0) & (prediction.confidence <= 1.0)).all()
    assert prediction.class_names[2] == "Building" and prediction.class_names[4] == "Water"


async def test_the_gate_two_models_back_to_back_evict_within_a_budget_and_warming_is_seen() -> None:
    """The second half of the 1.6 gate, with the real loaders and a budget that fits one model."""
    device = await detect_device()
    budget = max(FLEET[ModelId.CHANGEFORMER].vram_megabytes, FLEET[ModelId.SEGFORMER_LANDCOVER].vram_megabytes)
    manager = ModelManager(
        device=Device(device.kind, device.name, device.total_megabytes, device.profile, budget), loaders=LOADERS
    )
    observed: list[ModelHealth] = []

    async def watch(model_id: ModelId) -> None:
        for _ in range(600):
            observed.append((await manager.status()).models[list(FLEET).index(model_id)].health)
            await asyncio.sleep(0.05)

    watcher = asyncio.create_task(watch(ModelId.CHANGEFORMER))
    async with manager.lease(ModelId.CHANGEFORMER):
        pass
    watcher.cancel()
    assert manager.resident_ids == (ModelId.CHANGEFORMER,)
    assert ModelHealth.WARMING in observed

    async with manager.lease(ModelId.SEGFORMER_LANDCOVER) as model:
        assert model is not None
    assert manager.resident_ids == (ModelId.SEGFORMER_LANDCOVER,)
    assert manager.health_of(ModelId.CHANGEFORMER) is ModelHealth.OFFLINE
    assert manager.health_of(ModelId.SEGFORMER_LANDCOVER) in (ModelHealth.ONLINE, ModelHealth.DEGRADED)
    await manager.unload_all()


async def test_declared_footprints_are_not_smaller_than_measured(manager: ModelManager) -> None:
    """The constants the manager admits by. Measured after a forward pass at the working tile."""
    if not manager.device.has_accelerator:
        pytest.skip("footprints are measured on a CUDA device")
    import torch

    for model_id, run in (
        (ModelId.CHANGEFORMER, lambda m: m.predict(*synthetic_pair())),
        (ModelId.SEGFORMER_LANDCOVER, lambda m: m.predict(np.zeros((512, 512, 3), dtype=np.uint8))),
    ):
        await manager.unload_all()
        torch.cuda.reset_peak_memory_stats()
        async with manager.lease(model_id) as model:
            await asyncio.to_thread(run, model)
            peak = int(torch.cuda.max_memory_allocated() // (1 << 20))
        assert FLEET[model_id].vram_megabytes >= peak, (
            f"{model_id.value} peaked at {peak} MB; constants/fleet.py declares {FLEET[model_id].vram_megabytes}"
        )


async def test_sar_change_keeps_increase_and_decrease_apart_and_unseen_ground_unjudged() -> None:
    def date(power: np.ndarray, *, layover: np.ndarray | None = None) -> SarPreprocessingResult:
        shape = power.shape
        return SarPreprocessingResult(
            polarisation=Polarisation.VV, calibrated_power=power, filtered_power=power,
            terrain_corrected_power=power, backscatter_decibels=10 * np.log10(power),
            layover_mask=layover if layover is not None else np.zeros(shape, bool),
            shadow_mask=np.zeros(shape, bool), local_incidence_degrees=np.full(shape, 35.0, np.float32),
        )

    before = np.full((4, 4), 0.01, dtype=np.float32)
    after = before.copy()
    after[0, 0] = 0.03  # +4.8 dB: rougher, wetter, or built
    after[1, 1] = 0.003  # -5.2 dB: smoother or drier
    layover = np.zeros((4, 4), bool)
    layover[2, 2] = True

    result = await detect_sar_change(date(before), date(after, layover=layover))

    assert result.increase[0, 0] and not result.decrease[0, 0]
    assert result.decrease[1, 1] and not result.increase[1, 1]
    assert not result.observed[2, 2], "layover on either date is unobserved, not unchanged"
    assert result.changed.sum() == 2
    assert result.model_id is ModelId.SAR_CHANGE and result.confidence is None


async def test_a_misaligned_pair_is_refused_before_the_model_is_ever_loaded() -> None:
    """§8 rule 2, in front of S13: the residual gate refuses, and the detector is not leased at all."""
    from scipy.ndimage import shift as shift_array

    from app.lib.exceptions import InvalidRequestError
    from app.services.change_detection.comparison import compare_pair

    manager = ModelManager(device=await detect_device(), loaders=LOADERS)
    generator = np.random.default_rng(11)
    reference = generator.normal(loc=2000.0, scale=300.0, size=(256, 256)).astype(np.float32)
    # The 1.3 construction of a pair that is aligned on average and wrong in every tile.
    moving = reference.copy()
    moving[:128] = shift_array(reference[:128], (0.0, 4.0), order=1, mode="nearest")
    moving[128:] = shift_array(reference[128:], (0.0, -4.0), order=1, mode="nearest")
    rgb = np.repeat(np.clip(reference / 3000.0 * 255.0, 0, 255).astype(np.uint8)[..., None], 3, axis=2)

    with pytest.raises(InvalidRequestError, match="[Rr]efused"):
        await compare_pair(rgb, rgb, alignment_before=reference, alignment_after=moving, manager=manager)

    assert manager.resident_ids == (), "a refused comparison must not have cost a model load"
    assert manager.health_of(ModelId.CHANGEFORMER) is ModelHealth.OFFLINE

    good = await compare_pair(rgb, rgb, alignment_before=reference, alignment_after=reference, manager=manager)
    assert good.registration.measurement.residual_pixels < 0.5
    assert good.change.changed_fraction == 0.0
    await manager.unload_all()
