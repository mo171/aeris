"""The Phase 0.6 gate: `aeris doctor` reports every dependency, exits with a code a script can trust, and never prints a credential.

what  : Tests for `app/cli/doctor.py` and the `aeris` console script. The report's content and health logic
        are tested in-process; the exit code and the masking are tested by running the real command.
where : `tests/integration/`. Marked `integration` - `collect_report()` probes live infrastructure, which is
        the point of it.
how   : **The exit code is tested in a subprocess, and that is deliberate.** A CLI's contract is what the
        process does: what it prints, and what it exits with. Calling the command function in-process would
        test neither - Typer's `Exit` would be caught by the test rather than becoming a status, and the
        console script entry point in `pyproject.toml` would never be exercised. It also sidesteps a real
        conflict: `main.py` calls `asyncio.run()`, which raises inside the already-running loop these async
        tests use.

        There is a second reason, and it is this session's recurring bug. Twice now a pipe has eaten an exit
        code and made a failing command look like a passing one (`alembic … | tail` in 0.2,
        `docker exec … | head` in 0.5). `subprocess.run(...).returncode` is the one form that cannot be
        misread.

        The credential test runs the command with distinctive passwords in every credential-bearing setting
        and asserts that none of them appears in the output. Written that way rather than as a list of fields
        to check, so that **a future setting carrying a credential fails this test without anyone having to
        remember to add it** - which is the mistake `MASKED_URL_PROPERTIES` exists to survive.
"""

import os
import shutil
import subprocess

import pytest

from app.cli.doctor import MASKED_VALUE, collect_report
from app.lib import redis as aeris_redis

pytestmark = pytest.mark.integration

# Every dependency Phase 0 provisioned. Named here so that adding a service without adding its row fails.
EXPECTED_ROWS = (
    "PostgreSQL + PostGIS",
    "Database schema",
    "Redis",
    "Object storage",
    "Storage CORS",
    "Inngest",
)

# Distinctive enough that finding one in the output is unambiguous, and not a substring of anything else.
CREDENTIAL_PROBES = {
    "DATABASE_URL": ("postgresql+asyncpg://aeris:CANARYDBPASSWORD@127.0.0.1:5433/aeris", "CANARYDBPASSWORD"),
    "REDIS_URL": ("redis://:CANARYREDISPASSWORD@127.0.0.1:6379/0", "CANARYREDISPASSWORD"),
    "STORAGE_SECRET_KEY": ("CANARYSTORAGESECRET", "CANARYSTORAGESECRET"),
    "STORAGE_ACCESS_KEY": ("CANARYSTORAGEACCESS", "CANARYSTORAGEACCESS"),
    "INNGEST_SIGNING_KEY": ("CANARYSIGNINGKEY", "CANARYSIGNINGKEY"),
    "INNGEST_EVENT_KEY": ("CANARYEVENTKEY", "CANARYEVENTKEY"),
}


