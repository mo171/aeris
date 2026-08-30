"""The one async engine, the session every repository borrows, and the probe that proves PostGIS is really there.

what  : `get_engine()`, `get_session()` (an async context manager yielding an `AsyncSession`), `check_health()`
        which returns what `aeris doctor` prints, and `dispose_engine()` for shutdown.
where : The only module that constructs a database connection. Repositories take a session; services call
        repositories. **Nothing outside this file imports `create_async_engine` or `AsyncSession`** - a
        second engine means a second pool, and two pools against Supabase's connection limit is a production
        outage that looks like intermittent timeouts.
how   : The engine is created once, lazily, on first use rather than at import. Import-time construction
        would open sockets during `pytest --collect-only` and during `aeris --help`, and would make
        `app.lib.database` unimportable on a machine with no database - which is exactly the machine
        `aeris doctor` is meant to diagnose.

        **`check_health()` asks whether PostGIS is installed, not just whether Postgres answers.** Compose's
        `pg_isready` already covers "the socket accepts connections"; the failure this backend actually hits
        is a reachable Postgres *without* the extension, where every geometry column fails at migration time
        with an error that names a missing type rather than a missing extension. Reporting the PostGIS
        version turns that into one line in `aeris doctor`.

        `expire_on_commit=False` so that objects stay readable after the transaction closes. Without it,
        returning an ORM object from a service triggers a lazy refresh on first attribute access, outside the
        session that could serve it - which under asyncio raises `MissingGreenlet` rather than reloading.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import perf_counter

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import BACKEND_ROOT_DIRECTORY, settings
from app.lib.exceptions import UpstreamUnavailableError

# Module-level singletons, built on first use. Not thread-local: one event loop owns them.
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    """What `aeris doctor` prints for the database row."""

    is_reachable: bool
    postgres_version: str | None
    postgis_version: str | None
    latency_ms: float | None
    # Populated only when `is_reachable` is False, and phrased for someone deciding what to do next.
    failure_reason: str | None


async def get_engine() -> AsyncEngine:
    """Return the process-wide engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            str(settings.database_url),
            echo=settings.database_echo_sql,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            # Recycle below the shortest idle timeout upstream of us. Supabase's pooler drops idle
            # connections, and a pooled connection that was closed at the far end surfaces as a
            # `ConnectionDoesNotExist` on a query that has nothing to do with the cause.
            pool_recycle=1800,
            # Cheap liveness check on checkout. One round trip against debugging a stale connection.
            pool_pre_ping=True,
            connect_args={"timeout": settings.database_connect_timeout_seconds},
        )
    return _engine


