"""Every primary key in this system: a short type prefix followed by a ULID.

what  : `IdentifierPrefix`, the `new_identifier()` generator, and `prefix_of()` for reading one back.
where : The default for every `id` column in `app/db/models/`, and the ids that appear on the wire -
        `api-contract.md` already shows `run_01J...` and `clm_01J...` in its event examples.
how   : **ULID, not UUID4, and not a bigint sequence.**

        A ULID's first 48 bits are a millisecond timestamp, so ids sort in creation order. That matters
        twice here. A B-tree index on a random UUID4 primary key writes into a different leaf page on every
        insert, which is the well-known index-fragmentation cost; a ULID appends. And cursor pagination -
        mandatory for the imagery catalogue (`api-contract.md` §1 rule 5) - needs a total order that is
        stable under concurrent inserts, which is exactly what a time-ordered id gives without a second
        sort column.

        A bigint sequence would also sort, but it leaks how many scenes exist, cannot be generated before
        the row is written, and collides when two environments' data are ever merged.

        **The prefix is the point.** `scn_01J...` in a log, a stack trace or an operator's bug report is
        self-describing; a bare ULID is not. It also turns a whole class of bug into an immediate failure:
        passing a run id where a scene id was expected is visible on sight and assertable in a test, rather
        than becoming an empty query result three layers down.

        Ids are strings, not a custom SQLAlchemy type. The prefix means they are not valid UUIDs, so a
        native `uuid` column is unavailable anyway, and a `VARCHAR(32)` with a B-tree index is the correct
        shape for a value this size.
"""

from enum import StrEnum
from typing import Final

from ulid import ULID


class IdentifierPrefix(StrEnum):
    """The type tag that opens every identifier. One per persisted entity."""

    SCENE = "scn"
    INVESTIGATION = "inv"
    RUN = "run"
    TRACE_STEP = "stp"
    EVIDENCE = "ev"
    CLAIM = "clm"
    MISSION = "msn"

    # Not persisted as tables yet, and listed because the wire already names them: a layer id and a figure
    # id appear in `layer-ready` and `figure-ready` events, and an utterance id in `speech`. Declaring them
    # here keeps one vocabulary rather than letting each producer invent a prefix.
    LAYER = "lyr"
    FIGURE = "fig"
    REPORT = "rpt"
    UTTERANCE = "utt"
    PLAN = "pln"


IDENTIFIER_SEPARATOR: Final[str] = "_"

# `scn` + `_` + 26 ULID characters = 30. The longest prefix here is three characters, so 32 leaves room
# without being a round number chosen by guesswork.
IDENTIFIER_MAXIMUM_LENGTH: Final[int] = 32


def new_identifier(prefix: IdentifierPrefix) -> str:
    """Generate a fresh, time-ordered identifier for one entity.

    Sync, and deliberately so (code-standards.md §7): it does no I/O now and cannot plausibly do any later -
    a ULID is generated from the clock and a random source, both in process. It is also called from inside
    SQLAlchemy column defaults, which are sync callables.
    """
    return f"{prefix.value}{IDENTIFIER_SEPARATOR}{ULID()}"


def prefix_of(identifier: str) -> IdentifierPrefix | None:
    """Read the type tag back off an identifier, or `None` if it does not carry a known one.

    Returns `None` rather than raising because the common caller is a validator deciding whether an id is
    the right *kind*, and a wrong kind is a `VALIDATION_FAILED` with a useful message rather than an
    exception from a parsing helper.
    """
    tag, separator, _ = identifier.partition(IDENTIFIER_SEPARATOR)
    if not separator:
        return None
    try:
        return IdentifierPrefix(tag)
    except ValueError:
        return None
