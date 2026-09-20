"""Offline demonstration bundle management and database seeding.

what  : Verifies and generates pre-computed demonstration rasters and seeds the canonical demonstration
        investigation into PostGIS with full scene bindings.
where : Called by demo_controller, CLI demo command, and Phase 2.9 test suites.
how   : Conforms to PDF Phase 10 offline hardening requirements: guarantees that full multi-temporal
        and cross-modal demonstrations execute without network access to external satellite APIs.
"""

import asyncio
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from typing import Any

from geoalchemy2.shape import from_shape
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box
from sqlalchemy import select

from app.constants.geo import STORAGE_SRID
from app.constants.investigations import WorkspaceMode
from app.constants.scenes import SceneModality, SceneRole, TemporalRole
from app.constants.statuses import InvestigationStatus, SceneProcessingState
from app.db.models.investigation import Investigation, InvestigationScene
from app.db.models.project import Project
from app.db.models.scene import Scene
from app.lib import database

logger = logging.getLogger(__name__)

DEMO_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "demo"
RASTERS_DIR = DEMO_ROOT / "rasters"
MANIFEST_FILE = DEMO_ROOT / "manifest.json"

DEMO_PROJECT_ID = "prj_sih2026_demo"
DEMO_INVESTIGATION_ID = "inv_demo_canonical"
DEMO_SCENE_T0_ID = "scn_demo_optical_t0"
DEMO_SCENE_T1_ID = "scn_demo_optical_t1"
DEMO_SCENE_SAR_ID = "scn_demo_sar"

# Geographic coordinates for Beirut Port Demonstration Area
BEIRUT_WEST = 35.50
BEIRUT_SOUTH = 33.88
BEIRUT_EAST = 35.54
BEIRUT_NORTH = 33.92
BEIRUT_CENTER_LON = 35.52
BEIRUT_CENTER_LAT = 33.90


