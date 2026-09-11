"""S16 - says what the claims say, in words that contain only the numbers the claims carry.

what  : `generate_answer`, the S16 node of the index-query graph.
where : After S15 in `graphs/index_query.py`. Phase 1.7 replaces the sentence assembly with the
        constrained generator - language from the structured result, numbers injected, never generated -
        and this node is the shape that generator has to keep: claims in, tokens out.
how   : No model, no inference, no confidence. The answer is the claims' own text, primary first, then
        the caveats the run recorded about its inputs: whether a cloud mask was applied, and how much of
        the ground the formula refused. Nothing in the text comes from anywhere but the state, and every
        number in it is on a claim the frontend already holds (PDF §20: every numeric claim traceable to
        a computation).

        A run with no claims - a map-only question - describes the map from the distribution S15
        recorded, which is a description rather than an assertion and carries no claim for that reason.

        Streamed as word-sized tokens (`api-contract.md` §3.1). `confidence` is not decided here: S18
        aggregates it, and the completion event reads it from the checkpoint.
"""

from app.constants.spectral import SpectralIndex
from app.constants.stages import PipelineStage
from app.services.pipeline.node import describe_trace_step, pipeline_node
from app.services.pipeline.state import IndexQueryState
from app.services.pipeline.stream import emit_answer_token


@pipeline_node(PipelineStage.S16, detail="Composing the answer from the claims")
async def generate_answer(state: IndexQueryState) -> dict[str, object]:
    """S16. Sentences from the claims, nothing from anywhere else."""
    text = _compose(state)
    tokens = text.split(" ")
    for token in tokens:
        emit_answer_token(state["run_id"], token)
    describe_trace_step(f"{len(state.get('claims', []))} claims spoken in {len(tokens)} tokens")
    return {"answer_tokens": tokens}


def _compose(state: IndexQueryState) -> str:
    claims = state.get("claims", [])
    sentences: list[str] = []

    if claims:
        primary = [claim["text"] for claim in claims if claim["isPrimary"]]
        supporting = [claim["text"] for claim in claims if not claim["isPrimary"]]
        sentences.extend(primary + supporting)
    else:
        index = SpectralIndex(state["index"]).value.upper()
        fractions = state.get("band_fractions", {})
        sentences.append(f"{index} was computed over {state['scene_id']}.")
        if fractions:
            leading = max(fractions, key=fractions.__getitem__)
            sentences.append(f"Of the observed ground, {fractions[leading]:.1%} reads as {leading.lower()}.")

    obscured = state.get("obscured_fraction")
    if state.get("index_mask_applied") and obscured is not None:
        sentences.append(f"Cloud and shadow covering {obscured:.1%} of the scene were masked before the arithmetic.")
    else:
        sentences.append("No cloud mask was available for this scene, so values over cloud are included.")

    unphysical = state.get("index_unphysical_fraction") or 0.0
    if unphysical > 0.0:
        sentences.append(f"{unphysical:.1%} of observed pixels were refused by the formula as unphysical.")

    return " ".join(sentences)
