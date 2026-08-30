"""One command that answers "is this machine set up correctly", by asking every dependency rather than assuming any of them.

what  : `collect_report()`, which probes every Phase 0 dependency concurrently and returns a `DoctorReport`,
        and `render_report()`, which draws it as a table. `main.py` calls both and turns the report into an
        exit code.
where : `aeris doctor`. **This is the command the product owner runs to verify a setup** (`roadmap.md` 0.6),
        and the Phase 0 gate is this command printing green on a machine that has never run the project.
how   : The probing was written by sub-phases 0.2-0.5 and is not repeated here. Each dependency already
        returns a dataclass built for the row it becomes - `DatabaseHealth`, `SchemaVersion`, `RedisHealth`,
        `StorageHealth`, `CrossOriginAccess`, `InngestHealth`, `EventDeliveryProof` - and every one of them
        is documented never to raise. So this module maps and renders; it does not diagnose.

        **The probes run concurrently.** Serially, a machine with three things down costs three timeouts one
        after another, and the command people run when something is broken must not be slowest exactly then.

        **A row is not just "reachable".** Reachability is the least interesting thing that can be wrong. A
        Postgres with no schema, a Redis that will evict a held lock, storage with no buckets, an Inngest
        scanning for an app that does not exist - all four answer a ping perfectly. Every one of those is a
        row here, because each is a real first-run failure that a liveness check reports as healthy.

        **By default this command writes two things**, and both are idempotent: it creates any missing
        storage buckets, and it sends one health-probe event that has no consumer. That is deliberate - a
        setup verifier that reports a fixable problem and refuses to fix it makes the operator run a second
        command to finish the job. `--read-only` skips both for anyone who wants a pure observation.
"""

import asyncio
from dataclasses import dataclass

from pydantic import SecretStr
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from app.config import MASKED_URL_PROPERTIES, Settings, settings
from app.lib import database, inngest, redis, storage

# What a masked value prints as. Short, and obviously not a value that was truncated.
MASKED_VALUE = "***"


