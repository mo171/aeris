"""Synthetic and real-boundary integration tests for Phase 1.11 late fusion."""

import asyncio
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.constants.intents import Intent
from app.constants.pipeline import GraphName
from app.constants.raster import ProcessingLevel
from app.constants.statuses import RunStatus
from app.services.pipeline.runner import AnalysisRequest, run_analysis

pytestmark = pytest.mark.integration

CRS = "EPSG:32643"
TRANSFORM = from_origin(268410.0, 2113350.0, 10.0, 10.0)
ROWS = COLUMNS = 128


def _write(path: Path, values: np.ndarray, *, transform=TRANSFORM, nodata=None) -> None:
    with rasterio.open(
        path, "w", driver="GTiff", height=values.shape[0], width=values.shape[1], count=1,
        dtype=values.dtype, crs=CRS, transform=transform, nodata=nodata,
    ) as target:
        target.write(values, 1)


def _dn(reflectance: np.ndarray) -> np.ndarray:
    counts = np.round(reflectance * 10_000 + 1_000).astype(np.uint16)
    rows, columns = np.indices(counts.shape)
    return counts + ((rows + columns) % 2).astype(np.uint16)


@pytest.fixture
def cross_modal_pair(tmp_path: Path) -> tuple[Path, Path]:
    optical = tmp_path / "S2B_MSIL2A_20260312T053639_R005_T43QBB_SYNTHETIC"
    radar = tmp_path / "S1A_IW_GRDH_1SDV_20260315T010312_SYNTHETIC"
    optical.mkdir()
    radar.mkdir()

    green = np.full((ROWS, COLUMNS), 0.18, np.float32)
    nir = np.full((ROWS, COLUMNS), 0.22, np.float32)
    swir = np.full((ROWS, COLUMNS), 0.20, np.float32)
    # Every asserted ledger class occupies at least 5 ha at this 10 m grid.
    green[8:48, 8:48], nir[8:48, 8:48], swir[8:48, 8:48] = 0.40, 0.20, 0.08
    green[72:112, 8:48], nir[72:112, 8:48], swir[72:112, 8:48] = 0.10, 0.20, 0.40
    # A material water / built-up disagreement must block a fused headline, rather than being hidden
    # behind the two branch summaries spoken by S16.
    green[72:112, 72:112], nir[72:112, 72:112], swir[72:112, 72:112] = 0.40, 0.20, 0.08
    for name, values in (
        ("B02", np.full((ROWS, COLUMNS), 0.08, np.float32)),
        ("B03", green), ("B04", np.full((ROWS, COLUMNS), 0.12, np.float32)), ("B08", nir), ("B11", swir),
    ):
        _write(optical / f"{name}.tif", _dn(values), nodata=0)
    _write(optical / "SCL.tif", np.full((ROWS, COLUMNS), 4, np.uint8))

    vv_db = np.full((ROWS, COLUMNS), -12.0, np.float32)
    vh_db = np.full((ROWS, COLUMNS), -19.0, np.float32)
    # Partial overlap plus a radar-only strip for both physical classes.
    vv_db[8:48, 8:32], vh_db[8:48, 8:32] = -20.0, -26.0
    vv_db[72:112, 8:32], vh_db[72:112, 8:32] = -6.0, -12.0
    vv_db[72:112, 72:96], vh_db[72:112, 72:96] = -6.0, -12.0
    _write(radar / "vv.tif", np.power(10.0, vv_db / 10.0).astype(np.float32))
    _write(radar / "vh.tif", np.power(10.0, vh_db / 10.0).astype(np.float32))
    return optical, radar


@pytest.fixture(autouse=True)
def flat_test_dem(monkeypatch: pytest.MonkeyPatch) -> None:
    async def elevation(path: Path) -> np.ndarray:
        with rasterio.open(path) as source:
            return np.zeros((source.height, source.width), dtype=np.float32)

    monkeypatch.setattr("app.services.pipeline.nodes.cross_modal.elevation_on_grid", elevation)


async def test_cross_modal_graph_runs_both_sensors_and_persists_a_real_ledger(
    cross_modal_pair: tuple[Path, Path], isolated_pipeline_paths: Path,
) -> None:
    optical, radar = cross_modal_pair
    request = AnalysisRequest(
        graph=GraphName.CROSS_MODAL,
        query="Use optical and SAR images together to identify built-up and water-covered regions",
        intent=Intent.CROSS_MODAL,
        scene=optical,
        reference=radar,
        declared_level=ProcessingLevel.L2A,
        declared_registered=True,
        reference_is_sar=True,
    )

    outcome = await run_analysis(request)

    assert outcome.status is RunStatus.COMPLETE, outcome.error
    result = outcome.values["cross_modal_result"]
    assert result["optical"]["sensor"] == "optical"
    assert result["radar"]["sensor"] == "radar"
    states = {row["state"] for row in result["verdict"]["rows"]}
    assert "corroborated" in states and ({"optical-only", "radar-only"} & states)
    assert all(row["reason"] for row in result["verdict"]["rows"])
    assert result["verdict"]["blockedByConflict"]
    primary_claims = [claim for claim in outcome.values["claims"] if claim["isPrimary"]]
    assert len(primary_claims) == 1
    assert "cannot produce a fused conclusion" in primary_claims[0]["text"]
    assert primary_claims[0]["confidence"] is None
    assert "cannot produce a fused conclusion" in " ".join(outcome.values["answer_tokens"])
    # The radar has two built-up source regions; the corroborated component may reference only the one
    # it intersects, never the class-wide feature list.
    corroborated_built_up = next(
        row for row in result["verdict"]["rows"]
        if row["state"] == "corroborated" and row["label"].startswith("Built-up")
    )
    assert len(corroborated_built_up["radarFeatureIds"]) == 1
    assert len(outcome.values["layers"]) >= 8
    assert len(outcome.figures) == 5, "four branch diagnostics plus one categorical fusion overlay"
    assert await asyncio.to_thread(Path(outcome.values["cross_modal_result_path"]).exists)
    assert await asyncio.to_thread(Path(outcome.values["provenance_path"]).exists)
    assert await asyncio.to_thread(Path(outcome.values["evidence_graph_path"]).exists)


async def test_cross_modal_request_normalises_input_order(
    cross_modal_pair: tuple[Path, Path], isolated_pipeline_paths: Path,
) -> None:
    optical, radar = cross_modal_pair
    request = AnalysisRequest(
        graph=GraphName.CROSS_MODAL,
        query="Use optical and SAR together",
        intent=Intent.CROSS_MODAL,
        scene=radar,
        reference=optical,
        declared_level=ProcessingLevel.L2A,
        declared_registered=True,
        is_sar=True,
    )

    outcome = await run_analysis(request)

    assert outcome.status is RunStatus.COMPLETE, outcome.error
    assert outcome.values["optical_scene_id"].startswith("S2B_")
    assert outcome.values["radar_scene_id"].startswith("S1A_")
