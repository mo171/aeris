"""Unit tests for Layer 3 agent tools ensuring scientific computation and zero hardcoding."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import numpy as np
import pytest

from app.constants.model_ids import ModelId
from app.constants.intents import Intent
from app.schemas.orchestration import TaskSpec
from app.agents.tools.area import execute_area
from app.agents.tools.change import execute_change
from app.agents.tools.segment import execute_segment
from app.agents.tools.cross_modal import execute_cross_modal
from app.agents.harness.executor import execute_task_locally
from app.services.change_detection.detector import ChangeDetectionResult
from app.services.segmentation.segmenter import SegmentationResult


@pytest.mark.asyncio
async def test_execute_area_measures_real_pixels_and_hectares() -> None:
    # 100x100 array with a 20x20 active region
    pic = np.zeros((100, 100), dtype=np.uint8)
    pic[10:30, 10:30] = 1

    task = TaskSpec(
        task_id="T1",
        intent=Intent.INDEX_QUERY,
        target="water_body",
    )

    # 1. With nominal resolution (10m per pixel -> 400 pixels = 40,000 m2 = 4.00 ha)
    result = await execute_area(task, [pic], resolution_metres=10.0)
    assert result["type"] == "area"
    assert result["target"] == "water_body"
    assert result["unit"] == "ha"
    assert abs(result["hectares"] - 4.0) < 1e-3
    assert result["region_count"] == 1
    assert abs(result["coverage_fraction"] - 0.04) < 1e-3

    # 2. Without nominal resolution (raw pixels)
    result_px = await execute_area(task, [pic], resolution_metres=None)
    assert result_px["unit"] == "px"
    assert result_px["hectares"] == 400.0
    assert result_px["region_count"] == 1


@pytest.mark.asyncio
async def test_execute_change_calls_detector_and_computes_metrics() -> None:
    img_t0 = np.zeros((64, 64, 3), dtype=np.uint8)
    img_t1 = np.ones((64, 64, 3), dtype=np.uint8) * 255

    task = TaskSpec(
        task_id="T2",
        intent=Intent.CHANGE_DETECT,
        target="vegetation_loss",
    )

    mock_manager = MagicMock()
    mock_model = MagicMock()
    # Mock probability map with 25% change
    prob = np.zeros((64, 64), dtype=np.float32)
    prob[:32, :32] = 0.85
    mock_model.predict.return_value = prob

    mock_manager.lease.return_value.__aenter__.return_value = mock_model
    mock_manager.lease.return_value.__aexit__.return_value = None
    mock_manager.record_latency = AsyncMock()

    result = await execute_change(task, [img_t0, img_t1], manager=mock_manager)
    assert result["type"] == "change_detection"
    assert result["target"] == "vegetation_loss"
    assert result["changed_fraction"] == 0.25
    assert abs(result["confidence"] - 0.9625) < 1e-3
    assert result["model_id"] == ModelId.CHANGEFORMER.value


@pytest.mark.asyncio
async def test_execute_segment_computes_class_coverage() -> None:
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    task = TaskSpec(
        task_id="T3",
        intent=Intent.SEGMENT,
        target="water",
    )

    mock_manager = MagicMock()
    mock_model = MagicMock()
    class_map = np.zeros((64, 64), dtype=np.int32)
    class_map[:16, :] = 1  # 25% class 1 (water)
    conf = np.ones((64, 64), dtype=np.float32) * 0.92

    prediction = MagicMock()
    prediction.class_map = class_map
    prediction.confidence = conf
    prediction.class_names = ("background", "water", "built_up")
    mock_model.predict.return_value = prediction

    mock_manager.lease.return_value.__aenter__.return_value = mock_model
    mock_manager.lease.return_value.__aexit__.return_value = None
    mock_manager.record_latency = AsyncMock()

    result = await execute_segment(task, [img], manager=mock_manager)
    assert result["type"] == "segmentation"
    assert result["target"] == "water"
    assert result["coverage_fraction"] == 0.25
    assert abs(result["confidence"] - 0.92) < 1e-4
    assert result["model_id"] == ModelId.SEGFORMER_LANDCOVER.value


@pytest.mark.asyncio
async def test_execute_cross_modal_assesses_temporal_offset_and_verdict() -> None:
    task = TaskSpec(
        task_id="T4",
        intent=Intent.CHANGE_DETECT,
        target="cross_modal_fusion",
    )
    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)  # 4 days apart (< 12 days -> fair)

    result = await execute_cross_modal(task, optical_captured_at=t0, radar_captured_at=t1, residual_pixels=0.45)
    assert result["type"] == "cross_modal_analysis"
    assert result["verdict"] == "fair"
    assert result["offset_days"] == 4
    assert result["co_registration_pixels"] == 0.45
    assert result["refusal"] is None

    # Now test unusable pair (> 30 days)
    t_distant = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
    result_distant = await execute_cross_modal(task, optical_captured_at=t0, radar_captured_at=t_distant, residual_pixels=0.45)
    assert result_distant["verdict"] == "unusable"
    assert result_distant["refusal"] == "poor-co-registration"


@pytest.mark.asyncio
async def test_execute_task_locally_dispatches_correctly() -> None:
    pic = np.zeros((32, 32, 3), dtype=np.uint8)
    pic[5:15, 5:15] = 255
    task = TaskSpec(
        task_id="T5",
        intent=Intent.INDEX_QUERY,
        target="water",
    )
    mock_manager = MagicMock()

    # Dispatch to area
    res_area = await execute_task_locally(task, "area", [pic], [False], mock_manager)
    assert res_area["type"] == "area"
    assert res_area["unit"] == "ha"

    # Dispatch to optical-sar-fusion
    task_cm = TaskSpec(task_id="T6", intent=Intent.CHANGE_DETECT, target="fusion_pair")
    res_cm = await execute_task_locally(task_cm, "optical-sar-fusion", [pic, pic], [False, True], mock_manager)
    assert res_cm["type"] == "cross_modal_analysis"
    assert res_cm["verdict"] in ("fair", "offset", "unusable")
