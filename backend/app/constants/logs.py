"""The hardcoded parts of logging - field names, format strings, and the noise floor for third-party loggers.

what  : `JSON_LOG_FORMAT`, `JSON_FIELD_RENAMES`, `CONSOLE_LOG_FORMAT`, `THIRD_PARTY_LOG_LEVELS`.
where : Read only by `app/lib/logger.py`. Here rather than there because these are hardcoded lists, and a
        hardcoded list lives in `constants/` - the level at which the scientific stack is allowed to talk is a
        value someone will want to change without reading the logging setup.
how   : `JSON_FIELD_RENAMES` turns the standard library's `levelname` and `name` into `level` and `logger`,
        because a log line is read by whoever is filtering it at three in the morning.

        `THIRD_PARTY_LOG_FLOOR` is the design that matters here, and it replaced a hand-maintained list.

        The original `THIRD_PARTY_LOG_LEVELS` was a deny-list: name a noisy library, pin its level. It
        **failed open** - a library nobody had listed yet was as loud as `LOG_LEVEL` allowed. That was not a
        theory. It had to be extended in Phase 0.6 (botocore: 142 KB above a twenty-line table), in 1.0
        (aiosqlite: 76 KB for a four-row trace) and again in 1.1 (pystac-client printing every request
        header). Three phases, three floods, each found by a human reading unreadable output.

        So the rule is inverted: **everything that is not ours sits at `WARNING` unless it is named below.**
        A new dependency is quiet on the day it is added, and the list is now the small set of libraries we
        deliberately want to hear *more* from - an allow-list, not a deny-list.
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

# Everything not under `app.` is held here unless named below. A floor, not a suggestion:
# `app/lib/logger.py` applies it to the root logger and raises only our own tree to `LOG_LEVEL`.
THIRD_PARTY_LOG_FLOOR: Final[str] = "WARNING"

# The logger our own code lives under - every module calls `logging.getLogger(__name__)`, and every module
# is under `app.`. Raised to `LOG_LEVEL`; everything else stays at the floor.
APPLICATION_LOGGER_NAME: Final[str] = "app"

# Libraries we deliberately want to hear MORE from than the floor allows, each with the reason. Adding a
# dependency requires no entry here; one that is genuinely worth hearing from gets one.
THIRD_PARTY_LOG_LEVELS: Final[dict[str, str]] = {
    # Reports real event-send failures, which are ours to act on.
    "inngest": "INFO",
    # The Inngest SDK logs through a logger we hand it (`app/lib/inngest.py`), so the entry above does not
    # reach it. Kept separate so the SDK's chatter can be silenced without silencing our own Inngest lines.
    "app.lib.inngest.sdk": "INFO",
    # GDAL's warnings arrive through these, and a complaint about a malformed GeoTIFF is something Phase
    # 1.2 onwards genuinely needs to see rather than discover as a wrong number.
    "rasterio": "INFO",
    "fiona": "INFO",
    "PIL": "INFO",
    # LangGraph and LangChain narrate every superstep at DEBUG; INFO is where they say something useful.
    "langgraph": "INFO",
    "langchain_core": "INFO",
}