"""Typed failures, each carrying the stable code and HTTP status the wire contract requires.

what  : `AerisError` and the small set of subclasses the whole backend raises, plus `to_error_payload()`
        which renders one into the `{message, code, status, details}` shape the frontend parses.
where : Raised anywhere. Caught at the edges - a FastAPI exception handler in Phase 2, the CLI's top-level
        handler in Phase 1 - which is the only place allowed to turn one into a response or an exit code.
how   : Every failure that reaches the operator is one of these. A bare `ValueError` crossing the boundary
        becomes an untyped 500 with our internals in the message, so the rule is: raise an `AerisError` at the
        point where you know what went wrong, because that is the only place that knows.

        `code` and `status` are class attributes, not constructor arguments. If a call site could choose them,
        the same condition would eventually be reported two different ways, and the frontend branches on `code`
        (`constants/errors.py`).

        `details` is structured context - which scene, which stage, which bounding box. It is for a human
        reading a log or an error card, and it is never parsed for control flow, which is what `code` is for.

        `to_error_payload` is a plain function, not a coroutine, and it is the deliberate exception to
        code-standards.md §7: it maps fields that are already in memory, performs no I/O, and is called from
        exception handlers and log formatting paths where introducing an await would be a liability rather than
        a uniformity.
"""

from typing import Any

from app.constants.errors import ErrorCode


class AerisError(Exception):
    """Base class for every failure this backend reports deliberately."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    status: int = 500

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ConfigurationError(AerisError):
    """A value the process needs is missing or malformed. Raised at startup, never mid-request."""

    code = ErrorCode.CONFIGURATION_INVALID
    status = 500


class InvalidRequestError(AerisError):
    """The request was understood and is wrong.

    Named `InvalidRequestError` rather than `ValidationError` on purpose: Pydantic already owns that name,
    and an `except ValidationError` that catches the wrong one of the two is a bug that reads as correct.
    """

    code = ErrorCode.VALIDATION_FAILED
    status = 400


class ResourceNotFoundError(AerisError):
    """The addressed scene, investigation, run, figure or mission does not exist."""

    code = ErrorCode.RESOURCE_NOT_FOUND
    status = 404


class ConflictError(AerisError):
    """The request is valid but the current state forbids it."""

    code = ErrorCode.CONFLICT
    status = 409


class UpstreamUnavailableError(AerisError):
    """A dependency we do not own failed: the STAC catalogue, the tiler, storage, a model server.

    The one error class where a retry is sensible, which is why it is distinct from `InternalError`. Carry the
    upstream's name in `details` so the failure can be attributed without reading our logs.
    """

    code = ErrorCode.UPSTREAM_UNAVAILABLE
    status = 503


class RunCancelledError(AerisError):
    """The operator stopped the run, including by barge-in.

    499 is nginx's "client closed request" and is the honest status here: nothing failed. The run status the
    frontend renders is `cancelled`, not `failed`, so an intentional interruption is never shown as an
    incident to investigate.
    """

    code = ErrorCode.RUN_CANCELLED
    status = 499


class InternalError(AerisError):
    """Our bug. The message must be safe to show, because it will be shown."""

    code = ErrorCode.INTERNAL_ERROR
    status = 500


def to_error_payload(error: AerisError) -> dict[str, Any]:
    """Render an error into the `ApiErrorPayload` shape - `{message, code, status, details}`.

    Already camelCase, because all four field names are single words. `details` is omitted when empty rather
    than sent as `null`, so an error card never renders an empty context block.
    """
    payload: dict[str, Any] = {
        "message": error.message,
        "code": error.code.value,
        "status": error.status,
    }
    if error.details:
        payload["details"] = error.details
    return payload
