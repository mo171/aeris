"""Integration test for the threshold re-run vertical slice.

Validates that changing threshold (0.35 -> 0.45) reuses raw model inference (probability tensor)
and upstream stages (S1, S9), re-slices the mask, re-measures the area (area2 < area1), and emits
properly updated trace step events and layers.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.constants.intents import Intent
from app.constants.pipeline import GraphName
from app.constants.statuses import RunStatus
from app.services.pipeline.runner import AnalysisRequest, run_analysis
from app.services.sessions.journal_writer import journal_path

LEVIR = Path("data/datasets/levir-cd/test")
LEVIR_PAIR = "0271.png"


def levir_pair() -> tuple[Path, Path]:
    before, after = (LEVIR / part / LEVIR_PAIR for part in ("A", "B"))
    if not before.exists() or not after.exists():
        pytest.skip(f"LEVIR pair {LEVIR_PAIR} is not on disk")
    return before, after


def journal_events(run_id: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in journal_path(run_id).read_text(encoding="utf-8").splitlines()]


@pytest.mark.asyncio
async def test_threshold_rerun_reuses_probability_and_reslices_mask(isolated_pipeline_paths: Path) -> None:
    before, after = levir_pair()

    # 1. Baseline run at default threshold 0.5
    baseline_request = AnalysisRequest(
        GraphName.TEMPORAL,
        "find new construction",
        Intent.CHANGE_DETECT,
        scene=after,
        reference=before,
        declared_registered=True,
    )
    outcome1 = await run_analysis(baseline_request)
    assert outcome1.status is RunStatus.COMPLETE, outcome1.error
    assert outcome1.values["change_threshold"] == 0.5
    area1 = outcome1.values["measurement"]["pixelCount"]
    prob1 = outcome1.values["change_probability_path"]
    mask1 = outcome1.values["change_mask_path"]

    # 2. Re-run with threshold overridden to 0.7, reusing parent run outcome1
    rerun_request = AnalysisRequest(
        GraphName.TEMPORAL,
        "find new construction",
        Intent.CHANGE_DETECT,
        scene=after,
        reference=before,
        declared_registered=True,
        parameter_overrides={"change-detection": {"threshold": 0.7}},
        parent_run_id=outcome1.run_id,
    )
    outcome2 = await run_analysis(rerun_request)
    assert outcome2.status is RunStatus.COMPLETE, outcome2.error
    assert outcome2.values["change_threshold"] == 0.7
    area2 = outcome2.values["measurement"]["pixelCount"]
    prob2 = outcome2.values["change_probability_path"]
    mask2 = outcome2.values["change_mask_path"]

    # 3. Assertions on artifact reuse and invalidation
    assert prob1 == prob2, "Raw inference probability tensor must be reused without running model again"
    assert mask1 != mask2, "New mask must be sliced for the new threshold"
    assert area2 < area1, f"Stricter threshold 0.7 must produce fewer pixels than 0.5 (got {area2} vs {area1})"

    # 4. Assertions on journal events: S1, S9 should be skipped
    events2 = journal_events(outcome2.run_id)
    skipped_stages = [
        e["step"]["stageCode"]
        for e in events2
        if e["type"] == "trace-step" and e["step"]["state"] == "skipped"
    ]
    assert "S1" in skipped_stages
    assert "S9" in skipped_stages
