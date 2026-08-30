"""The three shapes every response takes: a camelCase model, a cursor page, an error payload.

what  : `CamelCaseModel` (the base class for everything that crosses the wire), `CursorPage[TItem]`,
        `CursorPageRequest`, `ApiErrorPayload`.
where : Inherited by every schema in `app/schemas/`, and returned by every route in Phase 2. In Phase 1 the same
        models are what the CLI journals, which is what makes Phase 2 a transport swap rather than a rewrite -
        the run journal is already wire-shaped.
how   : **camelCase is produced by the alias generator, once, here.** Python stays `snake_case`; the wire is
        camelCase; `populate_by_name=True` means a model can be constructed with either. Doing this per-field
        would guarantee that one field is eventually spelled `area_hectares` on the wire, and the frontend's Zod
        would reject the whole payload for it.

        Names are never shortened across the boundary - `ground_sample_distance_meters` becomes
        `groundSampleDistanceMeters` and nothing shorter (`api-contract.md` §1 rule 1).

        `CursorPage` matches the frontend's `CursorPage<TItem>` exactly, including that both `nextCursor` and
        `totalCount` are nullable. `totalCount: None` is not zero and not an error; it means the count was not
        worth a second query, and the frontend renders "25+" rather than a total. `nextCursor: None` is the only
        end-of-sequence signal - never an empty `items` array, which is also what a filtered page looks like.

        A single resource is returned bare, not wrapped in an envelope. The frontend's `api.types.ts` expects
        the resource itself, and a `{data: ...}` wrapper would have to be unwrapped in every hook.
"""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.constants.pagination import DEFAULT_PAGE_SIZE, MAXIMUM_PAGE_SIZE
from app.lib.exceptions import AerisError, to_error_payload


class CamelCaseModel(BaseModel):
    """Base class for every model that crosses the boundary. Serialise with `model_dump(by_alias=True)`."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class CursorPage[TItem](CamelCaseModel):
    """One page of a cursor-paginated collection. Mirrors the frontend's `CursorPage<TItem>`."""

    items: list[TItem]
    next_cursor: str | None = None
    total_count: int | None = None


class CursorPageRequest(CamelCaseModel):
    """The query parameters every paginated endpoint accepts."""

    cursor: str | None = None
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAXIMUM_PAGE_SIZE)
    search: str | None = None


class ApiErrorPayload(CamelCaseModel):
    """The error shape the frontend parses. Built from an `AerisError`, never assembled by hand at a route."""

    message: str
    code: str
    status: int
    details: dict[str, Any] | None = None

    @classmethod
    def from_error(cls, error: AerisError) -> Self:
        """The one conversion from a raised failure to a response body."""
        return cls.model_validate(to_error_payload(error))
