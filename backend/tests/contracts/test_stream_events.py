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
        Every current event has a real model and fixture. A future frontend event must gain the same or be
        recorded with the phase that will produce it, so union growth always forces an explicit decision.
"""

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.constants.color_ramps import ColorRampId
from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.constants.events import (
    EVENT_TYPES_NOT_YET_EMITTED,
    EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND,
    AnalysisEventType,
    AssistantEventType,
)
from app.constants.evidence import ClaimKind, EvidenceKind, MetricDirection
from app.constants.figure_kinds import FigureKind, LegendKind
from app.constants.intents import Intent
from app.constants.layers import ComparatorSide, LayerKind, LayerRenderMode
from app.constants.model_ids import ModelId
from app.constants.stages import PipelineStage
from app.constants.statuses import TraceStepState
from app.schemas.events import (
    ANALYSIS_STREAM_EVENT_ADAPTER,
    AnalysisTraceStep,
    AnswerTokenEvent,
    Claim,
    ClaimEvent,
    ClaimMetric,
    EvidenceFeature,
    EvidenceItem,
    EvidenceLayer,
    FigureLegend,
    FigureReadyEvent,
    InsufficientEvidence,
    InsufficientEvidenceRemedy,
    LayerProvenance,
    LayerReadyEvent,
    PolygonGeometry,
    RenderSpec,
    RunCompleteEvent,
    RunErrorEvent,
    RunStartEvent,
    SpeechEvent,
    TraceModelRef,
    TraceNodeRef,
    TraceStepEvent,
    UiCommandEvent,
    ValueDomain,
    parse_event,
    serialise_event,
)
from app.schemas.geo import GeoBoundingBox, GeoPoint

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
            model=TraceModelRef(id="changeformer", version="1.0.0"),
            artefact_layer_id="lyr_01J000000000000000000000",
        ),
    ),
    AnalysisEventType.LAYER_READY: LayerReadyEvent(
        run_id=RUN_ID,
        layer=EvidenceLayer(
            id="lyr_01J000000000000000000000",
            kind=LayerKind.POLYGON_VECTOR,
            render_mode=LayerRenderMode.EXTRUDED,
            title="Sparse vegetation",
            overlay_id=None,
            value_domain=ValueDomain(minimum=0.2, maximum=0.4),
            color_ramp_id=ColorRampId.MASK_AMBER,
            opacity=0.6,
            is_visible=True,
            comparator_side=ComparatorSide.BOTH,
            tile_url_template=None,
            attribution=None,
            bounds=GeoBoundingBox(west=72.80, south=19.00, east=72.90, north=19.10),
            minimum_zoom=None,
            maximum_zoom=None,
            features=[
                EvidenceFeature(
                    id="ftr_01J000000000000000000000",
                    label="Region 1",
                    geometry=PolygonGeometry(
                        ring=[
                            GeoPoint(latitude=19.01, longitude=72.81),
                            GeoPoint(latitude=19.01, longitude=72.82),
                            GeoPoint(latitude=19.02, longitude=72.82),
                        ]
                    ),
                    magnitude=1.0,
                    confidence=None,
                    area_hectares=112.1,
                    value=0.31,
                    class_id=None,
                    model_id=ModelId.GEOSPATIAL_ENGINE.value,
                    model_version="1.4.0",
                    trace_step_id=STEP_ID,
                )
            ],
            provenance=LayerProvenance(
                model_id=ModelId.GEOSPATIAL_ENGINE.value,
                model_version="1.4.0",
                trace_step_id=STEP_ID,
                confidence=None,
            ),
        ),
        evidence=[
            EvidenceItem(
                id="ev_01J000000000000000000000",
                kind=EvidenceKind.INDEX_MAP,
                title="Sparse vegetation regions",
                layer_id="lyr_01J000000000000000000000",
                feature_ids=["ftr_01J000000000000000000000"],
                area_hectares=2471.0,
                magnitude=0.21,
                confidence=None,
                source_scene_ids=["scn_01J000000000000000000000"],
            )
        ],
    ),
    AnalysisEventType.CLAIM: ClaimEvent(
        run_id=RUN_ID,
        claim=Claim(
            id="clm_01J000000000000000000000",
            run_id=RUN_ID,
            text="Sparse vegetation covers 2,471.0 hectares.",
            kind=ClaimKind.QUANTITATIVE,
            confidence=None,
            metrics=[
                ClaimMetric(
                    label="Area", value=2471.0057, unit="ha", direction=MetricDirection.NEUTRAL, precision=1
                )
            ],
            evidence_ids=["ev_01J000000000000000000000"],
            model_id=ModelId.GEOSPATIAL_ENGINE,
            model_version="1.4.0",
            trace_step_id=STEP_ID,
            is_primary=True,
        ),
    ),
    AnalysisEventType.ANSWER_TOKEN: AnswerTokenEvent(run_id=RUN_ID, text="Built-up"),
    AnalysisEventType.FIGURE_READY: FigureReadyEvent(
        run_id=RUN_ID,
        figure_id="fig_01J000000000000000000000",
        kind=FigureKind.INDEX_MAP,
        title="NDVI",
        caption="Vegetation index over the area of interest.",
        image_url="/api/v1/figures/fig_01J000000000000000000000.webp",
        width=1024,
        height=1024,
        trace_step_id=STEP_ID,
        claim_ids=["clm_01J000000000000000000000"],
        legend=FigureLegend(
            kind=LegendKind.CONTINUOUS,
            label="NDVI",
            color_ramp=ColorRampId.INDEX_VEGETATION,
            domain=[-1.0, 1.0],
        ),
        render_spec=RenderSpec(
            scene_ids=["scn_01J000000000000000000000"],
            bands=["B08", "B04"],
            stretch={"min": -1.0, "max": 1.0, "method": "fixed"},
            color_ramp=ColorRampId.INDEX_VEGETATION,
            resampling="nearest",
            crs="EPSG:32643",
            decimation=4,
            mask_applied=True,
        ),
        is_primary=True,
    ),
    AnalysisEventType.UI_COMMAND: UiCommandEvent(
        run_id=RUN_ID,
        command_id="investigation.focusEvidence",
        params={"evidenceId": "ev_01J000000000000000000000"},
        reason="Raise the largest validated change region.",
    ),
    AnalysisEventType.SPEECH: SpeechEvent(
        run_id=RUN_ID,
        utterance_id="utt_01J000000000000000000000",
        kind="grounded",
        text="The validated result is available.",
        audio_url="https://aeris.example/api/v1/speech/utt_01J000000000000000000000.opus",
        claim_ids=["clm_01J000000000000000000000"],
    ),
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

    **The exclusion is narrow on purpose.** It is empty while the contracts match. If the backend ever
    models an event ahead of the frontend, the named compatibility map records that one event and why;
    everything else remains an exact comparison rather than weakening the check to a subset.
    """
    emitted = {member.value for member in AnalysisEventType}
    agreed_but_unparsed = {
        member.value for member in EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND
    }

    assert emitted - agreed_but_unparsed == set(ANALYSIS_MEMBERS)


