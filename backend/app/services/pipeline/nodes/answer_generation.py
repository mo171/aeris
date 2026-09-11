"""S16 - says what was measured, in words that contain only the numbers S15 produced.

what  : `generate_answer`, the S16 node of the index-query graph.
where : Last node of `graphs/index_query.py`. Phase 1.7 replaces the sentence templates with the
        constrained generator - language from the structured result, numbers injected, never generated -
        and this node is the shape that generator has to keep.
how   : No model, no inference, no confidence. Every quantity in the text is read from the state S15
        wrote, formatted for a reader, and nothing else; the rounding is presentation and the underlying
        value in the state is what a claim will carry (`api-contract.md` §5 applies the same rule to
        speech). `confidence` is `None` because a deterministic measurement has no probability to report
        and `0.0` would claim it has none (§1 rule 2).

        Streamed as word-sized tokens (`api-contract.md` §3.1), which is how the terminal and, later, the
        frontend both draw an answer arriving.
"""

from app.constants.spectral import SpectralIndex
from app.constants.stages import PipelineStage
from app.services.pipeline.node import pipeline_node
from app.services.pipeline.state import IndexQueryState
from app.services.pipeline.stream import emit_answer_token


@pipeline_node(PipelineStage.S16, detail="Composing the answer from the measurement")
async def generate_answer(state: IndexQueryState) -> dict[str, object]:
    """S16. Sentences from the state, nothing from anywhere else."""
    text = _compose(state)
    tokens = text.split(" ")
    for token in tokens:
        emit_answer_token(state["run_id"], token)
    return {"answer_tokens": tokens, "confidence": None}


def _compose(state: IndexQueryState) -> str:
    index = SpectralIndex(state["index"]).value.upper()
    scene = state["scene_id"]
    sentences: list[str] = []

    measurement = state.get("measurement")
    if measurement is None:
        fractions = state.get("band_fractions", {})
        leading = max(fractions, key=fractions.__getitem__) if fractions else None
        sentences.append(f"{index} was computed over {scene}.")
        if leading is not None:
            sentences.append(
                f"Of the observed ground, {fractions[leading]:.1%} reads as {leading.lower()}."
            )
    else:
        lower, upper = state["target_lower"], state["target_upper"]
        sentences.append(
            f"{state['target_label']} ({index} {lower:.2f} to {upper:.2f}) covers "
            f"{measurement['areaHectares']:,.1f} hectares of {scene}: "
            f"{measurement['coverageFraction']:.1%} of the {measurement['observedHectares']:,.1f} hectares "
            f"observed, in {measurement['regionCount']:,} regions."
        )

    obscured = state.get("obscured_fraction")
    if state.get("index_mask_applied") and obscured is not None:
        sentences.append(f"Cloud and shadow covering {obscured:.1%} of the scene were masked before the arithmetic.")
    else:
        sentences.append("No cloud mask was available for this scene, so values over cloud are included.")

    unphysical = state.get("index_unphysical_fraction") or 0.0
    if unphysical > 0.0:
        sentences.append(f"{unphysical:.1%} of observed pixels were refused by the formula as unphysical.")

    return " ".join(sentences)
