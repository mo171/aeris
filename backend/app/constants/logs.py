"""The hardcoded parts of logging - field names, format strings, and the noise floor for third-party loggers.

what  : `JSON_LOG_FORMAT`, `JSON_FIELD_RENAMES`, `CONSOLE_LOG_FORMAT`, `THIRD_PARTY_LOG_LEVELS`.
where : Read only by `app/lib/logger.py`. Here rather than there because these are hardcoded lists, and a
        hardcoded list lives in `constants/` - the level at which the scientific stack is allowed to talk is a
        value someone will want to change without reading the logging setup.
how   : `JSON_FIELD_RENAMES` turns the standard library's `levelname` and `name` into `level` and `logger`,
        because a log line is read by whoever is filtering it at three in the morning.

        `THIRD_PARTY_LOG_LEVELS` is the noise floor. With `LOG_LEVEL=DEBUG` set locally - which is the point of
        local - matplotlib's font manager and rasterio's GDAL bridge emit thousands of lines per run and bury
        our own trace. Each entry here is a library that has actually been observed drowning a run, not a
        precaution.
"""

from typing import Final

# The standard library attributes to promote into the JSON object. Anything passed as `extra=` is merged in
# automatically, which is how `run_id` and `stage` reach the log line.
JSON_LOG_FORMAT: Final[str] = "%(levelname)s %(name)s %(message)s"

JSON_FIELD_RENAMES: Final[dict[str, str]] = {
    "levelname": "level",
    "name": "logger",
}

# Only ever used when `LOG_FORMAT=console`, which is a human watching a terminal. rich supplies the level,
# timestamp and source location columns, so the format string is the message alone.
CONSOLE_LOG_FORMAT: Final[str] = "%(message)s"

THIRD_PARTY_LOG_LEVELS: Final[dict[str, str]] = {
    "matplotlib": "WARNING",
    "matplotlib.font_manager": "WARNING",
    "PIL": "INFO",
    "rasterio": "INFO",
    "rasterio._env": "WARNING",
    "fiona": "INFO",
    "urllib3": "WARNING",
    "asyncio": "INFO",
    # Added in Phase 0.6, and measured rather than assumed: the first run of `aeris doctor` with
    # LOG_LEVEL=DEBUG produced **142 KB** of botocore hook-registration chatter above a table that is
    # twenty lines long. botocore logs its entire event-name remapping at DEBUG on client construction.
    "botocore": "WARNING",
    "boto3": "WARNING",
    "aiobotocore": "WARNING",
    "s3transfer": "WARNING",
    # The Inngest SDK's transport, and aiohttp's. Both log a line per request at DEBUG, which turns a
    # health probe into a paragraph.
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "aiohttp": "WARNING",
    # Ours to hear from - it reports real send failures - but not at DEBUG, where it narrates every retry.
    "inngest": "INFO",
    # The Inngest SDK logs through a logger we hand it (`app/lib/inngest.py`), so the entry above does not
    # reach it. This is that injected child logger, kept separate so the SDK's chatter can be silenced
    # without also silencing our own messages about Inngest.
    "app.lib.inngest.sdk": "INFO",
    # redis-py narrates protocol negotiation at DEBUG - including a `MAINT_NOTIFICATIONS` probe that fails
    # by design against any server older than its newest feature.
    "redis": "INFO",
    # Alembic announces its migration context at INFO on every schema check, which `aeris doctor` performs
    # on every run.
    "alembic": "WARNING",
}