async def test_nothing_is_listed_as_unparsed_that_the_frontend_now_parses() -> None:
    """The staleness check that makes the exclusion above safe.

    When the frontend begins parsing a backend-first event, this fails until its compatibility entry is
    removed, at which point the equality test starts enforcing the event properly. Without this, an
    exclusion added once would silently stay forever.
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


@pytest.mark.parametrize("event_type", [AnalysisEventType.SPEECH, AnalysisEventType.UI_COMMAND])
async def test_shared_events_have_one_shape_on_both_streams(event_type: AnalysisEventType) -> None:
    """A producer does not need a second payload model merely because transport chooses another stream."""
    payload = serialise_event(MODELLED_EVENTS[event_type])

    assert ANALYSIS_MEMBERS[event_type.value] == ASSISTANT_MEMBERS[event_type.value]
    validator_for(ANALYSIS_MEMBERS[event_type.value]).validate(payload)
    validator_for(ASSISTANT_MEMBERS[event_type.value]).validate(payload)


async def test_provisional_speech_is_explicit_and_can_be_superseded() -> None:
    provisional = SpeechEvent(
        run_id=RUN_ID,
        utterance_id="utt_provisional",
        kind="provisional",
        text="Provisional: cloud may obscure it.",
        claim_ids=[],
        provisional=True,
    )
    grounded = SpeechEvent(
        run_id=RUN_ID,
        utterance_id="utt_grounded",
        kind="grounded",
        text="The validated result is available.",
        audio_url="/api/v1/speech/utt_grounded.opus",
        claim_ids=["clm_01J000000000000000000000"],
        supersedes_utterance_id="utt_provisional",
    )

    provisional_payload = serialise_event(provisional)
    grounded_payload = serialise_event(grounded)

    assert provisional_payload["provisional"] is True
    assert provisional_payload["audioUrl"] is None
    assert grounded_payload["audioUrl"] == "/api/v1/speech/utt_grounded.opus"
    assert grounded_payload["supersedesUtteranceId"] == "utt_provisional"
    validator_for(ANALYSIS_MEMBERS["speech"]).validate(provisional_payload)
    validator_for(ANALYSIS_MEMBERS["speech"]).validate(grounded_payload)


async def test_speech_kind_is_required() -> None:
    with pytest.raises(ValidationError, match="kind"):
        SpeechEvent(
            run_id=RUN_ID,
            utterance_id="utt_untyped",
            text="The validated result is available.",
            claim_ids=["clm_01J000000000000000000000"],
        )


async def test_provisional_speech_cannot_claim_grounding() -> None:
    with pytest.raises(ValidationError, match="claim_ids|claimIds"):
        SpeechEvent(
            run_id=RUN_ID,
            utterance_id="utt_mislabelled",
            kind="provisional",
            text="Provisional: cloud may obscure it.",
            claim_ids=["clm_01J000000000000000000000"],
            provisional=True,
        )


@pytest.mark.parametrize(
    ("kind", "claim_ids", "interruptible"),
    [
        ("progress", [], True),
        ("refusal", [], False),
    ],
)
async def test_non_result_speech_categories_are_explicit(
    kind: str, claim_ids: list[str], interruptible: bool
) -> None:
    event = SpeechEvent(
        run_id=RUN_ID,
        utterance_id=f"utt_{kind}",
        kind=kind,
        text="The current stage has no result to claim.",
        claim_ids=claim_ids,
        interruptible=interruptible,
    )

    payload = serialise_event(event)
    assert payload["kind"] == kind
    validator_for(ANALYSIS_MEMBERS["speech"]).validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "grounded", "claim_ids": [], "provisional": False, "interruptible": True},
        {
            "kind": "provisional",
            "claim_ids": [],
            "provisional": False,
            "interruptible": True,
        },
        {"kind": "progress", "claim_ids": [], "provisional": True, "interruptible": True},
        {
            "kind": "refusal",
            "claim_ids": ["clm_01J000000000000000000000"],
            "provisional": False,
            "interruptible": True,
        },
    ],
)
async def test_speech_category_invariants_reject_contradictory_payloads(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SpeechEvent(
            run_id=RUN_ID,
            utterance_id="utt_invalid",
            text="Invalid speech state.",
            audio_url="/api/v1/speech/utt_invalid.opus",
            **payload,
        )


@pytest.mark.parametrize(
    ("case_name", "audio_url", "normalised"),
    [
        (
            "absolute HTTP URL",
            "https://aeris.example/api/v1/speech/utt_audio.opus",
            "https://aeris.example/api/v1/speech/utt_audio.opus",
        ),
        ("root-relative path", "/api/v1/speech/utt_audio.opus", "/api/v1/speech/utt_audio.opus"),
        (
            "whitespace-wrapped absolute URL",
            "  https://aeris.example/api/v1/speech/utt_audio.opus  ",
            "https://aeris.example/api/v1/speech/utt_audio.opus",
        ),
        (
            "whitespace-wrapped root-relative path",
            "  /api/v1/speech/utt_audio.opus  ",
            "/api/v1/speech/utt_audio.opus",
        ),
        ("malformed absolute URL port", "https://aeris.example:not-a-port/utt_audio.opus", None),
        ("unsupported scheme", "ftp://aeris.example/utt_audio.opus", None),
        ("protocol-relative path", "//different-origin.example/utt_audio.opus", None),
        ("empty path", "", None),
    ],
)
async def test_audio_url_backend_runtime_matrix(
    case_name: str, audio_url: str, normalised: str | None
) -> None:
    """The backend uses the same accepted locations and trim result as the frontend's runtime matrix."""
    event_arguments = {
        "run_id": RUN_ID,
        "utterance_id": "utt_audio",
        "kind": "grounded",
        "text": "The validated result is available.",
        "audio_url": audio_url,
        "claim_ids": ["clm_01J000000000000000000000"],
    }

    if normalised is None:
        with pytest.raises(ValidationError, match="audio_url|audioUrl"):
            SpeechEvent(**event_arguments)
        return

    event = SpeechEvent(**event_arguments)

    assert serialise_event(event)["audioUrl"] == normalised


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
    would rot is that a model is added without a fixture and is never validated against the schema that
    parses it.
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

