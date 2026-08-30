"""The declarative base every table inherits, plus the two column patterns that repeat on all of them.

what  : `Base` (the SQLAlchemy 2.0 `DeclarativeBase` Alembic autogenerates from), `TimestampMixin`,
        `identifier_column()` which builds a prefixed-ULID primary key, and `wire_enum()` which stores a
        shared vocabulary as the value the frontend expects.
where : Inherited by every module in `app/db/models/`. Alembic's `env.py` imports `Base.metadata` and
        nothing else, so a model file that is never imported is invisible to migrations - which is why
        `app/db/models/__init__.py` imports all of them.
how   : `type_annotation_map` is what lets the model files stay readable: `Mapped[datetime]` becomes
        `TIMESTAMP WITH TIME ZONE` and `Mapped[dict]` becomes `JSONB` without either being spelled out on
        every column.

        **Timestamps are timezone-aware, always.** A naive `TIMESTAMP` column is the bug that turns a
        Sentinel-2 acquisition time into a value an hour off in one deployment and correct in another, and
        acquisition time is the axis the temporal comparator is built on.

        **`updated_at` is maintained by the database, not by Python.** `onupdate` on the column means a row
        written by a migration, a repository or a psql session all get the same treatment; a service that
        remembered to set it would eventually be a service that forgot.

        Naming convention is set explicitly. Without it, Postgres names constraints and Alembic
        autogenerates anonymous `ALTER TABLE ... DROP CONSTRAINT` statements it cannot resolve on the way
        back down, which makes a downgrade fail on exactly the migration you most want to reverse.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, MetaData, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.identifiers import IDENTIFIER_MAXIMUM_LENGTH, IdentifierPrefix, new_identifier

# Deterministic, readable constraint names. `ix_scenes_captured_at` rather than a generated string, so a
# migration diff is reviewable and a downgrade can name what it is dropping.
CONSTRAINT_NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """The declarative base. Persistence shape only - no business logic lives on a model."""

    metadata = MetaData(naming_convention=CONSTRAINT_NAMING_CONVENTION)

    type_annotation_map = {
        # Timezone-aware everywhere. See the module docstring.
        datetime: DateTime(timezone=True),
        # JSONB rather than JSON: it is indexable and it round-trips without re-parsing. Used for the
        # structures the frontend receives verbatim - claim metrics, camera bookmarks, id lists.
        dict[str, Any]: JSONB,
        # Two list shapes, both JSONB. `list[str]` is an id list - evidence ids on a claim, source scene ids
        # on evidence. `list[dict[str, Any]]` is a list of objects the frontend owns the shape of, such as a
        # claim's metrics. Both are spelled out because SQLAlchemy resolves the annotation exactly: a bare
        # `dict` or `list` does not match either key and fails at class definition, which is the behaviour we
        # want - it forces the column's real shape to be stated.
        list[str]: JSONB,
        list[dict[str, Any]]: JSONB,
    }


def identifier_column(prefix: IdentifierPrefix) -> Mapped[str]:
    """A primary key column that defaults to a fresh prefixed ULID for `prefix`.

    The default is applied in Python rather than by the database so that a caller holds the id *before* the
    insert. A run emits `run-start` naming its own id, and evidence rows reference a claim id, both before
    anything is flushed.
    """
    return mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        primary_key=True,
        default=lambda: new_identifier(prefix),
    )


def wire_enum(enum_type: type[StrEnum]) -> Enum:
    """A column type for a `StrEnum` from `app/constants/`, stored as its **value**.

    Two decisions here, both of which are bugs if made the other way.

    **`values_callable`.** SQLAlchemy stores an enum member's `.name` by default, so `EvidenceKind` would
    land in the database as `CHANGE_MASK` while the frontend's Zod expects `change-mask`. Every one of these
    vocabularies is shared with the frontend (`code-standards.md` §5), so the value is the only thing worth
    persisting.

    **`native_enum=False`.** A `VARCHAR` with a `CHECK` constraint rather than a Postgres `ENUM` type.
    Postgres enums cannot have a value removed and can only have one appended, so every future change to a
    shared vocabulary would be a type migration rather than a constraint one - and these vocabularies change
    whenever the frontend's do.
    """
    return Enum(
        enum_type,
        native_enum=False,
        values_callable=lambda members: [member.value for member in members],
        length=64,
        create_constraint=True,
        validate_strings=True,
    )


class TimestampMixin:
    """`created_at` and `updated_at`, both server-side, on every table that has a lifecycle."""

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
