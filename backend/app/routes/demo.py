"""Route declarations for demonstration suite and offline bundle operations.

what  : Declares HTTP endpoints for running the demo suite, listing scenarios, and managing the offline bundle.
where : Mounted under /api/v1/demo in app/main.py.
how   : Thin route layer delegating directly to demo_controller.
"""

from typing import Any
from fastapi import APIRouter, status

from app.controllers import demo_controller
from app.schemas.demo import (
    DemoBundleStatus,
    DemoManifest,
    DemoRunRequest,
    DemoScenario,
    DemoSuiteResult,
)

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get(
    "/manifest",
    response_model=DemoManifest,
    status_code=status.HTTP_200_OK,
    summary="Get demo manifest",
)
async def get_manifest() -> DemoManifest:
    """Retrieve the full manifest of pre-computed demonstration scenarios."""
    return await demo_controller.get_manifest()


@router.get(
    "/scenarios",
    response_model=list[DemoScenario],
    status_code=status.HTTP_200_OK,
    summary="List demo scenarios",
)
async def list_scenarios() -> list[DemoScenario]:
    """List all available canonical demonstration scenarios."""
    return await demo_controller.get_scenarios()


@router.get(
    "/bundle",
    response_model=DemoBundleStatus,
    status_code=status.HTTP_200_OK,
    summary="Get offline bundle status",
)
async def get_bundle_status() -> DemoBundleStatus:
    """Check whether offline rasters and assets are ready on disk."""
    return await demo_controller.get_bundle_status()


@router.post(
    "/bundle/seed",
    status_code=status.HTTP_200_OK,
    summary="Seed demo environment",
)
async def seed_bundle() -> dict[str, Any]:
    """Seed the database with pre-computed demonstration project, scenes, and investigation."""
    return await demo_controller.seed_bundle()


@router.post(
    "/run",
    response_model=DemoSuiteResult,
    status_code=status.HTTP_200_OK,
    summary="Execute demo run",
)
async def run_demo(request: DemoRunRequest | None = None) -> DemoSuiteResult:
    """Execute the canonical demo script (or specific scenario) and return execution scorecard."""
    req = request or DemoRunRequest()
    return await demo_controller.run_demo(req)
