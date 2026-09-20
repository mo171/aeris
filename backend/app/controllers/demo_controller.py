"""Controller for canonical demonstration endpoints and offline bundle operations.

what  : Coordinates demonstration scenario retrieval, bundle validation, database seeding, and script execution.
where : Called by app/routes/demo.py and CLI demo command.
how   : Delegates domain logic to services/demo/bundle.py and services/demo/runner.py.
"""

import logging
from typing import Any

from app.schemas.demo import (
    DemoBundleStatus,
    DemoManifest,
    DemoRunRequest,
    DemoScenario,
    DemoSuiteResult,
)
from app.services.demo import bundle as demo_bundle
from app.services.demo import runner as demo_runner

logger = logging.getLogger(__name__)


async def get_manifest() -> DemoManifest:
    """Retrieve the demonstration scenarios manifest."""
    return demo_runner.get_demo_manifest()


async def get_scenarios() -> list[DemoScenario]:
    """List available demonstration scenarios."""
    manifest = demo_runner.get_demo_manifest()
    return manifest.scenarios


async def get_bundle_status() -> DemoBundleStatus:
    """Check integrity of the offline demonstration bundle."""
    report = await demo_bundle.verify_offline_bundle()
    return DemoBundleStatus.model_validate(report)


async def seed_bundle() -> dict[str, Any]:
    """Seed the database with pre-computed demonstration project, scenes, and investigation."""
    return await demo_bundle.seed_demo_environment()


async def run_demo(request: DemoRunRequest) -> DemoSuiteResult:
    """Execute the canonical demo suite or a specific scenario."""
    if request.scenario_id:
        single_result = await demo_runner.execute_demo_scenario(request.scenario_id)
        return DemoSuiteResult(
            bundle_id="bnd_aeris_sih2026_canonical",
            success=single_result.status == "complete",
            completed_runs=1,
            total_duration_ms=single_result.duration_ms,
            scenarios=[single_result],
        )

    return await demo_runner.execute_full_demo_suite(iterations=request.iterations)
