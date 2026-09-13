"""S16 - says what the claims say, in words that contain only the numbers the claims carry.

what  : `generate_answer`, the S16 node of the index-query graph.
where : After S15 in `graphs/index_query.py`. Claims in, tokens out.
how   : The claims are phrased by the constrained generator (`services/answer/constrained.py`, 1.7): the
        VLM writes the prose with placeholders where the numbers go, the text is rejected if it carries any
        numeral of its own, and the placeholders are filled from the claims afterwards. With
        `settings.answer_generator = "template"`, or when the model is unavailable, the answer is the
        claims' own sentences. Either way the caveats the run recorded about its inputs follow: whether a
        cloud mask was applied, and how much ground the formula refused. Every number in the text is on a
        claim the frontend already holds (PDF §20: every numeric claim traceable to a computation); the
        trace step says which generator spoke.

        A run with no claims - a map-only question - describes the map from the distribution S15
        recorded, which is a description rather than an assertion and carries no claim for that reason.

        Streamed as word-sized tokens (`api-contract.md` §3.1). `confidence` is not decided here: S18
        aggregates it, and the completion event reads it from the checkpoint.
"""

from app.config import settings
from app.constants.spectral import SpectralIndex
from app.constants.stages import PipelineStage
from app.services.answer.constrained import admissible_reading, phrase_claims
from app.services.pipeline.node import describe_trace_step, pipeline_node
from app.services.pipeline.state import IndexQueryState
from app.services.pipeline.stream import emit_answer_token


@pipeline_node(PipelineStage.S16, detail="Composing the answer from the claims")
async def generate_answer(state: IndexQueryState) -> dict[str, object]:
    """S16. Sentences from the claims, nothing from anywhere else."""
    claims = state.get("claims", [])
    manager = None
    model = None
    if settings.answer_generator == "llm" and claims:
        from app.lib.llm.chat_model import build_chat_model

        model = build_chat_model()
    if (settings.answer_generator == "vlm" or (settings.answer_generator == "llm" and model is None)) and claims:
        from app.models.manager import get_manager

        manager = await get_manager()
    phrased = await phrase_claims(state["query"], claims, manager=manager, model=model)
    reading = state.get("reading_text")
    reading_spoken = bool(reading) and admissible_reading(reading, claims)
    text = _compose(state, phrased.text, reading if reading_spoken else None)
    tokens = text.split(" ")
    for token in tokens:
        emit_answer_token(state["run_id"], token)
    describe_trace_step(
        f"{len(claims)} claims spoken in {len(tokens)} tokens by the {phrased.source} generator"
        + (f" ({phrased.model_version})" if phrased.model_version else "")
        + (" - model phrasing rejected" if phrased.rejected_phrasing else "")
        + ("; the model's reading of the figure is included, labelled" if reading_spoken
           else "; the model's reading carried a number no claim carries and was left out" if reading else "")
    )
    return {"answer_tokens": tokens, "answer_source": phrased.source, "reading_spoken": reading_spoken}


def _compose(state: IndexQueryState, phrased_claims: str, reading: str | None) -> str:
    sentences: list[str] = []

    if phrased_claims:
        sentences.append(phrased_claims)
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

    # The S14 reading, last and labelled: the model's words about the picture, not a measurement.
    if reading:
        sentences.append(f"The vision-language model's reading of the figure (not a measurement): {reading.rstrip('.')}.")

    return " ".join(sentences)