def run_doctor(extra_environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the real `aeris doctor`, as a shell script or CI would.

    Sync, and one of the few sync functions in the suite: it is a subprocess boundary, and wrapping
    `subprocess.run` in a thread to satisfy a convention would add a moving part to the one test whose value
    is that it has none.
    """
    executable = shutil.which("aeris")
    assert executable is not None, (
        "The `aeris` console script is not on PATH. It is declared in pyproject.toml under "
        "[project.scripts]; run `uv sync` to install it."
    )

    return subprocess.run(
        [executable, "doctor"],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, **(extra_environment or {})},
    )


async def test_every_phase_0_dependency_has_a_row() -> None:
    """A dependency with no row is a dependency nobody checks."""
    report = await collect_report()

    row_names = [row.name for row in report.rows]
    for expected in EXPECTED_ROWS:
        assert expected in row_names, f"no doctor row for {expected}"


async def test_the_report_is_healthy_when_the_stack_is_up() -> None:
    """The Phase 0 gate, in-process: everything green against a running `docker compose up`."""
    report = await collect_report()

    unhealthy = [(row.name, row.detail) for row in report.rows if not row.is_healthy]
    assert report.is_healthy, f"unhealthy rows: {unhealthy}"


async def test_the_default_run_proves_the_event_round_trip() -> None:
    """The write probe is on by default, because a setup verifier that half-checks is not one."""
    report = await collect_report()

    assert report.was_read_only is False
    assert "Inngest round trip" in [row.name for row in report.rows]


async def test_read_only_skips_the_probes_that_write() -> None:
    """`--read-only` must observe and nothing else - no buckets created, no event sent."""
    report = await collect_report(read_only=True)

    assert report.was_read_only is True
    assert "Inngest round trip" not in [row.name for row in report.rows]
    # Everything that only observes is still checked, so the flag narrows the report without gutting it.
    for expected in EXPECTED_ROWS:
        assert expected in [row.name for row in report.rows]


async def test_one_unhealthy_dependency_makes_the_whole_report_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`is_healthy` is what becomes the exit code, so a single failure has to reach it.

    A report that averaged its rows, or that reported healthy because most things worked, would let a broken
    setup pass the Phase 0 gate - which is the one thing this command exists to prevent.
    """

    async def unreachable_redis() -> aeris_redis.RedisHealth:
        return aeris_redis.RedisHealth(
            is_reachable=False,
            server_version=None,
            maxmemory_policy=None,
            maxmemory_bytes=None,
            latency_ms=None,
            failure_reason="ConnectionError: pretend Redis is down",
        )

    monkeypatch.setattr(aeris_redis, "check_health", unreachable_redis)
    report = await collect_report(read_only=True)

    assert report.is_healthy is False
    redis_row = next(row for row in report.rows if row.name == "Redis")
    assert redis_row.is_healthy is False
    assert redis_row.detail is not None and "pretend Redis is down" in redis_row.detail


async def test_a_reachable_redis_that_would_evict_a_lock_is_reported_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reachability is the least interesting thing that can be wrong.

    A Redis on `allkeys-lru` answers every ping and will still delete a lock a process is holding
    (`constants/redis_keys.py`). If `doctor` graded on reachability alone it would call that setup healthy,
    and the failure would arrive later as two models loading into 8 GB of VRAM.
    """

    async def evicting_redis() -> aeris_redis.RedisHealth:
        return aeris_redis.RedisHealth(
            is_reachable=True,
            server_version="8.2.9",
            maxmemory_policy="allkeys-lru",
            maxmemory_bytes=268_435_456,
            latency_ms=1.0,
            failure_reason="maxmemory-policy is 'allkeys-lru' and would evict a held lock",
        )

    monkeypatch.setattr(aeris_redis, "check_health", evicting_redis)
    report = await collect_report(read_only=True)

    assert report.is_healthy is False


async def test_the_configuration_block_lists_every_setting() -> None:
    """`aeris doctor` prints the config in force. A setting it omits is one nobody can verify."""
    from app.config import Settings

    report = await collect_report(read_only=True)

    assert {name for name, _ in report.configuration} == set(Settings.model_fields)


async def test_secrets_are_masked_in_the_report() -> None:
    """The in-process half of the masking check; the subprocess test below is the end-to-end one."""
    report = await collect_report(read_only=True)
    configuration = dict(report.configuration)

    assert configuration["inngest_event_key"] == MASKED_VALUE
    assert configuration["storage_secret_key"] == MASKED_VALUE
    assert "aeris_local_development@" not in configuration["database_url"]


# --- The command itself, in a subprocess -----------------------------------------------------------------


def test_the_command_exits_zero_when_the_stack_is_healthy() -> None:
    """**The gate.** `aeris doctor` is meant to be usable from a script, where `$?` is the whole answer."""
    result = run_doctor()

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "All dependencies are healthy." in result.stdout


def test_the_command_never_prints_a_credential() -> None:
    """Run it with a canary in every credential-bearing setting and look for any of them in the output.

    Deliberately not a list of fields to assert on. Written this way, a future setting that carries a
    credential and is not added to `MASKED_URL_PROPERTIES` fails here without anyone having to remember it -
    and forgetting is the entire failure mode, since the code works perfectly while printing the password.
    """
    environment = {name: value for name, (value, _) in CREDENTIAL_PROBES.items()}
    result = run_doctor(environment)

    output = result.stdout + result.stderr
    leaked = [canary for _, canary in CREDENTIAL_PROBES.values() if canary in output]

    assert not leaked, f"aeris doctor printed {leaked} in its output"
    # Proof the run actually happened and read those settings, rather than dying before it printed anything.
    assert "Configuration in force" in result.stdout


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/integration/test_doctor.py -v                          2026-08-31
#
#   collected 10 items
#
#   test_every_phase_0_dependency_has_a_row ...................................... PASSED [ 10%]
#   test_the_report_is_healthy_when_the_stack_is_up .............................. PASSED [ 20%]
#   test_the_default_run_proves_the_event_round_trip ............................. PASSED [ 30%]
#   test_read_only_skips_the_probes_that_write ................................... PASSED [ 40%]
#   test_one_unhealthy_dependency_makes_the_whole_report_unhealthy ............... PASSED [ 50%]
#   test_a_reachable_redis_that_would_evict_a_lock_is_reported_unhealthy ......... PASSED [ 60%]
#   test_the_configuration_block_lists_every_setting ............................. PASSED [ 70%]
#   test_secrets_are_masked_in_the_report ........................................ PASSED [ 80%]
#   test_the_command_exits_zero_when_the_stack_is_healthy ........................ PASSED [ 90%]
#   test_the_command_never_prints_a_credential ................................... PASSED [100%]
#
#   ======================= 10 passed in 14.53s =======================
#
# --- The Phase 0 gate ------------------------------------------------------------------------------------
#
# The gate is "`aeris doctor` green on a machine that has never run this project". Demonstrated without
# destroying the working environment, by pointing the command at a database that has never been migrated and
# a bucket prefix that has never existed:
#
#   $ export DATABASE_URL=...@127.0.0.1:5433/aeris_firstrun   # a database created empty
#   $ export STORAGE_BUCKET_PREFIX=firstrun                   # a prefix with no buckets
#
#   $ aeris doctor                                            EXIT 1
#     PostgreSQL + PostGIS  FAILED  PostgreSQL 17.5, no PostGIS
#     Database schema       FAILED  not migrated
#     Object storage        ok      5 buckets      <- provisioned from nothing by this run
#     2 of 7 checks failed: PostgreSQL + PostGIS, Database schema
#
#   $ uv run alembic upgrade head                             exit 0   (the remedy the table printed)
#
#   $ aeris doctor                                            EXIT 0
#     All dependencies are healthy.
#
# So a first run reports exactly two problems, names the command that fixes both, and creates the five
# buckets itself. The database and buckets created for this were dropped afterwards.
#
# Three consecutive `aeris doctor` runs exited 0, and three consecutive full-suite runs passed 63/63 - run
# repeatedly on purpose, because the bug this phase found was a race that passed three times before failing.
