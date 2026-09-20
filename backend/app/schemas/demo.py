"""Wire models for the canonical demo suite and offline verification.

what  : Defines Pydantic wire models for demonstration scenarios, execution requests, and run scorecards.
where : Used by app/controllers/demo_controller.py and app/routes/demo.py.
how   : Inherits from CamelCaseModel for automatic snake_case to camelCase JSON mapping.
"""

from typing import Any
from pydantic import Field

from app.lib.responses import CamelCaseModel


class DemoScenario(CamelCaseModel):
    """A single canonical demonstration scenario."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    modality: str = Field(min_length=1)
    query: str = Field(min_length=1)
    expected_intent: str = Field(min_length=1)
    expected_min_evidence: int = Field(ge=0)
    requires_sar: bool = Field(default=False)


class DemoManifest(CamelCaseModel):
    """Manifest describing the complete pre-computed offline bundle."""

    version: str
    bundle_id: str
    name: str
    description: str
    scenarios: list[DemoScenario] = Field(default_factory=list)


class DemoRunRequest(CamelCaseModel):
    """Request to execute one scenario or the full demo script."""

    scenario_id: str | None = None
    investigation_id: str | None = None
    iterations: int = Field(default=1, ge=1, le=10)


class DemoScenarioExecution(CamelCaseModel):
    """Outcome of running a single demonstration scenario."""

    scenario_id: str
    title: str
    query: str
    status: str
    duration_ms: int
    trace_id: str
    claims_count: int
    evidence_count: int
    confidence: float | None = None
    answer: str


class DemoSuiteResult(CamelCaseModel):
    """Overall outcome of running the demonstration suite."""

    bundle_id: str
    success: bool
    completed_runs: int
    total_duration_ms: int
    scenarios: list[DemoScenarioExecution] = Field(default_factory=list)


class DemoBundleStatus(CamelCaseModel):
    """Health and presence report for offline demonstration bundle."""

    status: str
    manifest_present: bool
    rasters_present: bool
    raster_paths: dict[str, str] = Field(default_factory=dict)
    scenario_count: int
    bundle_id: str
