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
    """S20. Stands in for answer delivery, and is the node a test abandons.

    The pause is a stand-in for model inference, and it is spent in a loop rather than in one `sleep` for
    the reason a real node must do the same: a stage that is not checkable partway through cannot be
    stopped partway through, so an operator's "stop" would wait for the whole inference to finish.
    """
    run_id = state["run_id"]
    pause_seconds = float(state.get("probe_pause_seconds", 0.0))

    waited = 0.0
    while waited < pause_seconds:
        raise_if_abandoned()
        await asyncio.sleep(min(ABANDONMENT_CHECK_INTERVAL_SECONDS, pause_seconds - waited))
        waited += ABANDONMENT_CHECK_INTERVAL_SECONDS

    tokens = ["The", "analysis", "pipeline", "is", "operational.", "Ground", "features", "and", "claims", "verified."]
    for i, token in enumerate(tokens):
        prefix = " " if i > 0 else ""
        emit_answer_token(run_id, prefix + token)

    # Phase 2.7: Emit ui-command and speech events over the live stream
    from app.constants.ui_commands import UiCommand
    from app.constants.voice import SpeechKind
    from app.controllers.speech_controller import speech_registry
    from app.db.identifiers import IdentifierPrefix, new_identifier
    from app.schemas.events.interface import UiCommandEvent
    from app.schemas.events.voice import SpeechEvent
    from app.services.pipeline.stream import emit

    emit(
        UiCommandEvent(
            run_id=run_id,
            command_id=UiCommand.GLOBE_FLY_TO.value,
            params={"latitude": 33.8938, "longitude": 35.5018, "altitudeMeters": 15000},
            reason="Positioning camera over target area of interest",
        )
    )

    utterance_id = new_identifier(IdentifierPrefix.UTTERANCE)
    speech_text = "The analysis spine is verified and operational."
    speech_registry.register_utterance(utterance_id, speech_text)
    emit(
        SpeechEvent(
            run_id=run_id,
            utterance_id=utterance_id,
            kind=SpeechKind.PROGRESS,
            text=speech_text,
            audio_url=f"/api/v1/speech/{utterance_id}.opus",
            claim_ids=[],
            interruptible=True,
            provisional=False,
        )
    )

    from app.constants.evidence import ClaimKind, MetricDirection
    from app.constants.model_ids import ModelId
    from app.schemas.events.claim import Claim as SchemaClaim, ClaimEvent, ClaimMetric as SchemaClaimMetric
    from app.db.models.claim import Claim as DbClaim
    from app.lib import database

    claim_id = new_identifier(IdentifierPrefix.CLAIM)
    metric_list = [
        SchemaClaimMetric(
            label="NDVI Vegetation Mean",
            value=0.74,
            unit="index",
            direction=MetricDirection.NEUTRAL,
            precision=2,
        ),
        SchemaClaimMetric(
            label="Surface Area",
            value=28.5,
            unit="ha",
            direction=MetricDirection.INCREASE,
            precision=1,
        ),
    ]
    sample_claim = SchemaClaim(
        id=claim_id,
        run_id=run_id,
        text="Spectral index analysis confirms 28.5 ha vegetation health stability with zero surface anomaly.",
        kind=ClaimKind.QUANTITATIVE,
        confidence=0.94,
        metrics=metric_list,
        evidence_ids=[],
        model_id=ModelId.INDEX_ENGINE,
        model_version="1.4.0",
        trace_step_id="stp_01M2YN64YPE1YW49NHZK1051DB",
        is_primary=True,
    )
    emit(ClaimEvent(run_id=run_id, claim=sample_claim))

    try:
        async with database.get_session() as session:
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
                trace_step_id="stp_01M2YN64YPE1YW49NHZK1051DB",
                is_primary=True,
            )
            session.add(db_claim)
            await session.commit()
    except Exception as e:
        logger.warning("Failed persisting probe claim to DB: %s", e)

    return {"answer_tokens": tokens, "confidence": 0.94, "claims": [sample_claim]}


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
