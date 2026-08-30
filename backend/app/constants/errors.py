"""The stable error codes that cross the wire. Renaming one is a breaking change.

what  : `ErrorCode`, the `code` field of `ApiErrorPayload` (`{message, code, status, details}`).
where : Every typed exception in `app/lib/exceptions.py` declares one. Routes translate the exception into
        the payload without inventing anything.
how   : A code is for a machine, a message is for a person. The frontend branches on `code` - retry, prompt
        for re-authentication, show a specific empty state - so a code is part of the contract in the same way
        an endpoint path is, and the message beside it is free to be rewritten at any time.

        Codes are coarse on purpose. A code per failure site produces a vocabulary nobody can branch on;
        detail belongs in `details`, which is structured and never parsed for control flow.

        Not an error code: **insufficient evidence.** `api-contract.md` §1 rule 7 - a run that looked and
        could not establish an answer returns a successful response carrying a reason and remedies. Modelling
        it as an error would make honest uncertainty indistinguishable from a broken pipeline.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Why a request or a run failed, in the one word a client is allowed to branch on."""

    # The process is misconfigured. Raised at import by `config.py`, so it is normally seen in a log rather
    # than on the wire - a process this happens to should not be serving requests.
    CONFIGURATION_INVALID = "CONFIGURATION_INVALID"

    # The request was understood and is wrong: a malformed geometry, an unknown stage code, a date range
    # that runs backwards.
    VALIDATION_FAILED = "VALIDATION_FAILED"

    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"

    # The request is valid but the current state forbids it - confirming an upload that was never ticketed,
    # starting a run on an investigation that has no scenes.
    CONFLICT = "CONFLICT"

    # A dependency we do not own failed: the STAC catalogue, the tiler, object storage, a model server.
    # Separate from `INTERNAL_ERROR` because it is the one class of failure where retrying is sensible.
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"

    # The operator stopped the run, including by barge-in (`api-contract.md` §5). Deliberately not a failure:
    # an interruption on purpose must not be presented as something to investigate.
    RUN_CANCELLED = "RUN_CANCELLED"

    # Our bug. Nothing about it is actionable by the client, and the message must never leak a traceback.
    INTERNAL_ERROR = "INTERNAL_ERROR"