@dataclass(frozen=True, slots=True)
class DependencyRow:
    """One line of the table. `detail` is what to do next when `is_healthy` is False."""

    name: str
    is_healthy: bool
    version: str | None
    latency_ms: float | None
    detail: str | None


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Everything the command found. `is_healthy` is what becomes the process exit code."""

    rows: tuple[DependencyRow, ...]
    configuration: tuple[tuple[str, str], ...]
    was_read_only: bool

    @property
    def is_healthy(self) -> bool:
        """True only when every row is. A property rather than a coroutine for the `code-standards.md` §7
        reason: it reads fields already in memory and is called from the sync Typer callback that sets the
        exit code."""
        return all(row.is_healthy for row in self.rows)


async def collect_report(read_only: bool = False) -> DoctorReport:
    """Probe every dependency and return what to print. Never raises.

    `read_only` skips the two probes that write: creating missing buckets, and sending the Inngest
    health-probe event. Everything else is an observation.
    """
    if not read_only:
        # Before the storage health check, so that a first run reports five buckets present rather than five
        # missing and a remedy the operator then has to carry out by hand.
        await _provision_storage()

    (
        database_health,
        schema_version,
        redis_health,
        storage_health,
        cross_origin,
        inngest_health,
    ) = await asyncio.gather(
        database.check_health(),
        database.check_schema_version(),
        redis.check_health(),
        storage.check_health(),
        storage.check_cross_origin_access(),
        inngest.check_health(),
    )

    rows = [
        await _database_row(database_health),
        await _schema_row(schema_version),
        await _redis_row(redis_health),
        await _storage_row(storage_health),
        await _cross_origin_row(cross_origin),
        await _inngest_row(inngest_health),
    ]

    if not read_only:
        rows.append(await _event_delivery_row(await inngest.check_event_delivery()))

    return DoctorReport(
        rows=tuple(rows),
        configuration=await _masked_configuration(),
        was_read_only=read_only,
    )


async def _provision_storage() -> None:
    """Create any missing buckets. A failure here is reported by the storage row, not raised."""
    try:
        await storage.ensure_buckets()
    except Exception:
        # `check_health()` runs next and will report the buckets as missing with a remedy, which is a better
        # message than this exception. Swallowed rather than logged so the table is not preceded by a
        # traceback describing something the table is about to explain.
        return


# --- One mapper per dependency. Each turns a health dataclass into a row. --------------------------------


async def _database_row(health: database.DatabaseHealth) -> DependencyRow:
    return DependencyRow(
        name="PostgreSQL + PostGIS",
        # PostGIS present, not merely Postgres answering: every geometry column depends on the extension,
        # and its absence surfaces at migration time as an error naming a missing *type*.
        is_healthy=health.is_reachable and health.postgis_version is not None,
        # `SELECT version()` returns a whole banner - build host, compiler, distribution packaging. The first
        # two words are the answer; the rest is noise in a table row. When the extension is absent the row
        # says so in words rather than printing `PostGIS None`, because that reads as a rendering bug and
        # sends the reader looking in the wrong place.
        version=(
            None
            if health.postgres_version is None
            else (
                f"PostGIS {health.postgis_version} on {' '.join(health.postgres_version.split()[:2])}"
                if health.postgis_version is not None
                else f"{' '.join(health.postgres_version.split()[:2])}, no PostGIS"
            )
        ),
        latency_ms=health.latency_ms,
        detail=health.failure_reason,
    )


async def _schema_row(version: database.SchemaVersion) -> DependencyRow:
    return DependencyRow(
        name="Database schema",
        is_healthy=version.is_at_head,
        version=version.current_revision or "not migrated",
        latency_ms=None,
        detail=version.failure_reason,
    )


async def _redis_row(health: redis.RedisHealth) -> DependencyRow:
    return DependencyRow(
        name="Redis",
        # An unknown eviction policy is reported, not failed - several managed providers disable `CONFIG GET`,
        # and refusing on that would make the command red on every one of them.
        is_healthy=health.is_reachable
        and health.maxmemory_policy in {None, redis.REQUIRED_MAXMEMORY_POLICY},
        version=(
            None
            if health.server_version is None
            else f"{health.server_version} ({health.maxmemory_policy or 'policy unknown'})"
        ),
        latency_ms=health.latency_ms,
        detail=health.failure_reason,
    )


async def _storage_row(health: storage.StorageHealth) -> DependencyRow:
    return DependencyRow(
        name="Object storage",
        is_healthy=health.is_reachable and not health.missing_buckets,
        version=None if not health.is_reachable else f"{len(health.present_buckets)} buckets",
        latency_ms=health.latency_ms,
        detail=health.failure_reason,
    )


async def _cross_origin_row(access: storage.CrossOriginAccess) -> DependencyRow:
    return DependencyRow(
        name="Storage CORS",
        is_healthy=access.is_allowed,
        version=access.allowed_origin_header,
        latency_ms=None,
        # Named with the origin either way: "CORS is fine" means nothing without saying for whom.
        detail=access.failure_reason or f"allowed for {access.origin}",
    )


async def _inngest_row(health: inngest.InngestHealth) -> DependencyRow:
    return DependencyRow(
        name="Inngest",
        is_healthy=health.is_reachable and health.app_discovery_enabled is not True,
        version=health.server_version,
        latency_ms=health.latency_ms,
        detail=health.failure_reason or "no functions bound until Phase 2.5 (ADR-002)",
    )


async def _event_delivery_row(proof: inngest.EventDeliveryProof) -> DependencyRow:
    return DependencyRow(
        name="Inngest round trip",
        is_healthy=proof.was_read_back,
        version=proof.event_id or None,
        latency_ms=None,
        detail=proof.failure_reason or f"{proof.event_name} sent and read back",
    )


# --- Configuration, with every credential masked ---------------------------------------------------------


async def _masked_configuration() -> tuple[tuple[str, str], ...]:
    """Every setting in force, as `(name, value)`, with nothing printable that should not be printed.

    Two kinds of secret, and they are masked differently because they are declared differently. A
    `SecretStr` masks itself. A DSN cannot be one - SQLAlchemy and redis-py have to parse it - so it is
    rendered through the property named in `MASKED_URL_PROPERTIES`.
    """
    rendered: list[tuple[str, str]] = []

    for field_name in Settings.model_fields:
        value = getattr(settings, field_name)

        if isinstance(value, SecretStr):
            rendered.append((field_name, MASKED_VALUE))
        elif field_name in MASKED_URL_PROPERTIES:
            rendered.append((field_name, str(getattr(settings, MASKED_URL_PROPERTIES[field_name]))))
        else:
            rendered.append((field_name, str(value)))

    return tuple(rendered)


# --- Rendering -------------------------------------------------------------------------------------------


async def render_report(report: DoctorReport, console: Console) -> None:
    """Draw the report. Rich handles the table; this decides what goes in it."""
    # `overflow="fold"` on every value column. rich's default is to truncate with an ellipsis, which in a
    # diagnostic means the command silently hides the part of the value someone needed - a DSN's host, the
    # tail of an origin, the end of a remedy. Folding wraps instead, so nothing is lost at any width.
    dependency_table = Table(title="AERIS dependencies", title_justify="left", header_style="bold")
    dependency_table.add_column("Dependency", overflow="fold")
    dependency_table.add_column("Status")
    dependency_table.add_column("Version / detail", overflow="fold")
    dependency_table.add_column("Latency", justify="right")
    dependency_table.add_column("Notes", overflow="fold")

    for row in report.rows:
        # Every cell carrying a *value* is escaped. rich reads `[...]` as a style tag, so an unescaped
        # version string or failure message containing square brackets is silently altered or swallowed -
        # which in a command whose entire job is to report values accurately is a correctness bug, not a
        # cosmetic one. The status cell is the exception: its markup is ours and deliberate.
        dependency_table.add_row(
            escape(row.name),
            "[green]ok[/green]" if row.is_healthy else "[red]FAILED[/red]",
            escape(row.version or "-"),
            "-" if row.latency_ms is None else f"{row.latency_ms:.1f} ms",
            escape(row.detail or ""),
        )

    console.print(dependency_table)

    configuration_table = Table(
        title="Configuration in force (secrets masked)", title_justify="left", header_style="bold"
    )
    configuration_table.add_column("Setting", overflow="fold")
    configuration_table.add_column("Value", overflow="fold")
    for name, value in report.configuration:
        configuration_table.add_row(escape(name), escape(value))

    console.print(configuration_table)

    if report.was_read_only:
        console.print(
            "[yellow]--read-only:[/yellow] buckets were not provisioned and no Inngest event was sent."
        )

    if report.is_healthy:
        console.print("[bold green]All dependencies are healthy.[/bold green]")
    else:
        failed = [row.name for row in report.rows if not row.is_healthy]
        console.print(
            f"[bold red]{len(failed)} of {len(report.rows)} checks failed:[/bold red] "
            f"{escape(', '.join(failed))}"
        )
