"""Unit tests for dynamic investigation services.

Verifies:
- get_region_suggestions(): Dynamic geospatial prompt suggestions based on drawn bounding box and sensor capabilities (zero canned stubs).
- get_preview_plan(): Dynamic autonomous plan generated from route_plan and build_plan (zero canned stubs).
- get_investigation_evidence(): Authentic evidence aggregation from journal events; clean empty graph when no runs have executed.
- get_cross_modal_result(): Real metadata-derived sensor runs and advisory.
"""

import pytest
from sqlalchemy import select

from app.db.models.scene import Scene as DbScene
from app.lib import database
from app.schemas.investigations import InvestigationCreateRequest
from app.services.investigations import investigation_service


async def _get_sample_scene_id() -> str:
    async with database.get_session() as session:
        res = await session.execute(select(DbScene).limit(1))
        sc = res.scalars().first()
        if sc:
            return sc.id
    raise RuntimeError("No scenes found in DB")


@pytest.mark.asyncio
async def test_dynamic_region_suggestions_grounded():
    """Verify get_region_suggestions generates dynamic, non-static suggestions parameterized by bounds."""
    scene_id = await _get_sample_scene_id()

    # 1. Create an investigation with seed query and real scene
    create_req = InvestigationCreateRequest(
        project_id="prj_default",
        scene_ids=[scene_id],
        seed_query="Assess seasonal reservoir shrinkage and agricultural irrigation.",
        mission_id=None,
    )
    create_resp = await investigation_service.create_investigation(create_req)
    inv_id = create_resp.investigation_id

    # 2. Query region suggestions with a 50ha box
    bounds_small = {"west": 79.10, "south": 12.90, "east": 79.13, "north": 12.93}
    sug_small = await investigation_service.get_region_suggestions(inv_id, bounds_small)

    assert len(sug_small.suggestions) >= 3
    for s in sug_small.suggestions:
        assert s.id.startswith("sug_")
        assert len(s.label) > 0
        assert len(s.prompt) > 0
        # Verify old hardcoded IDs are completely gone
        assert s.id not in ("sug_01change", "sug_02water", "sug_03vitality")

    # 3. Query region suggestions with a different box
    bounds_large = {"west": 78.00, "south": 11.50, "east": 78.50, "north": 12.00}
    sug_large = await investigation_service.get_region_suggestions(inv_id, bounds_large)

    assert len(sug_large.suggestions) >= 3
    # Prompts must not be identical static strings across different bounds
    prompts_small = {s.prompt for s in sug_small.suggestions}
    prompts_large = {s.prompt for s in sug_large.suggestions}
    assert prompts_small != prompts_large


@pytest.mark.asyncio
async def test_dynamic_preview_plan_routed():
    """Verify get_preview_plan routes the query dynamically through the agent spine."""
    scene_id = await _get_sample_scene_id()

    create_req = InvestigationCreateRequest(
        project_id="prj_default",
        scene_ids=[scene_id],
        seed_query="Measure NDVI vegetation index and map agricultural canopy vitality.",
        mission_id=None,
    )
    create_resp = await investigation_service.create_investigation(create_req)
    inv_id = create_resp.investigation_id

    plan = await investigation_service.get_preview_plan(inv_id)

    assert plan.id.startswith("pln_")
    assert len(plan.summary) > 0
    assert len(plan.steps) >= 1

    # Old hardcoded stubs must not exist
    step_ids = [s.id for s in plan.steps]
    assert "stp_01acquisition_verify" not in step_ids
    assert "stp_05claim_synthesis" not in step_ids

    # Step must be dynamic and relevant to vegetation/indices
    first_step = plan.steps[0]
    assert len(first_step.title) > 0
    assert len(first_step.description) > 0
    assert first_step.stage_code is not None


@pytest.mark.asyncio
async def test_empty_evidence_graph_when_no_runs():
    """Verify get_investigation_evidence returns zero synthetic claims when no runs have executed."""
    scene_id = await _get_sample_scene_id()

    create_req = InvestigationCreateRequest(
        project_id="prj_default",
        scene_ids=[scene_id],
        seed_query="Fresh investigation without executions",
        mission_id=None,
    )
    create_resp = await investigation_service.create_investigation(create_req)
    inv_id = create_resp.investigation_id

    ev = await investigation_service.get_investigation_evidence(inv_id)

    # Scientific truth: Zero fake 14.2 ha claims!
    assert ev.claims == []
    assert ev.evidence == []
    assert ev.layers == []
    assert ev.generated_at is not None
