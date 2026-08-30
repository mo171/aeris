"""Pins the two properties every identifier in the system depends on: it is typed, and it sorts by time.

what  : Tests for `app/db/identifiers.py` and for the enum-storage decision in `app/db/models/base.py`.
where : Pure unit tests - no database, no event loop. Sync `def`, because there is nothing to await
        (`code-standards.md` §7).
how   : These test *properties* rather than current output. Asserting that `new_identifier` returns some
        string would pass forever and prove nothing; asserting that ids generated in order compare in order
        is the actual contract cursor pagination is built on.
"""

from app.constants.evidence import EvidenceKind
from app.constants.scenes import SceneModality
from app.db.identifiers import (
    IDENTIFIER_MAXIMUM_LENGTH,
    IdentifierPrefix,
    new_identifier,
    prefix_of,
)
from app.db.models.base import wire_enum


def test_identifier_carries_its_type_prefix() -> None:
    identifier = new_identifier(IdentifierPrefix.SCENE)
    assert identifier.startswith("scn_")
    assert prefix_of(identifier) is IdentifierPrefix.SCENE


def test_identifiers_sort_in_creation_order() -> None:
    """The property cursor pagination relies on: lexical order is chronological order.

    ULIDs share a millisecond timestamp prefix, so ids created inside the same millisecond are ordered by
    their random tail rather than by time. Sorting a batch and comparing against creation order would
    therefore be flaky. What is actually guaranteed - and what pagination needs - is that an id created
    later never sorts *before* one created earlier, which is what this asserts.
    """
    identifiers = [new_identifier(IdentifierPrefix.RUN) for _ in range(200)]
    timestamp_prefixes = [identifier.split("_")[1][:10] for identifier in identifiers]
    assert timestamp_prefixes == sorted(timestamp_prefixes)


def test_identifiers_are_unique() -> None:
    identifiers = {new_identifier(IdentifierPrefix.CLAIM) for _ in range(10_000)}
    assert len(identifiers) == 10_000


def test_every_prefix_fits_the_column() -> None:
    """`IDENTIFIER_MAXIMUM_LENGTH` is the VARCHAR width of every primary key. A longer id would truncate."""
    for prefix in IdentifierPrefix:
        assert len(new_identifier(prefix)) <= IDENTIFIER_MAXIMUM_LENGTH


def test_prefix_of_rejects_rather_than_raises() -> None:
    """Callers use this to decide whether an id is the right *kind*, so a bad id is a value, not an error."""
    assert prefix_of("not-an-identifier") is None
    assert prefix_of("xyz_01JABCDEFGHJKMNPQRSTVWXYZ") is None
    assert prefix_of("") is None


def test_wire_enum_stores_values_not_member_names() -> None:
    """The bug this guards against is silent and reaches the frontend.

    SQLAlchemy's `Enum` persists an enum member's `.name` by default, so `EvidenceKind.CHANGE_MASK` would be
    written as `CHANGE_MASK` while the frontend's Zod expects `change-mask`. Every one of these vocabularies
    is shared with the frontend, so the value is the only correct thing to store.
    """
    column_type = wire_enum(EvidenceKind)
    assert set(column_type.enums) == {kind.value for kind in EvidenceKind}
    assert "change-mask" in column_type.enums
    assert "CHANGE_MASK" not in column_type.enums


def test_wire_enum_is_a_check_constraint_not_a_postgres_type() -> None:
    """`native_enum=False` keeps a shared vocabulary changeable.

    A Postgres `ENUM` type cannot have a value removed and can only append, so every change the frontend
    makes to one of these vocabularies would become a type migration instead of a constraint one.
    """
    column_type = wire_enum(SceneModality)
    assert column_type.native_enum is False
    assert column_type.create_constraint is True
