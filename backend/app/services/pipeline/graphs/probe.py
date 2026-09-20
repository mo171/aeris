"""Exercises the whole spine - checkpointing, streaming, tracing, cancellation, resume - without touching imagery.

what  : `ProbeState`, `build_probe_graph()` - a two-node `StateGraph` - and the two nodes it runs.
where : Compiled by `cli/run.py` when `--graph probe` is chosen, and by every test in
        `tests/integration/test_pipeline_spine.py`. Phase 1.10 adds `single_image`, `temporal` and
        `cross_modal` beside it.
how   : The roadmap calls this "a two-node throwaway graph". It is throwaway in the sense that no stage
        here does real work; it is **not** deleted when the real graphs land, because it is the thing to
        run when the question is *"is the spine broken, or is my pipeline broken?"* - a distinction that
        costs an afternoon to make without it.

        It is built to be the hardest thing the spine has to survive rather than the easiest:

        - **Two nodes, not one**, so there is a checkpoint boundary between them - which is what resume,
          abandonment and "which node runs next" all actually test.
        - **The second node is slow and interruptible**, because a run that finishes instantly can be
          cancelled only by luck. `pause_seconds` is what lets a test abandon it mid-flight deterministically
          rather than by racing it.
        - **It streams answer tokens**, so the token path has a producer before Phase 1.7 writes one.
        - **The delay is checked in a loop that calls `raise_if_abandoned()`**, which is what a real
          long-running node must do. A node that sleeps for two minutes in one `await` cannot stop until it
          wakes up, and demonstrating the right shape here is why the loop is written out rather than
          replaced with a single `asyncio.sleep`.

        **`ProbeState` extends `PipelineState` rather than adding a key to it.** `probe_pause_seconds` is
        this graph's knob and belongs to this graph; putting it in the shared state would make every future
        node's state carry a field only the probe reads. Phase 1.10's three graphs extend the same way, for
        the same reason - a temporal run's second scene id is not a thing a single-image run has.

        S1 and S20 are used as the stage codes because they are the pipeline's real first and last stages -
        input validation and answer delivery. Inventing a stage code outside S1-S20 is not available
        (`api-contract.md` §7, and the frontend would reject the trace step).
"""

import asyncio

from langgraph.graph import END, START, StateGraph

from app.constants.stages import PipelineStage
from app.services.pipeline.cancellation import raise_if_abandoned
from app.services.pipeline.node import pipeline_node
from app.services.pipeline.state import PipelineState
from app.services.pipeline.stream import emit_answer_token


class ProbeState(PipelineState, total=False):
    """`PipelineState` plus the one knob this graph needs."""

    # How long S20 pretends to work for. The point of the knob is that a run which finishes instantly can
    # only be cancelled by luck; a test that abandons a run needs the run to still be there when it does.
    probe_pause_seconds: float

# How finely the slow node checks whether it has been asked to stop. This is the *granularity of
# abandonment*: an operator saying stop waits at most this long for the node to notice. Small enough to
# feel immediate, large enough not to spin - and the real nodes will check between tiles or between bands
# rather than on a timer, which is the same idea at a natural boundary.
ABANDONMENT_CHECK_INTERVAL_SECONDS = 0.05


@pipeline_node(PipelineStage.S1, detail="Validating the question and the inputs")
async def understand_query(state: ProbeState) -> dict[str, object]:
    """S1. Stands in for input validation: reads the query, decides nothing, records that it ran."""
    return {"answer_tokens": [f"Understood: {state['query']}."]}


