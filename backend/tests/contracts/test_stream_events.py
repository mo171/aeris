"""Proves the events this backend models are the events the frontend parses - same names, same fields, same union.

what  : Tests over `app/schemas/events/` and `app/constants/events.py` against the two stream unions in the
        vendored contracts.
where : `tests/contracts/`. No infrastructure - the contracts are a committed artefact and the event models
        are pure.
how   : `api-contract.md` §3 makes a claim the whole two-phase plan rests on: "In Phase 1 these are exactly
        the objects the CLI prints and journals", which is what makes Phase 2 a transport swap rather than
        a rewrite. That is only true if the objects match, and it is exactly the kind of claim that is true
        when written and false four sub-phases later.

        The frontend spells its event types as string literals inside a discriminated union rather than as
        an exported enum, so the 0.7 vocabulary test cannot pair them automatically - which is why
        `AnalysisEventType` sits in `BACKEND_ONLY_VOCABULARIES`. It is checked here instead, and more
        strictly: not just that the names match, but that every modelled event **validates against the
        frontend's schema for that event**, field by field.

        The test that keeps this honest over time is `test_every_analysis_event_is_modelled_or_recorded`.
        Five of the seven events can be built today; the other two carry payloads no subsystem produces
        yet. Recording those two with the phase that will produce them - rather than leaving a silent gap -
        means adding a sixth model, or the frontend adding an eighth event, forces a decision here.
"""

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.constants.events import (
    EVENT_TYPES_NOT_YET_EMITTED,
    EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND,
    AnalysisEventType,
    AssistantEventType,
)
from app.constants.intents import Intent
from app.constants.stages import PipelineStage
from app.constants.statuses import TraceStepState
from app.schemas.events import (
    ANALYSIS_STREAM_EVENT_ADAPTER,
    AnalysisTraceStep,
    AnswerTokenEvent,
    InsufficientEvidence,
    InsufficientEvidenceRemedy,
    RunCompleteEvent,
    RunErrorEvent,
    RunStartEvent,
    TraceStepEvent,
    parse_event,
    serialise_event,
)

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))

ANALYSIS_MODULE = "features/investigation/schemas/analysis.schema.ts"
ASSISTANT_MODULE = "features/missionCommand/schemas/assistant.schema.ts"

RUN_ID = "run_01J000000000000000000000"
STEP_ID = "stp_01J000000000000000000000"


def union_members(module_key: str, schema_name: str) -> dict[str, dict[str, Any]]:
    """The frontend's union, split into one schema per `type` discriminator."""
    union = CONTRACTS[module_key][schema_name]
    return {member["properties"]["type"]["const"]: member for member in union["oneOf"]}


ANALYSIS_MEMBERS = union_members(ANALYSIS_MODULE, "analysisStreamEventSchema")
ASSISTANT_MEMBERS = union_members(ASSISTANT_MODULE, "assistantStreamEventSchema")

# One of each event this backend can actually build, keyed by its wire type. Built with real vocabulary
# values rather than placeholder strings, so a stage code or a step state that drifted would fail here too.
MODELLED_EVENTS = {
    AnalysisEventType.RUN_START: RunStartEvent(
        run_id=RUN_ID, intent=Intent.CHANGE_DETECT, started_at=datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)
    ),
    AnalysisEventType.TRACE_STEP: TraceStepEvent(
        run_id=RUN_ID,
        step=AnalysisTraceStep(
            id=STEP_ID,
            stage_code=PipelineStage.S13,
            state=TraceStepState.COMPLETED,
            detail="ChangeFormer over the co-registered pair",
            duration_ms=1200,
            model_id="changeformer",
            model_version="1.0.0",
            artefact_layer_id="lyr_01J000000000000000000000",
        ),
    ),
    AnalysisEventType.ANSWER_TOKEN: AnswerTokenEvent(run_id=RUN_ID, text="Built-up"),
    AnalysisEventType.RUN_COMPLETE: RunCompleteEvent(
        run_id=RUN_ID, confidence=0.91, insufficient_evidence=None, total_duration_ms=42_000
    ),
    AnalysisEventType.RUN_ERROR: RunErrorEvent(run_id=RUN_ID, message="ChangeFormer is not loaded."),
}


def validator_for(member: dict[str, Any]) -> Draft202012Validator:
    """A validator with format checking on, so `date-time` is enforced rather than advisory."""
    return Draft202012Validator(member, format_checker=Draft202012Validator.FORMAT_CHECKER)


