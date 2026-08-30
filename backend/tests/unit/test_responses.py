"""Proves the one wire rule that cannot be caught by reading code: field names arrive as camelCase.

what  : Tests for `CamelCaseModel`, `CursorPage`, `CursorPageRequest` and `ApiErrorPayload`.
where : `tests/unit/`. These run before any route exists, which is the point - the envelope is settled in
        Phase 0 so Phase 2 has nothing to negotiate.
how   : `api-contract.md` §1 rule 1 says the wire is camelCase and names are never shortened. A single field
        serialised as `next_cursor` makes the frontend's Zod reject the entire payload, and the symptom appears
        as an empty list rather than as an error, so it is worth a test rather than a convention.

        `test_multi_word_field_is_not_abbreviated` uses the field name the contract itself cites, because the
        failure it guards against is a well-meant rename to something shorter.
"""

import pytest
from pydantic import ValidationError

from app.constants.errors import ErrorCode
from app.lib.exceptions import ResourceNotFoundError, UpstreamUnavailableError
from app.lib.responses import ApiErrorPayload, CamelCaseModel, CursorPage, CursorPageRequest


class _SceneSummary(CamelCaseModel):
    """A stand-in for a real schema, with the kind of long field name the contract insists on."""

    scene_id: str
    ground_sample_distance_meters: float
    cloud_cover_percentage: float | None = None


async def test_multi_word_field_is_not_abbreviated() -> None:
    scene = _SceneSummary(scene_id="scn_1", ground_sample_distance_meters=10.0)

    serialised = scene.model_dump(by_alias=True)

    assert serialised["sceneId"] == "scn_1"
    assert serialised["groundSampleDistanceMeters"] == 10.0


async def test_model_accepts_either_spelling() -> None:
    """`populate_by_name=True` - constructed in Python by snake_case, parsed from the wire by camelCase."""
    from_wire = _SceneSummary.model_validate(
        {"sceneId": "scn_1", "groundSampleDistanceMeters": 10.0, "cloudCoverPercentage": None}
    )

    assert from_wire.scene_id == "scn_1"


async def test_null_cloud_cover_survives_serialisation() -> None:
    """SAR scenes carry `None`, never `0` - `api-contract.md` §1 rule 3. Zero asserts a cloud-free radar scene."""
    serialised = _SceneSummary(
        scene_id="scn_sar", ground_sample_distance_meters=20.0
    ).model_dump(by_alias=True)

    assert serialised["cloudCoverPercentage"] is None


async def test_cursor_page_serialises_to_the_frontend_shape() -> None:
    page: CursorPage[_SceneSummary] = CursorPage(
        items=[_SceneSummary(scene_id="scn_1", ground_sample_distance_meters=10.0)],
        next_cursor="eyJpZCI6ICJzY25fMSJ9",
        total_count=None,
    )

    serialised = page.model_dump(by_alias=True)

    assert set(serialised) == {"items", "nextCursor", "totalCount"}
    assert serialised["totalCount"] is None
    assert serialised["items"][0]["sceneId"] == "scn_1"


async def test_page_request_clamps_an_oversized_limit() -> None:
    """A client asking for more than `MAXIMUM_PAGE_SIZE` is rejected rather than served."""
    with pytest.raises(ValidationError):
        CursorPageRequest(limit=50_000)

    assert CursorPageRequest().limit > 0


async def test_error_payload_carries_the_code_a_client_branches_on() -> None:
    payload = ApiErrorPayload.from_error(ResourceNotFoundError("No scene scn_missing."))

    serialised = payload.model_dump(by_alias=True, exclude_none=True)

    assert serialised["code"] == ErrorCode.RESOURCE_NOT_FOUND.value
    assert serialised["status"] == 404
    assert "details" not in serialised


async def test_error_details_are_preserved_for_attribution() -> None:
    """An upstream failure must say which upstream, without anyone reading our logs."""
    payload = ApiErrorPayload.from_error(
        UpstreamUnavailableError(
            "The imagery catalogue did not respond.",
            details={"upstream": "planetary-computer-stac", "attempts": 3},
        )
    )

    assert payload.details == {"upstream": "planetary-computer-stac", "attempts": 3}
    assert payload.status == 503
