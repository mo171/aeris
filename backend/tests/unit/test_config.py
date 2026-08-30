"""Proves the Phase 0.1 gate: a missing configuration variable fails at import time and names itself.

what  : Tests for `app.config.Settings` - required fields, secret masking, and value normalisation.
where : `tests/unit/`. No fixtures, no network, no filesystem beyond the repository's own `.env.example`.
how   : The gate in `roadmap.md` 0.1 is "importing `config` with a missing variable fails loudly and names it".
        That is only a guarantee if something checks it, because the failure mode it prevents - a process that
        starts happily and dies forty seconds into a run at stage S13 - is exactly the kind of regression a
        later refactor introduces by giving a field a convenient default.

        `_env_file=None` is what makes the test honest. The repository's own `.env` is fully populated, so
        without it these tests would pass by reading the file they are meant to be testing the absence of.
"""

import pytest
from pydantic import ValidationError

from app.config import BACKEND_ROOT_DIRECTORY, Settings, settings


async def test_missing_required_variable_raises_and_names_the_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of the gate: the error says which variable, so nobody has to guess."""
    monkeypatch.delenv("INNGEST_EVENT_KEY", raising=False)
    monkeypatch.delenv("INNGEST_SIGNING_KEY", raising=False)

    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None)

    message = str(raised.value).lower()
    assert "inngest_event_key" in message
    assert "inngest_signing_key" in message


async def test_secrets_are_masked_in_representation() -> None:
    """`aeris doctor` prints settings. A secret must not be printable by accident."""
    assert "local" not in repr(settings.inngest_event_key)
    assert "local" not in repr(settings.inngest_signing_key)
    # And still readable when genuinely needed.
    assert settings.inngest_event_key.get_secret_value() == "local"


async def test_log_level_is_normalised_to_upper_case(
    monkeypatch: pytest.MonkeyPatch,
    mandatory_environment: None,
) -> None:
    """A `.env` is typed by hand, so `info` and `INFO` must mean the same thing."""
    monkeypatch.setenv("LOG_LEVEL", "info")

    assert Settings(_env_file=None).log_level == "INFO"


async def test_invalid_enumerated_value_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    mandatory_environment: None,
) -> None:
    """`ENVIRONMENT=prod` is a typo, not a fourth environment. Fail rather than silently behave as local.

    The error is asserted to name `environment`. Without that, this test passes the moment any *other*
    required field is missing - it would be catching the wrong failure and would keep passing even if the
    `Literal` on `environment` were removed.
    """
    monkeypatch.setenv("ENVIRONMENT", "prod")

    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None)

    assert "environment" in str(raised.value).lower()


async def test_env_example_documents_every_configurable_field() -> None:
    """A field added to `Settings` and not to `.env.example` is an unreported requirement for whoever clones.

    Checked mechanically rather than by review, because this is precisely the file people forget.
    """
    example_text = (BACKEND_ROOT_DIRECTORY / ".env.example").read_text(encoding="utf-8")

    undocumented = [
        field_name.upper()
        for field_name in Settings.model_fields
        if f"{field_name.upper()}=" not in example_text
    ]
    assert not undocumented, f"missing from .env.example: {undocumented}"


async def test_database_url_must_use_the_async_driver(
    monkeypatch: pytest.MonkeyPatch,
    mandatory_environment: None,
) -> None:
    """A `postgresql://` DSN is valid to Pydantic and wrong for us.

    Supabase hands out exactly that form, so this is the mistake most likely to be made. SQLAlchemy would
    accept it and pick the blocking psycopg driver, which blocks the event loop on every query
    (`code-standards.md` §7) - a performance failure with no error message attached to it.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/aeris")

    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None)

    assert "asyncpg" in str(raised.value)


async def test_database_password_is_masked_for_reporting(
    monkeypatch: pytest.MonkeyPatch,
    mandatory_environment: None,
) -> None:
    """`aeris doctor` prints the DSN. The password must not survive that."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://aeris:hunter2@localhost:5432/aeris")

    masked = Settings(_env_file=None).database_url_without_password

    assert "hunter2" not in masked
    assert "aeris@localhost" in masked or "***" in masked