def _create_raster_file(
    file_path: Path,
    width: int = 128,
    height: int = 128,
    bands: int = 4,
    dtype: str = "uint16",
    fill_value: int = 1000,
    change_patch: bool = False,
) -> Path:
    """Create a synthetically consistent GeoTIFF for demo scenarios."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_origin(BEIRUT_WEST, BEIRUT_NORTH, (BEIRUT_EAST - BEIRUT_WEST) / width, (BEIRUT_NORTH - BEIRUT_SOUTH) / height)

    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": bands,
        "dtype": dtype,
        "crs": "EPSG:4326",
        "transform": transform,
        "nodata": 0,
    }

    with rasterio.open(file_path, "w", **profile) as dst:
        for b in range(1, bands + 1):
            arr = np.full((height, width), fill_value=fill_value * b, dtype=dtype)
            if change_patch and b == bands:
                # Introduce distinct change signal in quadrant
                arr[30:70, 30:70] = fill_value * 5
            dst.write(arr, b)

    return file_path


async def ensure_demo_rasters() -> dict[str, Path]:
    """Ensure all required offline demonstration GeoTIFF files exist on disk."""
    def _sync_create() -> dict[str, Path]:
        RASTERS_DIR.mkdir(parents=True, exist_ok=True)
        t0_path = RASTERS_DIR / "demo_optical_t0.tif"
        t1_path = RASTERS_DIR / "demo_optical_t1.tif"
        sar_path = RASTERS_DIR / "demo_sar.tif"

        if not t0_path.exists():
            _create_raster_file(t0_path, bands=4, fill_value=500, change_patch=False)
        if not t1_path.exists():
            _create_raster_file(t1_path, bands=4, fill_value=500, change_patch=True)
        if not sar_path.exists():
            _create_raster_file(sar_path, bands=2, fill_value=300, change_patch=False)

        return {
            "optical_t0": t0_path,
            "optical_t1": t1_path,
            "sar": sar_path,
        }

    return await asyncio.to_thread(_sync_create)


async def verify_offline_bundle() -> dict[str, Any]:
    """Audit the integrity of the offline demonstration bundle."""
    rasters = await ensure_demo_rasters()
    manifest_present = MANIFEST_FILE.exists()
    all_rasters_present = all(p.exists() for p in rasters.values())

    manifest_data = {}
    if manifest_present:
        manifest_data = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))

    return {
        "status": "ready" if (manifest_present and all_rasters_present) else "incomplete",
        "manifestPresent": manifest_present,
        "rastersPresent": all_rasters_present,
        "rasterPaths": {k: str(v) for k, v in rasters.items()},
        "scenarioCount": len(manifest_data.get("scenarios", [])),
        "bundleId": manifest_data.get("bundleId", "unknown"),
    }


async def seed_demo_environment() -> dict[str, Any]:
    """Seed the database with the pre-computed demonstration project, scenes, and investigation."""
    rasters = await ensure_demo_rasters()

    async with database.get_session() as session:
        # 1. Seed Project
        proj = await session.get(Project, DEMO_PROJECT_ID)
        if not proj:
            proj = Project(
                id=DEMO_PROJECT_ID,
                name="SIH 2026 Demonstration",
                description="Canonical offline demo project evaluating multimodal remote sensing workflows.",
            )
            session.add(proj)
            await session.flush()

        # 2. Seed Scenes
        footprint_geom = from_shape(box(BEIRUT_WEST, BEIRUT_SOUTH, BEIRUT_EAST, BEIRUT_NORTH), srid=STORAGE_SRID)
        centroid_geom = from_shape(Point(BEIRUT_CENTER_LON, BEIRUT_CENTER_LAT), srid=STORAGE_SRID)

        # Scene T0 Optical
        scene_t0 = await session.get(Scene, DEMO_SCENE_T0_ID)
        if not scene_t0:
            scene_t0 = Scene(
                id=DEMO_SCENE_T0_ID,
                name="Beirut Port Sentinel-2 Baseline (Pre-Event)",
                captured_at=datetime(2020, 7, 24, 8, 30, 0, tzinfo=UTC),
                ingested_at=datetime(2020, 7, 25, 0, 0, 0, tzinfo=UTC),
                modality=SceneModality.OPTICAL,
                sensor_platform="Sentinel-2B",
                band_count=4,
                ground_sample_distance_meters=10.0,
                cloud_cover_percentage=0.0,
                coordinate_reference_system="EPSG:4326",
                footprint=footprint_geom,
                centroid=centroid_geom,
                file_size_bytes=rasters["optical_t0"].stat().st_size,
                raw_object_key=f"demo/{rasters['optical_t0'].name}",
                processing_state=SceneProcessingState.READY,
                cog_object_key=str(rasters["optical_t0"]),
            )
            session.add(scene_t0)

        # Scene T1 Optical
        scene_t1 = await session.get(Scene, DEMO_SCENE_T1_ID)
        if not scene_t1:
            scene_t1 = Scene(
                id=DEMO_SCENE_T1_ID,
                name="Beirut Port Sentinel-2 Post-Event",
                captured_at=datetime(2020, 8, 5, 8, 30, 0, tzinfo=UTC),
                ingested_at=datetime(2020, 8, 6, 0, 0, 0, tzinfo=UTC),
                modality=SceneModality.OPTICAL,
                sensor_platform="Sentinel-2A",
                band_count=4,
                ground_sample_distance_meters=10.0,
                cloud_cover_percentage=0.0,
                coordinate_reference_system="EPSG:4326",
                footprint=footprint_geom,
                centroid=centroid_geom,
                file_size_bytes=rasters["optical_t1"].stat().st_size,
                raw_object_key=f"demo/{rasters['optical_t1'].name}",
                processing_state=SceneProcessingState.READY,
                cog_object_key=str(rasters["optical_t1"]),
            )
            session.add(scene_t1)

        # Scene SAR
        scene_sar = await session.get(Scene, DEMO_SCENE_SAR_ID)
        if not scene_sar:
            scene_sar = Scene(
                id=DEMO_SCENE_SAR_ID,
                name="Beirut Port Sentinel-1 SAR Verification",
                captured_at=datetime(2020, 8, 5, 15, 0, 0, tzinfo=UTC),
                ingested_at=datetime(2020, 8, 6, 0, 0, 0, tzinfo=UTC),
                modality=SceneModality.SAR,
                sensor_platform="Sentinel-1A",
                band_count=2,
                ground_sample_distance_meters=10.0,
                cloud_cover_percentage=None,  # CHECK constraint rule
                coordinate_reference_system="EPSG:4326",
                footprint=footprint_geom,
                centroid=centroid_geom,
                file_size_bytes=rasters["sar"].stat().st_size,
                raw_object_key=f"demo/{rasters['sar'].name}",
                processing_state=SceneProcessingState.READY,
                cog_object_key=str(rasters["sar"]),
            )
            session.add(scene_sar)
        await session.flush()

        # 3. Seed Canonical Investigation
        inv = await session.get(Investigation, DEMO_INVESTIGATION_ID)
        if not inv:
            inv = Investigation(
                id=DEMO_INVESTIGATION_ID,
                name="Beirut Port Disaster Assessment (SIH 2026 Canonical)",
                area_of_interest_name="Beirut Port, Lebanon",
                area_of_interest=footprint_geom,
                centroid=centroid_geom,
                status=InvestigationStatus.READY,
                mode=WorkspaceMode.TEMPORAL,
                seed_query="What changed between these two dates, and where did the change occur?",
                project_id=DEMO_PROJECT_ID,
                trace_id="trc_sih2026_demo_canonical_trace",
            )
            session.add(inv)

        await session.commit()

        # 4. Bind Scene Slots
        existing_slots = await session.execute(
            select(InvestigationScene).where(InvestigationScene.investigation_id == DEMO_INVESTIGATION_ID)
        )
        existing_roles = {s.role for s in existing_slots.scalars().all()}

        if SceneRole.T0 not in existing_roles:
            session.add(InvestigationScene(investigation_id=DEMO_INVESTIGATION_ID, scene_id=DEMO_SCENE_T0_ID, role=SceneRole.T0))
        if SceneRole.T1 not in existing_roles:
            session.add(InvestigationScene(investigation_id=DEMO_INVESTIGATION_ID, scene_id=DEMO_SCENE_T1_ID, role=SceneRole.T1))
        if SceneRole.SAR not in existing_roles:
            session.add(InvestigationScene(investigation_id=DEMO_INVESTIGATION_ID, scene_id=DEMO_SCENE_SAR_ID, role=SceneRole.SAR))

        await session.commit()

    return {
        "projectId": DEMO_PROJECT_ID,
        "investigationId": DEMO_INVESTIGATION_ID,
        "sceneT0Id": DEMO_SCENE_T0_ID,
        "sceneT1Id": DEMO_SCENE_T1_ID,
        "sceneSarId": DEMO_SCENE_SAR_ID,
        "status": "seeded",
    }
