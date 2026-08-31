"""Fixtures shared by the whole suite. Today: the mandatory environment a `Settings` can be built from.

what  : `mandatory_environment`, which sets every variable `Settings` requires and has no default for, and
        a session-scoped teardown that closes the infrastructure clients before the event loop goes.
where : Used by any test that constructs `Settings(_env_file=None)` - that is, any test about configuration
        rather than about a running system.
how   : `Settings` deliberately has required fields with no defaults, so that a clone with an incomplete
        `.env` fails at import naming the field (the Phase 0.1 gate). The cost of that is that every test
        building a `Settings` from scratch must supply them.

        Centralising it here matters for a reason beyond tidiness: **without it, a test that asserts
        `pytest.raises(ValidationError)` starts passing for the wrong reason** the moment a new required
        field is added. It would be catching the missing new field rather than the condition it was written
        to check, and it would keep passing even if that condition were deleted. Tests that expect a
        validation failure use this fixture and then break exactly one thing.
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from app.config import settings
from app.lib.database import dispose_engine
from app.lib.redis import close_client as close_redis_client
from app.lib.storage import close_client as close_storage_client

# Every field on `Settings` that is required and has no default. Adding one here is part of adding one there.
MANDATORY_ENVIRONMENT: dict[str, str] = {
    "INNGEST_EVENT_KEY": "test",
    "INNGEST_SIGNING_KEY": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "STORAGE_ENDPOINT_URL": "http://localhost:9000",
    "STORAGE_ACCESS_KEY": "test",
    "STORAGE_SECRET_KEY": "test",
}


@pytest.fixture
def mandatory_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set every required variable, so a test can then break exactly the one it is about."""
    for name, value in MANDATORY_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def unique_marker() -> str:
    """A value no other test or previous run uses, for asserting a payload survived a round trip."""
    return uuid4().hex


@pytest.fixture(scope="session", autouse=True)
async def close_infrastructure_connections_at_end_of_session() -> AsyncIterator[None]:
    """Close every pooled connection before the session's event loop closes.

    Without this the pooled asyncpg, redis-py and aiohttp connections are garbage-collected after the loop has gone,
    which prints a wall of `Event loop is closed` noise on an otherwise green run and can mask a real
    teardown error. aioboto3's client is an async context manager held open in an `AsyncExitStack`, so
    closing it is not optional tidiness - the stack has to be unwound on the loop that opened it. One fixture rather than one per client, because they share a single reason to exist and
    the list grows with every sub-phase that adds a dependency.
    """
    yield
    await dispose_engine()
    await close_redis_client()
    await close_storage_client()


@pytest.fixture
def isolated_pipeline_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the checkpointer, the memory store and the journal directory at a fresh temporary directory.

    Without this, every pipeline test shares `backend/data/checkpoints.sqlite` and `backend/runs/` with
    every other test *and with the developer's own runs*. Two costs, and the second is the one that bites:
    a test asserting "this thread has no checkpoint" passes until someone runs `aeris run` with a colliding
    id, and a test that counts journals is wrong the moment the directory is not empty.

    The three settings are patched rather than the properties that read them, because the properties also
    create the parent directories - which is behaviour the tests should exercise rather than bypass.
    """
    monkeypatch.setattr(settings, "pipeline_checkpoint_database_path", tmp_path / "checkpoints.sqlite")
    monkeypatch.setattr(settings, "pipeline_memory_database_path", tmp_path / "memory.sqlite")
    monkeypatch.setattr(settings, "pipeline_journal_directory", tmp_path / "runs")
    yield tmp_path


@pytest.fixture
def isolated_dataset_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the datasets root at an empty temporary directory.

    Without it, a dataset test reports whatever the developer happens to have downloaded - so a test
    asserting "absent" passes on CI and fails on the machine that actually has the data, which is the worst
    possible distribution of outcomes.
    """
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setattr(settings, "datasets_directory", root)
    return root
