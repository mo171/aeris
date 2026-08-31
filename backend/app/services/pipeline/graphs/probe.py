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

    tokens = ["The", "spine", "is", "working."]
    for token in tokens:
        emit_answer_token(run_id, token)

    # `None` rather than a number, on purpose. This node ran no specialist model, so it has no confidence
    # to report - and `0.0` would claim it has none, which is a different statement (api-contract.md §1
    # rule 2). The probe graph refusing to invent a confidence is the same rule the real pipeline runs on.
    return {"answer_tokens": tokens, "confidence": None}


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
