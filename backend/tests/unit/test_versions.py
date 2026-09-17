"""Unit tests for investigation workspace versioning and snapshot comparison."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.history import InvestigationHistory, InvestigationVersion
from app.db.models.investigation import Investigation
from app.lib.exceptions import ResourceNotFoundError
from app.services.versions.manager import (
    compare_version_snapshots,
    get_version,
    list_versions,
    restore_version,
    save_version,
)


def test_investigation_version_to_wire() -> None:
    now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
    version = InvestigationVersion(
        id="ver_abc123",
        investigation_id="inv_test",
        name="Threshold 0.5 Baseline",
        created_at=now,
        updated_at=now,
        state={
            "snapshot": {
                "traceId": "trc_1",
                "layerIds": ["layer-1"],
                "steps": [],
                "resultSummary": {"claimMetrics": [], "confidence": 0.85},
            },
            "actor": "operator",
            "parentVersionId": None,
        },
    )

    wire = version.to_wire()
    assert wire["id"] == "ver_abc123"
    assert wire["label"] == "Threshold 0.5 Baseline"
    assert wire["actor"] == "operator"
    assert wire["parentVersionId"] is None
    assert wire["snapshot"]["traceId"] == "trc_1"
    assert "2026-09-17" in wire["createdAt"]


def test_investigation_history_to_wire() -> None:
    now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
    history = InvestigationHistory(
        id="his_abc123",
        investigation_id="inv_test",
        at=now,
        actor="operator",
        command_id="investigation.saveVersion",
        params={"versionId": "ver_abc123"},
        summary="Saved version 'Threshold 0.5 Baseline'",
    )

    wire = history.to_wire()
    assert wire["id"] == "his_abc123"
    assert wire["investigationId"] == "inv_test"
    assert wire["actor"] == "operator"
    assert wire["commandId"] == "investigation.saveVersion"
    assert wire["summary"] == "Saved version 'Threshold 0.5 Baseline'"


def test_compare_version_snapshots_detects_parameter_and_metric_deltas() -> None:
    v1 = {
        "id": "ver_1",
        "snapshot": {
            "timelinePair": {"baselineSceneId": "scene-1", "comparisonSceneId": "scene-2"},
            "steps": [
                {
                    "operationId": "change-detection",
                    "parameters": {"threshold": 0.5, "method": "changeformer"},
                }
            ],
            "resultSummary": {
                "claimMetrics": [{"label": "Changed Area (ha)", "value": 15.0}],
                "confidence": 0.85,
            },
            "layerIds": ["layer-prob", "layer-mask-05"],
        },
    }

    v2 = {
        "id": "ver_2",
        "snapshot": {
            "timelinePair": {"baselineSceneId": "scene-1", "comparisonSceneId": "scene-2"},
            "steps": [
                {
                    "operationId": "change-detection",
                    "parameters": {"threshold": 0.7, "method": "changeformer"},
                }
            ],
            "resultSummary": {
                "claimMetrics": [{"label": "Changed Area (ha)", "value": 10.0}],
                "confidence": 0.90,
            },
            "layerIds": ["layer-prob", "layer-mask-07"],
        },
    }

    diff = compare_version_snapshots(v1, v2)
    assert diff["versionAId"] == "ver_1"
    assert diff["versionBId"] == "ver_2"
    assert not diff["timeline"]["baselineChanged"]
    assert not diff["timeline"]["comparisonChanged"]

    # Parameter diff
    assert "change-detection" in diff["parameterDiffs"]
    assert diff["parameterDiffs"]["change-detection"]["threshold"] == (0.5, 0.7)

    # Metric diff
    assert "Changed Area (ha)" in diff["metricDiffs"]
    metric = diff["metricDiffs"]["Changed Area (ha)"]
    assert metric["before"] == 15.0
    assert metric["after"] == 10.0
    assert metric["delta"] == -5.0

    # Layer diffs
    assert diff["layers"]["added"] == ["layer-mask-07"]
    assert diff["layers"]["removed"] == ["layer-mask-05"]
    assert diff["layers"]["shared"] == ["layer-prob"]

    # Confidence delta
    assert pytest.approx(diff["confidenceDelta"], 0.001) == 0.05


@pytest.mark.asyncio
async def test_save_and_get_version_lifecycle() -> None:
    session = AsyncMock()

    # 1. Non-existent investigation raises ResourceNotFoundError
    session.get.return_value = None
    with pytest.raises(ResourceNotFoundError):
        await save_version(
            session,
            investigation_id="inv_missing",
            label="Baseline",
            snapshot={},
        )

    # 2. Existing investigation saves successfully
    fake_inv = MagicMock(spec=Investigation)
    session.get.return_value = fake_inv
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    result = await save_version(
        session,
        investigation_id="inv_valid",
        label="Test Baseline",
        snapshot={"traceId": "trc_test"},
    )
    assert result["label"] == "Test Baseline"
    assert result["snapshot"]["traceId"] == "trc_test"
    assert session.add.call_count == 2  # Version + History entry
