"""S16 - says what the claims say, in words that contain only the numbers the claims carry.

what  : `generate_answer`, the S16 node of every graph.
where : After S14 in the single-image and temporal graphs. Claims in, tokens out.
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

        The caveats are the run's, not a template's (1.10): the cloud sentence is spoken only when S7 ran
        (an optical scene directory), the formula's refusals only when an index was computed, and a
        perception answer's reading is the claim itself rather than a sentence appended after it.

        Streamed as word-sized tokens (`api-contract.md` §3.1). `confidence` is not decided here: S18
        aggregates it, and the completion event reads it from the checkpoint.
"""

from app.config import settings
from app.constants.intents import Intent
from app.constants.spectral import SpectralIndex
from app.constants.stages import PipelineStage
from app.services.answer.constrained import admissible_reading, phrase_claims
from app.services.pipeline.node import describe_trace_step, pipeline_node
from app.services.pipeline.state import AnalysisState
from app.services.pipeline.stream import emit_answer_token

# The intents whose S14 is the specialist: the reading is the claim, not a sentence after the claims.
PERCEPTION_INTENTS = frozenset({Intent.SCENE_VQA, Intent.CHANGE_VQA})


@pipeline_node(PipelineStage.S16, detail="Composing the answer from the claims")
async def generate_answer(state: AnalysisState) -> dict[str, object]:
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
    perception = Intent(state["intent"]) in PERCEPTION_INTENTS
    # A perception answer's reading *is* its claim; speaking it again after the claim would say it twice.
    reading_spoken = bool(reading) and (perception or admissible_reading(reading, claims))
    text = _compose(state, phrased.text, reading if reading_spoken and not perception else None)
    tokens = text.split(" ")
    for token in tokens:
        emit_answer_token(state["run_id"], token)
    # Phase 2.7: Emit ui-command and speech events
    from app.constants.ui_commands import UiCommand
    from app.constants.voice import SpeechKind
    from app.controllers.speech_controller import speech_registry
    from app.db.identifiers import IdentifierPrefix, new_identifier
    from app.schemas.events.interface import UiCommandEvent
    from app.schemas.events.voice import SpeechEvent
    from app.services.pipeline.stream import emit

    primary_claim = next((c for c in claims if c.get("is_primary") or c.get("isPrimary")), None) or (claims[0] if claims else None)
    if primary_claim and primary_claim.get("id"):
        primary_id = primary_claim["id"]
        emit(UiCommandEvent(
            run_id=state["run_id"],
            command_id=UiCommand.INVESTIGATION_SPOTLIGHT_CLAIM.value,
            params={"claimId": primary_id},
            reason="Spotlighting primary finding",
        ))
        first_ev = next(iter(primary_claim.get("evidence_ids") or primary_claim.get("evidenceIds") or []), None)
        if first_ev:
            emit(UiCommandEvent(
                run_id=state["run_id"],
                command_id=UiCommand.INVESTIGATION_FOCUS_EVIDENCE.value,
                params={"evidenceId": first_ev},
                reason="Focusing evidence area",
            ))

    if claims:
        claim_ids = [c["id"] for c in claims if c.get("id")]
        if claim_ids:
            utterance_id = new_identifier(IdentifierPrefix.UTTERANCE)
            speech_text = phrased.text or text
            speech_registry.register_utterance(utterance_id, speech_text)
            emit(SpeechEvent(
                run_id=state["run_id"],
                utterance_id=utterance_id,
                kind=SpeechKind.GROUNDED,
                text=speech_text,
                audio_url=f"/api/v1/speech/{utterance_id}.opus",
                claim_ids=claim_ids,
                interruptible=True,
                provisional=False,
            ))

    describe_trace_step(
        f"{len(claims)} claims spoken in {len(tokens)} tokens by the {phrased.source} generator"
        + (f" ({phrased.model_version})" if phrased.model_version else "")
        + (" - model phrasing rejected" if phrased.rejected_phrasing else "")
        + ("; the model's reading of the figure is included, labelled" if reading_spoken
           else "; the model's reading carried a number no claim carries and was left out" if reading else "")
    )
    return {"answer_tokens": tokens, "answer_source": phrased.source, "reading_spoken": reading_spoken}


def _compose(state: AnalysisState, phrased_claims: str, reading: str | None) -> str:
    sentences: list[str] = []

    if phrased_claims:
        sentences.append(phrased_claims)
    elif state.get("index"):
        index = SpectralIndex(state["index"]).value.upper()
        fractions = state.get("band_fractions", {})
        sentences.append(f"{index} was computed over {state['scene_id']}.")
        if fractions:
            leading = max(fractions, key=fractions.__getitem__)
            sentences.append(f"Of the observed ground, {fractions[leading]:.1%} reads as {leading.lower()}.")
    else:
        sentences.append(f"The run over {state['scene_id']} produced no finding to report.")

    # S7 ran when the key is present at all (a path, or None for a scene with no classification layer).
    if "cloud_mask_path" in state:
        obscured = state.get("obscured_fraction")
        masked = state.get("index_mask_applied") if state.get("index") else state.get("cloud_mask_path") is not None
        before = "the arithmetic" if state.get("index") else "the analysis"
        if masked and obscured is not None and _claims_carry(state, "Obscured by cloud and shadow"):
            sentences.append(f"Cloud and shadow covering {obscured:.1%} of the scene were masked before {before}.")
        elif masked:
            # The share is not on any claim of this branch, so it is not spoken (invariant 15).
            sentences.append(f"Cloud and shadow were masked before {before}.")
        else:
            sentences.append("No cloud mask was available for this scene, so values over cloud are included.")

    unphysical = state.get("index_unphysical_fraction") or 0.0
    if state.get("index") and unphysical > 0.0:
        sentences.append(f"{unphysical:.1%} of observed pixels were refused by the formula as unphysical.")

    # The S14 reading, last and labelled: the model's words about the picture, not a measurement.
    if reading:
        sentences.append(f"The vision-language model's reading of the figure (not a measurement): {reading.rstrip('.')}.")

    return " ".join(sentences)


def _claims_carry(state: AnalysisState, metric_label: str) -> bool:
    """Whether some claim of the run carries a metric with this label - the test for speaking its number."""
    return any(metric.get("label") == metric_label for claim in state.get("claims", []) for metric in claim.get("metrics", []))