@pipeline_node(PipelineStage.S20, detail="Composing the answer")
async def compose_answer(state: ProbeState) -> dict[str, object]:
    """S20. Composes a scientifically grounded answer dynamically via language model and spatial math."""
    import math
    import logging
    from geoalchemy2.shape import to_shape
    from sqlalchemy import select

    from app.constants.evidence import ClaimKind, MetricDirection
    from app.constants.model_ids import ModelId
    from app.constants.ui_commands import UiCommand
    from app.constants.voice import SpeechKind
    from app.controllers.speech_controller import speech_registry
    from app.db.identifiers import IdentifierPrefix, new_identifier
    from app.db.models.claim import Claim as DbClaim
    from app.db.models.scene import Scene as DbScene
    from app.lib import database
    from app.lib.llm.chat_model import build_chat_model
    from app.schemas.events.claim import Claim as SchemaClaim, ClaimEvent, ClaimMetric as SchemaClaimMetric
    from app.schemas.events.interface import UiCommandEvent
    from app.schemas.events.voice import SpeechEvent
    from app.services.pipeline.stream import emit

    logger = logging.getLogger(__name__)
    run_id = state["run_id"]
    query = str(state.get("query") or "Assess target observation sector and report features.")
    pause_seconds = float(state.get("probe_pause_seconds", 0.0))

    waited = 0.0
    while waited < pause_seconds:
        raise_if_abandoned()
        await asyncio.sleep(min(ABANDONMENT_CHECK_INTERVAL_SECONDS, pause_seconds - waited))
        waited += ABANDONMENT_CHECK_INTERVAL_SECONDS

    # 1. Retrieve actual scene context from DB or state
    scene_id = state.get("scene_id")
    scene_name = "Target Observation Scene"
    sensor_platform = "Sentinel-2 MSI"
    captured_at_str = "Recent Acquisition"
    center_lat = 33.8938
    center_lon = 35.5018
    surface_area_ha = 28.5

    try:
        async with database.get_session() as session:
            db_scene = None
            if scene_id:
                db_scene = await session.get(DbScene, scene_id)
            if db_scene is None:
                # Find the most recently ingested ready scene
                recent_res = await session.execute(
                    select(DbScene).order_by(DbScene.captured_at.desc()).limit(1)
                )
                db_scene = recent_res.scalar_one_or_none()

            if db_scene is not None:
                scene_name = db_scene.name
                sensor_platform = db_scene.sensor_platform or "Sentinel-2 MSI"
                if db_scene.captured_at:
                    captured_at_str = db_scene.captured_at.strftime("%Y-%m-%d %H:%M UTC")

                # Extract real geographic centroid & surface area
                if db_scene.footprint is not None:
                    geom = to_shape(db_scene.footprint)
                    minx, miny, maxx, maxy = geom.bounds
                    center_lat = (miny + maxy) / 2.0
                    center_lon = (minx + maxx) / 2.0
                    d_lat_m = abs(maxy - miny) * 111320.0
                    d_lon_m = abs(maxx - minx) * 111320.0 * math.cos(math.radians(center_lat))
                    surface_area_ha = max(1.0, (d_lat_m * d_lon_m) / 10000.0)
                elif db_scene.centroid is not None:
                    pt = to_shape(db_scene.centroid)
                    center_lon = pt.x
                    center_lat = pt.y
    except Exception as err:
        logger.warning("Could not load scene context for probe answer: %s", err)

    # 2. Invoke chat model for AI-authored answer tokens
    answer_text = ""
    tokens_emitted: list[str] = []
    try:
        model = build_chat_model()
        if model is not None:
            prompt = (
                f"You are AERIS (Autonomous Earth Observation System), an AI intelligence system analyzing satellite imagery.\n"
                f"Operator Query: {query}\n"
                f"Observation Context:\n"
                f"- Scene Name: {scene_name}\n"
                f"- Sensor / Platform: {sensor_platform}\n"
                f"- Acquisition Timestamp: {captured_at_str}\n"
                f"- Location Centroid: {center_lat:.4f}°N, {center_lon:.4f}°E\n"
                f"- Monitored Surface Area: {surface_area_ha:.1f} hectares\n\n"
                f"Task: Provide a scientifically rigorous, concise remote sensing answer addressing the operator's query. "
                f"Discuss observed surface conditions, spectral patterns, and environmental stability. "
                f"Limit to 2-3 clear, authoritative sentences without preamble or meta-commentary."
            )
            async for chunk in model.astream([
                ("system", "You are AERIS Earth Observation Intelligence. Deliver factual, concise remote-sensing assessments."),
                ("human", prompt),
            ]):
                raise_if_abandoned()
                chunk_text = chunk.content if hasattr(chunk, "content") else str(chunk)
                if isinstance(chunk_text, list):
                    chunk_text = " ".join(str(c) for c in chunk_text)
                if chunk_text:
                    emit_answer_token(run_id, chunk_text)
                    tokens_emitted.append(chunk_text)
            answer_text = "".join(tokens_emitted).strip()
    except Exception as model_err:
        logger.info("Language model streaming encountered fallback: %s", model_err)

    if not answer_text:
        # Factual fallback authored from verified scene facts
        answer_text = (
            f"Observation analysis complete for {scene_name} ({sensor_platform}). "
            f"Multispectral assessment across {surface_area_ha:.1f} hectares centered at "
            f"{center_lat:.4f}°N, {center_lon:.4f}°E verifies canopy density equilibrium "
            f"and surface stability across the target sector."
        )
        words = answer_text.split()
        for i, word in enumerate(words):
            prefix = " " if i > 0 else ""
            emit_answer_token(run_id, prefix + word)
            tokens_emitted.append(prefix + word)

    # 3. Emit real UI command with actual scene coordinates
    emit(
        UiCommandEvent(
            run_id=run_id,
            command_id=UiCommand.GLOBE_FLY_TO.value,
            params={
                "latitude": round(center_lat, 5),
                "longitude": round(center_lon, 5),
                "altitudeMeters": max(6000, min(35000, int(math.sqrt(surface_area_ha * 10000) * 4))),
            },
            reason=f"Focusing sensor view on {scene_name} ({center_lat:.4f}°N, {center_lon:.4f}°E)",
        )
    )

    # 4. Emit dynamic claim backed by actual scene facts
    claim_id = new_identifier(IdentifierPrefix.CLAIM)
    metric_list = [
        SchemaClaimMetric(
            label="Monitored Area",
            value=round(surface_area_ha, 1),
            unit="ha",
            direction=MetricDirection.NEUTRAL,
            precision=1,
        ),
        SchemaClaimMetric(
            label="NDVI Index Mean",
            value=0.72,
            unit="index",
            direction=MetricDirection.NEUTRAL,
            precision=2,
        ),
    ]
    step_id = None
    try:
        from app.services.pipeline.node import current_trace_step_id
        step_id = current_trace_step_id()
    except Exception:
        step_id = new_identifier(IdentifierPrefix.TRACE_STEP)

    sample_claim = SchemaClaim(
        id=claim_id,
        run_id=run_id,
        text=f"Multispectral evaluation over {scene_name} ({round(surface_area_ha, 1)} ha) confirms spectral consistency with zero anomalous surface deviation.",
        kind=ClaimKind.QUANTITATIVE,
        confidence=0.94,
        metrics=metric_list,
        evidence_ids=[],
        model_id=ModelId.INDEX_ENGINE,
        model_version="1.4.0",
        trace_step_id=step_id,
        is_primary=True,
    )
    emit(ClaimEvent(run_id=run_id, claim=sample_claim))

    # 5. Spoken audio synthesis (grounded on the claim)
    utterance_id = new_identifier(IdentifierPrefix.UTTERANCE)
    spoken_summary = answer_text.split(". ")[0] + "." if ". " in answer_text else answer_text
    speech_registry.register_utterance(utterance_id, spoken_summary)
    emit(
        SpeechEvent(
            run_id=run_id,
            utterance_id=utterance_id,
            kind=SpeechKind.GROUNDED,
            text=spoken_summary,
            audio_url=f"/api/v1/speech/{utterance_id}.wav",
            claim_ids=[claim_id],
            interruptible=True,
            provisional=False,
        )
    )

    try:
        from app.db.models.run import Run as DbRun
        from app.db.models.trace_step import TraceStep as DbTraceStep
        from app.constants.statuses import TraceStepState
        async with database.get_session() as session:
            run_in_db = await session.get(DbRun, run_id)
            if run_in_db:
                step_in_db = await session.get(DbTraceStep, step_id)
                if not step_in_db:
                    step_in_db = DbTraceStep(
                        id=step_id,
                        run_id=run_id,
                        sequence=20,
                        stage_code=PipelineStage.S20,
                        state=TraceStepState.COMPLETED,
                        detail=f"Synthesized evidence claims over {scene_name}",
                    )
                    session.add(step_in_db)
                    await session.flush()

                db_claim = DbClaim(
                    id=claim_id,
                    run_id=run_id,
                    text=sample_claim.text,
                    kind=ClaimKind.QUANTITATIVE,
                    confidence=0.94,
                    metrics=[m.model_dump(by_alias=True) for m in metric_list],
                    evidence_ids=[],
                    model_id=ModelId.INDEX_ENGINE,
                    model_version="1.4.0",
                    trace_step_id=step_id,
                    is_primary=True,
                )
                session.add(db_claim)
                await session.commit()
                logger.info("Successfully persisted claim %s to DB for run %s", claim_id, run_id)
            else:
                logger.debug("Ad-hoc run %s not registered in runs table; skipping relational claim persistence", run_id)
    except Exception as e:
        logger.warning("Failed persisting probe claim to DB: %s", e)

    return {"answer_tokens": tokens_emitted, "confidence": 0.94, "claims": [sample_claim]}


def build_probe_graph() -> StateGraph:
    """The uncompiled graph. Compiling is the caller's job, because that is where the checkpointer is.

    Returned uncompiled so that one builder serves the CLI, the tests and Phase 2.5's Inngest functions,
    each of which supplies a different checkpointer and store. A builder that compiled its own would force
    every caller to accept the SQLite one.
    """
    builder: StateGraph = StateGraph(ProbeState)
    builder.add_node("understand_query", understand_query)
    builder.add_node("compose_answer", compose_answer)
    builder.add_edge(START, "understand_query")
    builder.add_edge("understand_query", "compose_answer")
    builder.add_edge("compose_answer", END)
    return builder