async def test_the_backend_event_names_are_the_frontend_union_exactly() -> None:
    """`AnalysisEventType` equals the union's discriminators, once the agreed-but-unimplemented ones are set
    aside - not a subset, not a superset.

    A missing member means an event the frontend can render and the backend can never send. An extra one is
    worse: the backend emits something the frontend's Zod has never heard of, the parse throws at the
    boundary, and the operator sees a blank surface rather than an error naming the field.

    **The exclusion is narrow on purpose.** `api-contract.md` marks three events agreed and not yet
    implemented on the frontend (§4 `ui-command`, §5 `speech`, §6 `figure-ready`), and the backend
    implements them ahead of it - 1.2.1 built `figure-ready`. Excluding exactly those, by name and with a
    reason, keeps the equality check on everything else rather than weakening it to a subset.
    """
    emitted = {member.value for member in AnalysisEventType}
    agreed_but_unparsed = {
        member.value for member in EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND
    }

    assert emitted - agreed_but_unparsed == set(ANALYSIS_MEMBERS)


async def test_nothing_is_listed_as_unparsed_that_the_frontend_now_parses() -> None:
    """The staleness check that makes the exclusion above safe.

    When the frontend ships its figure panel, `figure-ready` joins its union - and this fails until the
    entry is removed, at which point the equality test starts enforcing the event properly. Without this,
    an exclusion added once would silently stay forever.
    """
    still_unparsed = {
        member.value for member in EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND
    }
    now_parsed = still_unparsed & set(ANALYSIS_MEMBERS)

    assert not now_parsed, (
        f"The frontend now parses {sorted(now_parsed)}. Remove them from "
        "`EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND` so the union test enforces them."
    )


async def test_the_assistant_event_names_are_its_union_exactly() -> None:
    """The same, for the assistant stream. Two enums because the two streams' trace steps differ in shape."""
    assert {member.value for member in AssistantEventType} == set(ASSISTANT_MEMBERS)


@pytest.mark.parametrize("event_type", sorted(MODELLED_EVENTS))
async def test_a_modelled_event_validates_against_the_frontend_schema(event_type: AnalysisEventType) -> None:
    """Every event the backend can build satisfies the frontend's schema for that event, field by field.

    This is the check `api-contract.md` §3's claim actually rests on. Names matching is not enough - the
    frontend rejects the whole event for one camelCase field spelled wrongly or one required nullable key
    left out.
    """
    payload = serialise_event(MODELLED_EVENTS[event_type])

    assert payload["type"] == event_type.value
    validator_for(ANALYSIS_MEMBERS[event_type.value]).validate(payload)


async def test_every_analysis_event_is_modelled_or_recorded() -> None:
    """**The test that keeps the rest honest.** No event may exist without a decision about it.

    Same rule as `test_every_backend_enum_is_classified` in 0.7, pointed at events. An event that is
    neither modelled nor explicitly recorded as owed is a gap nothing surfaces - and the way this suite
    would rot is that Phase 1.5 adds a `claim` model, nobody adds it here, and it is never validated
    against the schema that parses it.
    """
    modelled = {event_type.value for event_type in MODELLED_EVENTS}
    recorded = {event_type.value for event_type in EVENT_TYPES_NOT_YET_EMITTED}

    unaccounted = sorted(set(ANALYSIS_MEMBERS) - modelled - recorded)
    assert not unaccounted, (
        f"The frontend defines these analysis events and the backend does neither: {unaccounted}. "
        "Model each in `app/schemas/events/`, or record the sub-phase that will in "
        "`EVENT_TYPES_NOT_YET_EMITTED`."
    )

    # And the reverse, both ways: a recorded event that was quietly modelled is a stale entry, and a
    # recorded event the frontend no longer defines is a check doing nothing.
    assert not (modelled & recorded), (
        f"These are modelled and also recorded as not-yet-emitted: {sorted(modelled & recorded)}. "
        "Remove them from `EVENT_TYPES_NOT_YET_EMITTED`."
    )
    assert not (recorded - set(ANALYSIS_MEMBERS)), (
        f"These are recorded as owed but the frontend no longer defines them: "
        f"{sorted(recorded - set(ANALYSIS_MEMBERS))}."
    )


async def test_a_snake_case_event_fails_the_contract() -> None:
    """**The gate, in the shape of the real mistake.** `model_dump()` without `by_alias=True` must not pass.

    Not a hand-typed typo. `serialise_event()` exists precisely because that one keyword argument is a
    plausible omission at every call site, and it produces a dictionary that looks entirely correct in a
    debugger - `run_id` instead of `runId`.
    """
    event = MODELLED_EVENTS[AnalysisEventType.RUN_START]
    validator = validator_for(ANALYSIS_MEMBERS["run-start"])

    validator.validate(serialise_event(event))

    snake_case = event.model_dump(mode="json")
    assert "run_id" in snake_case, "the fixture is not actually snake_case"
    assert not validator.is_valid(snake_case)