async def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory, creating it on first call."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=await get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """One unit of work. Commits on clean exit, rolls back on any exception.

    The transaction boundary is here rather than in each repository so that a service performing several
    writes gets one transaction, not several. A repository that commits on its own makes a half-applied
    multi-step operation possible, and a run that wrote its evidence but not its claims is worse than one
    that wrote neither.
    """
    factory = await get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_health() -> DatabaseHealth:
    """Probe the database. Never raises - this is what `aeris doctor` calls to report a failure.

    Returns a `DatabaseHealth` in every case, because a diagnostic command that crashes when the thing it
    diagnoses is down is useless exactly when it is needed.
    """
    started_at = perf_counter()
    try:
        engine = await get_engine()
        async with engine.connect() as connection:
            postgres_version = (await connection.execute(text("SELECT version()"))).scalar_one()
            # `PostGIS_Full_Version()` would also report the linked GEOS and PROJ builds, which is more than
            # a doctor row can show. The short version answers the question that matters: is the extension
            # installed in *this database*, which is per-database rather than per-server.
            postgis_version = (
                await connection.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'"))
            ).scalar_one_or_none()
        latency_ms = (perf_counter() - started_at) * 1000

        return DatabaseHealth(
            is_reachable=True,
            postgres_version=postgres_version,
            postgis_version=postgis_version,
            latency_ms=round(latency_ms, 2),
            failure_reason=(
                None
                if postgis_version is not None
                else "Postgres is reachable but the PostGIS extension is not installed in this database. "
                "Run `CREATE EXTENSION postgis;`, or apply the first Alembic migration, which does it."
            ),
        )
    except Exception as error:
        return DatabaseHealth(
            is_reachable=False,
            postgres_version=None,
            postgis_version=None,
            latency_ms=None,
            failure_reason=f"{type(error).__name__}: {error}",
        )


async def require_healthy_database() -> None:
    """Raise `UpstreamUnavailableError` unless the database is reachable with PostGIS present.

    Used at the start of a pipeline run rather than at process start. Failing here means a run refuses
    immediately with `UPSTREAM_UNAVAILABLE`, which the frontend can branch on, instead of
    failing at stage S15 once the expensive work has already been paid for.
    """
    health = await check_health()
    if not health.is_reachable or health.postgis_version is None:
        raise UpstreamUnavailableError(
            "The database is not available.",
            details={"upstream": "postgis", "reason": health.failure_reason},
        )



@dataclass(frozen=True, slots=True)
class SchemaVersion:
    """Whether the database's schema is the one this checkout expects.

    Separate from `DatabaseHealth` because it answers a different question. Health is "can we talk to it";
    this is "is what we are talking to the right shape". A fresh clone with `docker compose up` already run
    passes the first and fails the second, and that gap is the single most likely reason a first run breaks -
    which is exactly what `aeris doctor` exists to catch before the run rather than during it.
    """

    current_revision: str | None
    head_revision: str | None
    is_at_head: bool
    failure_reason: str | None


async def check_schema_version() -> SchemaVersion:
    """Compare the database's Alembic revision against the head in `migrations/`. Never raises.

    `None` for `current_revision` means the migrations have never been applied - not that something is
    broken - so the message says `alembic upgrade head` rather than reporting a fault.
    """
    try:
        script_directory = ScriptDirectory.from_config(AlembicConfig(BACKEND_ROOT_DIRECTORY / "alembic.ini"))
        head_revision = script_directory.get_current_head()
    except Exception as error:
        return SchemaVersion(
            current_revision=None,
            head_revision=None,
            is_at_head=False,
            failure_reason=f"Could not read the migration scripts: {type(error).__name__}: {error}",
        )

    try:
        engine = await get_engine()
        async with engine.connect() as connection:
            # Alembic's migration context is synchronous - it predates asyncio and takes a DBAPI-style
            # connection. `run_sync` hands it the underlying sync connection from inside the async one,
            # which is the supported bridge rather than a workaround.
            current_revision = await connection.run_sync(_read_current_revision)
    except Exception as error:
        return SchemaVersion(
            current_revision=None,
            head_revision=head_revision,
            is_at_head=False,
            failure_reason=f"Could not read the applied revision: {type(error).__name__}: {error}",
        )

    is_at_head = current_revision == head_revision

    return SchemaVersion(
        current_revision=current_revision,
        head_revision=head_revision,
        is_at_head=is_at_head,
        failure_reason=(
            None
            if is_at_head
            else (
                "The database has no schema yet. Run `uv run alembic upgrade head`."
                if current_revision is None
                else f"The database is at revision {current_revision!r} and this checkout expects "
                f"{head_revision!r}. Run `uv run alembic upgrade head`, or check out the code that matches "
                "the database."
            )
        ),
    )


def _read_current_revision(connection: Connection) -> str | None:
    """The revision stamped in `alembic_version`, or `None` if the table is absent.

    Sync because Alembic's `MigrationContext` is sync, and it is handed to `run_sync` - the `code-standards.md`
    §7 case of a callback a library calls for us. Declaring it `async def` would hand `run_sync` a coroutine
    object where it expects a value.
    """
    return MigrationContext.configure(connection).get_current_revision()


async def dispose_engine() -> None:
    """Close every pooled connection. Called on CLI exit and, in Phase 2, on application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