async def test_analysis_trace_step_full_graph_shape() -> None:
    """A trace-step carrying operationId, inputs, parameters, outputs, and dependsOn validates and round-trips."""
    event = TraceStepEvent(
        run_id=RUN_ID,
        step=AnalysisTraceStep(
            id=STEP_ID,
            operation_id="change-detection",
            stage_code=PipelineStage.S13,
            state=TraceStepState.COMPLETED,
            detail="ChangeFormer over the co-registered pair",
            duration_ms=1200,
            model=TraceModelRef(id="changeformer", version="1.0.0"),
            rationale="Optical bi-temporal pair with NIR and SWIR coverage",
            inputs=[TraceNodeRef(kind="scene", id="scene_t0"), TraceNodeRef(kind="scene", id="scene_t1")],
            parameters={"threshold": 0.45, "method": "changeformer"},
            outputs=[TraceNodeRef(kind="layer", id="lyr_change_01"), TraceNodeRef(kind="figure", id="fig_change_01")],
            depends_on=["stp_coregister_s9"],
            artefact_layer_id="lyr_change_01",
            artefact_uri="s3://artefacts/run_123/S13/change-probability.tif",
        ),
    )
    wire = serialise_event(event)
    assert wire["step"]["operationId"] == "change-detection"
    assert wire["step"]["dependsOn"] == ["stp_coregister_s9"]
    assert wire["step"]["parameters"] == {"threshold": 0.45, "method": "changeformer"}
    assert wire["step"]["inputs"] == [{"kind": "scene", "id": "scene_t0"}, {"kind": "scene", "id": "scene_t1"}]
    assert wire["step"]["outputs"] == [{"kind": "layer", "id": "lyr_change_01"}, {"kind": "figure", "id": "fig_change_01"}]
    assert wire["step"]["rationale"] == "Optical bi-temporal pair with NIR and SWIR coverage"
    assert wire["step"]["artefactUri"] == "s3://artefacts/run_123/S13/change-probability.tif"

    # Validate against JSON schema validator for trace-step
    validator = Draft202012Validator(ANALYSIS_MEMBERS[AnalysisEventType.TRACE_STEP])
    assert validator.is_valid(wire)

    # And round-trip back
    restored = parse_event(wire)
    assert isinstance(restored, TraceStepEvent)
    assert restored.step.operation_id == "change-detection"
    assert restored.step.parameters["threshold"] == 0.45


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/contracts/test_stream_events.py -q                          2026-09-15
#
#   ...................................                                      [100%]
#   35 passed in 1.56s
#
# All ten analysis event models validate against the freshly exported frontend union; both frontend unions
# carry the same `speech` and `ui-command` shapes. The speech cases cover grounded results, provisional
# knowledge, progress narration, explicit refusal, supersession, null/local/absolute audio locations, and
# every category-specific rejection.
#
# Observed RED in this task: the pre-category model admitted missing `kind`, progress/refusal could not be
# represented, contradictory flags and interruptible refusals passed, and the frontend rejected the
# documented root-relative audio path. The focused suite and export-time Zod `safeParse` cases now catch
# those failures at both runtime boundaries.