async def test_a_timestamp_without_its_z_fails() -> None:
    """`startedAt` must be `...Z`, which means `mode="json"` is part of the contract rather than a preference.

    Pinned again here because 0.7 pinned it for a response body and this is the stream - the same four
    characters, a different producer, and `serialise_event()` is the only thing standing between them.
    """
    validator = validator_for(ANALYSIS_MEMBERS["run-start"])
    payload = serialise_event(MODELLED_EVENTS[AnalysisEventType.RUN_START])

    assert payload["startedAt"] == "2026-08-31T12:00:00Z"
    validator.validate(payload)

    assert not validator.is_valid({**payload, "startedAt": "2026-08-31T12:00:00+00:00"})


async def test_a_nullable_field_is_still_required() -> None:
    """`confidence` and `insufficientEvidence` are nullable **and** required, which are different things.

    So `exclude_none=True` - a reasonable-looking way to keep a stream light - drops both keys and the
    frontend rejects the completion of a run that actually succeeded.
    """
    event = MODELLED_EVENTS[AnalysisEventType.RUN_COMPLETE]
    validator = validator_for(ANALYSIS_MEMBERS["run-complete"])

    validator.validate(serialise_event(event))
    assert not validator.is_valid(event.model_dump(by_alias=True, mode="json", exclude_none=True))


async def test_confidence_is_never_coerced_to_zero() -> None:
    """`None` is "no claim"; `0.0` is the claim "no confidence" (`api-contract.md` §1 rule 2).

    The frontend renders the first as an explicit refusal card and the second as a very bad result, so a
    `or 0.0` anywhere on this path would be a silent change of meaning rather than a formatting choice.
    """
    declined = RunCompleteEvent(
        run_id=RUN_ID, confidence=None, insufficient_evidence=None, total_duration_ms=1
    )
    payload = serialise_event(declined)

    assert payload["confidence"] is None
    validator_for(ANALYSIS_MEMBERS["run-complete"]).validate(payload)


async def test_an_insufficient_evidence_completion_is_a_success_not_an_error() -> None:
    """A refusal travels on `run-complete` (`api-contract.md` §1 rule 7, PDF p.38).

    A system that says "I cannot answer this from these two scenes, and here is what would let me" has
    succeeded at what it is for. Routing that through `run-error` would show the operator an incident.
    """
    refusal = RunCompleteEvent(
        run_id=RUN_ID,
        confidence=None,
        insufficient_evidence=InsufficientEvidence(
            reason="The two scenes are 400 m apart after co-registration.",
            remedies=[
                InsufficientEvidenceRemedy(
                    id="rem_recoregister", label="Re-run co-registration", prompt="Co-register and retry."
                )
            ],
        ),
        total_duration_ms=5_000,
    )

    validator_for(ANALYSIS_MEMBERS["run-complete"]).validate(serialise_event(refusal))


async def test_an_event_round_trips_through_the_journal_form() -> None:
    """Serialise then parse gives back the same event, which is what `--replay` depends on."""
    for event in MODELLED_EVENTS.values():
        assert parse_event(serialise_event(event)) == event


async def test_an_unknown_event_type_is_rejected_rather_than_ignored() -> None:
    """A journal line this backend does not understand fails loudly.

    Replaying the part of a journal we happen to understand would present a partial record as a complete
    one - the worst outcome for an artefact whose entire job is provenance.
    """
    with pytest.raises(ValidationError):
        ANALYSIS_STREAM_EVENT_ADAPTER.validate_python({"type": "layer-ready", "runId": RUN_ID})


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/contracts/ -q                                                2026-08-31
#
#   .....................................................                    [100%]
#   53 passed in 3.62s
#
# 15 of those are this file. No infrastructure - the contracts are a committed artefact (0.7) and the event
# models are pure, so these run on a machine that has never installed Node or started a container.
#
# Five of the seven analysis events are modelled; `layer-ready` and `claim` are recorded in
# `EVENT_TYPES_NOT_YET_EMITTED` with the sub-phase that will build their payloads (1.2.1 and 1.5). Both
# assistant-stream discriminators match too, though nothing emits them until Phase 2.
#
# Checked by mutation:
#
#   `serialise_event` without `by_alias=True`     -> 4 tests FAILED here, and all 4 in test_run_journal.py
#   an eighth member added to AnalysisEventType   -> test_the_backend_event_names_are_the_frontend_union
#                                                    _exactly FAILED
#   `layer-ready` removed from EVENT_TYPES_NOT    -> test_every_analysis_event_is_modelled_or_recorded
#   _YET_EMITTED                                     FAILED
#   a frontend vocabulary listed that the         -> test_every_frontend_vocabulary_is_classified FAILED
#   frontend no longer defines                       (0.7's test, still holding in 1.0)
#
# The `EVENT_TYPES_NOT_YET_EMITTED` one is what keeps this file honest over time. Without it, Phase 1.5 adds
# a `claim` model, nobody adds it here, and it is never validated against the schema that will parse it.
#
# Worth recording about the process rather than the code: the first version of this comment listed two
# mutations that had not actually been run. They were run afterwards and both behaved as claimed - but a
# recorded result nobody executed is exactly the kind of evidence this file exists to replace.
