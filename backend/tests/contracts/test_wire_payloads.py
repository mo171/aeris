"""The Phase 0.7 gate: a payload this backend serialises validates against the frontend's own schema, and a wrong field name fails.

what  : Meta-validation of the vendored document, and validation of the wire models `app/lib/responses.py`
        already produces against the schemas that will receive them.
where : `tests/contracts/`. No infrastructure - the contracts are a committed artefact.
how   : **The gate is `test_snake_case_field_names_fail_the_contract`, and it is written as the mistake
        rather than as a typo.** The roadmap asks for "a deliberately wrong field name". Renaming a field by
        hand would prove the validator works; serialising with `model_dump()` instead of
        `model_dump(by_alias=True)` proves it catches *the* error - the single most likely serialisation
        mistake in this codebase, one keyword argument away at every call site, and one that produces a
        perfectly reasonable-looking dictionary.

        Phase 1 has no domain wire models yet, so what can be validated today is the envelope and a payload
        built from the backend's own vocabularies. That is not a placeholder: the envelope is what every
        collection endpoint returns, and two of the assertions below pin details of it that nobody would
        guess from reading either side.
"""

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.constants.model_ids import ModelId
from app.constants.statuses import ModelHealth
from app.lib.exceptions import ResourceNotFoundError
from app.lib.responses import ApiErrorPayload, CamelCaseModel, CursorPage

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))

IMAGERY_MODULE = "features/missionCommand/schemas/imagery.schema.ts"
MODEL_MODULE = "features/missionCommand/schemas/model.schema.ts"


def validator_for(module_key: str, schema_name: str) -> Draft202012Validator:
    """A validator with format checking on.

    Formats are advisory in JSON Schema and `jsonschema` ignores them unless asked. Ignoring them here would
    silently drop the `date-time` constraint, which is exactly the constraint the backend is most likely to
    get subtly wrong - see the timestamp test below.
    """
    return Draft202012Validator(
        CONTRACTS[module_key][schema_name],
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


class ModelStatus(CamelCaseModel):
    """One row of `GET /models/status`, built from the backend's own vocabularies.

    Declared here rather than in `app/schemas/` because Phase 2.1 owns that endpoint and an unread model in
    the application would be a claim nothing verifies. What it is doing now is testing the **boundary rule**:
    `to_camel` has to turn `median_latency_ms` into `medianLatencyMs`, and the frontend's schema is the only
    authority on whether it did.
    """

    id: ModelId
    version: str
    health: ModelHealth
    median_latency_ms: int
    queue_depth: int


class ModelStatusCollection(CamelCaseModel):
    models: list[ModelStatus]
    checked_at: datetime


def a_model_status_collection() -> ModelStatusCollection:
    return ModelStatusCollection(
        models=[
            ModelStatus(
                id=ModelId.CHANGEFORMER,
                version="1.0.0",
                health=ModelHealth.ONLINE,
                median_latency_ms=1200,
                queue_depth=0,
            )
        ],
        checked_at=datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC),
    )


async def test_every_vendored_schema_is_a_valid_json_schema() -> None:
    """The artefact is valid JSON Schema, not merely valid JSON.

    Checked because the exporter is a converter: a Zod construct it cannot express could produce something
    that parses as JSON and is meaningless as a schema, and every validation below would then pass against
    nothing.
    """
    checked = 0
    for module_key, schemas in CONTRACTS.items():
        for schema_name, schema in schemas.items():
            try:
                Draft202012Validator.check_schema(schema)
            except Exception as error:  # noqa: BLE001 - the message names which schema, which is the point
                pytest.fail(f"{module_key} :: {schema_name} is not a valid JSON Schema: {error}")
            checked += 1

    assert checked >= 90, f"only {checked} schemas were checked; the export looks truncated"


async def test_the_cursor_page_envelope_matches_the_frontend() -> None:
    """`CursorPage` is what every collection endpoint returns, so its envelope has to be exactly right."""
    page: CursorPage[Any] = CursorPage(items=[], next_cursor=None, total_count=None)

    validator_for(IMAGERY_MODULE, "imageryCatalogPageSchema").validate(page.model_dump(by_alias=True))


