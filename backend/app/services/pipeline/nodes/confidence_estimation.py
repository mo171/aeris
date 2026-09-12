"""S18 - decides the one confidence the run reports, from what each stage stated, by a rule that is named.

what  : `estimate_confidence`, the S18 node of the index-query graph.
where : After S16 in `graphs/index_query.py`. Writes `confidence`, the state key `run_handle.py` reads
        into `run-complete`, and names the rule for S19 to record.
how   : Reads the `ModelRecord`s the earlier stages left in the state - which engine ran, at which
        version, and the confidence it stated or declined to - and hands them to
        `evidence/math/confidence_aggregation.py`. The rule is `minimum-of-stated`: the run is as
        confident as its least confident stage that said anything, and `None` when none did
        (`architecture-context.md` §8 rule 10; PDF §21.2, "aggregation rule recorded, not just shown").

        In 1.4 and 1.5 every engine is deterministic and declines, so the run's confidence is `None` and
        the frontend renders that as an explicit statement rather than a score. This node exists now so
        that the first model that states one (1.6) changes the inputs and not the graph.
"""

import asyncio

from app.constants.evidence import CONFIDENCE_AGGREGATION_RULE
from app.constants.stages import PipelineStage
from app.services.evidence.math.confidence_aggregation import aggregate_confidence
from app.services.pipeline.node import describe_trace_step, pipeline_node
from app.services.pipeline.state import IndexQueryState


@pipeline_node(PipelineStage.S18, detail="Aggregating the confidence the stages stated")
async def estimate_confidence(state: IndexQueryState) -> dict[str, object]:
    """S18. The weakest stated stage confidence, or `None` when nothing was stated."""
    records = state.get("stage_models", [])
    stated = [record.get("confidence") for record in records]
    confidence = await asyncio.to_thread(aggregate_confidence, stated)

    declined = sum(1 for value in stated if value is None)
    describe_trace_step(
        f"{CONFIDENCE_AGGREGATION_RULE} over {len(records)} stages: "
        + (f"{confidence:.2f}" if confidence is not None else "none stated")
        + (f", {declined} declined" if declined else "")
    )
    return {"confidence": confidence, "confidence_aggregation_rule": CONFIDENCE_AGGREGATION_RULE}
