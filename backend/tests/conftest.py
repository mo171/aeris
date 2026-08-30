"""Fixtures shared by the whole suite. Today: the mandatory environment a `Settings` can be built from.

what  : `mandatory_environment`, which sets every variable `Settings` requires and has no default for.
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

from collections.abc import AsyncIterator

import pytest

from app.lib.database import dispose_engine

# Every field on `Settings` that is required and has no default. Adding one here is part of adding one there.
MANDATORY_ENVIRONMENT: dict[str, str] = {
    "INNGEST_EVENT_KEY": "test",
    "INNGEST_SIGNING_KEY": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
}


@pytest.fixture
def mandatory_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set every required variable, so a test can then break exactly the one it is about."""
    for name, value in MANDATORY_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


@pytest.fixture(scope="session", autouse=True)
async def close_database_connections_at_end_of_session() -> AsyncIterator[None]:
    """Dispose the engine's pool before the session's event loop closes.

    Without this the pooled asyncpg connections are garbage-collected after the loop has gone, which prints
    a wall of `Event loop is closed` noise on an otherwise green run and can mask a real teardown error.
    """
    yield
    await dispose_engine()