async def test_a_null_cursor_must_still_be_present() -> None:
    """`nextCursor` is nullable **and required**, which are different things and are easy to conflate.

    Zod's `.nullable()` means "the key is there and may be null"; it does not mean optional. So serialising
    with `exclude_none=True` - a reasonable-looking way to keep payloads small - drops the key entirely and
    the frontend rejects the whole page. Pinned because the failure is at the boundary, wholesale, and says
    nothing about pagination.
    """
    page: CursorPage[Any] = CursorPage(items=[], next_cursor=None, total_count=None)
    validator = validator_for(IMAGERY_MODULE, "imageryCatalogPageSchema")

    validator.validate(page.model_dump(by_alias=True))

    with pytest.raises(ValidationError) as raised:
        validator.validate(page.model_dump(by_alias=True, exclude_none=True))

    assert "nextCursor" in str(raised.value) or "totalCount" in str(raised.value)


async def test_snake_case_field_names_fail_the_contract() -> None:
    """**The gate.** A payload serialised without `by_alias=True` must not validate.

    Written as the real mistake rather than a hand-typed typo. `model_dump()` is one keyword argument away
    from `model_dump(by_alias=True)` at every call site and returns a dictionary that looks entirely correct
    in a debugger - `next_cursor` instead of `nextCursor`. This is the failure the vendored contracts exist
    to catch, so it is the failure the gate is written against.
    """
    page: CursorPage[Any] = CursorPage(items=[], next_cursor=None, total_count=None)
    validator = validator_for(IMAGERY_MODULE, "imageryCatalogPageSchema")

    snake_case_payload = page.model_dump()
    assert "next_cursor" in snake_case_payload, "the fixture is not actually snake_case"

    with pytest.raises(ValidationError):
        validator.validate(snake_case_payload)


async def test_a_model_status_payload_validates_against_the_frontend_schema() -> None:
    """A payload built from the backend's vocabularies satisfies the schema that will parse it.

    This is where the camelCase rule (`api-contract.md` §1) stops being a convention and becomes checkable:
    `median_latency_ms` must arrive as `medianLatencyMs`, and the frontend's schema is what says so.
    """
    payload = a_model_status_collection().model_dump(by_alias=True, mode="json")

    assert payload["models"][0]["medianLatencyMs"] == 1200
    assert payload["models"][0]["queueDepth"] == 0

    validator_for(MODEL_MODULE, "modelStatusCollectionSchema").validate(payload)


async def test_a_timestamp_must_carry_a_z_suffix_which_means_mode_json_is_not_optional() -> None:
    """`z.iso.datetime()` accepts `...Z` and rejects `...+00:00`. Measured, because the three obvious ways
    to serialise the same UTC instant do not agree:

        datetime.isoformat()                     2026-08-31T12:00:00+00:00   <- REJECTED
        model_dump(mode="json")                  2026-08-31T12:00:00Z        <- accepted
        model_dump()            (mode="python")  datetime(...) object        <- not a string at all

    The frontend's exported pattern ends `(?:Z)$`; Zod does not permit a numeric offset unless the schema
    asks for one, and none of these do. Pydantic's JSON mode happens to emit exactly the right form, which
    is lucky rather than obvious - and it means **`mode="json"` is part of the contract**, not a
    formatting preference. The default `mode="python"` returns live `datetime` objects that never reach the
    wire correctly, and anyone hand-rolling a timestamp with `.isoformat()` produces the rejected form.

    Pinned as a test because it is invisible from either side: the Python reads correctly, the Zod reads
    correctly, and the two disagree about four characters.
    """
    collection = a_model_status_collection()
    validator = validator_for(MODEL_MODULE, "modelStatusCollectionSchema")

    correct = collection.model_dump(by_alias=True, mode="json")
    assert correct["checkedAt"] == "2026-08-31T12:00:00Z"
    validator.validate(correct)

    # The hand-rolled form, which is what `.isoformat()` gives you.
    with pytest.raises(ValidationError):
        validator.validate({**correct, "checkedAt": "2026-08-31T12:00:00+00:00"})

    # And the default dump mode, which never produces a string at all.
    with pytest.raises(ValidationError):
        validator.validate(collection.model_dump(by_alias=True))


async def test_the_error_payload_keeps_its_four_fields() -> None:
    """The frontend types `ApiErrorPayload` in TypeScript rather than Zod, so there is no schema to validate
    against - which is why `ErrorCode` sits in `BACKEND_ONLY_VOCABULARIES` with that reason recorded.

    The shape is still a contract (`api-contract.md` §1), so it is checked here against the four field names
    the frontend's `ApiError` constructor destructures.
    """
    payload = ApiErrorPayload.from_error(
        ResourceNotFoundError("No scene scn_01.", details={"sceneId": "scn_01"})
    ).model_dump(by_alias=True)

    assert set(payload) == {"message", "code", "status", "details"}
    assert payload["code"] == "RESOURCE_NOT_FOUND"
    assert payload["status"] == 404
