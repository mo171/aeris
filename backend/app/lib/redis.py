"""The one Redis pool, the lock that protects the GPU, and the cache that is allowed to fail.

what  : `get_client()`, `held_lock()` (an async context manager over redis-py's own `Lock`), the four cache
        functions, `check_health()` for `aeris doctor`, `require_healthy_redis()` for the start of a run, and
        `close_client()` for shutdown.
where : The only module that opens a Redis connection or assembles a Redis key. Deliberately shaped like
        `app/lib/database.py` - same lazy singleton, same never-raising health probe, same `require_healthy_*`
        gate - so that provisioning the next dependency is a copy of a shape already understood rather than a
        new one to learn.
how   : **The two uses are separated because their failure policies are opposite, not because they need
        different storage.**

        A *cache* miss costs a recomputation, so every cache function swallows `RedisError` and behaves as a
        miss: a Redis outage must degrade AERIS, never stop it. A *lock* is mutual exclusion over the GPU's
        VRAM, so every lock function raises: a caller that carried on unlocked would load a second model into
        a card with room for one, and that surfaces several stages later as a CUDA out-of-memory error with
        nothing pointing back here.

        `asyncio.CancelledError` is caught nowhere in this module. It derives from `BaseException` rather
        than `Exception`, so `except RedisError` cannot absorb it - which is what barge-in needs
        (`product-truth.md` section 1.3): cancelling a run must not be swallowed by a cache read that
        happened to be in flight.

        **Locks are redis-py's `Lock`, not a hand-written recipe.** It already implements the correct one -
        `SET key token NX PX ttl`, released by a Lua script that compares the token before deleting - and the
        token comparison is the part that is easy to omit and expensive to omit: without it, a holder whose
        TTL has expired releases the *next* holder's lock instead of its own. `held_lock()` adds only the key
        prefix, the configured timeouts, and the rule that a failed acquisition raises.
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.lock import Lock
from redis.exceptions import LockError, LockNotOwnedError, RedisError

from app.config import settings
from app.constants.redis_keys import (
    KEY_PREFIX,
    KEY_SEPARATOR,
    NAMESPACE_SCAN_BATCH_SIZE,
    REQUIRED_MAXMEMORY_POLICY,
    KeyNamespace,
)
from app.lib.exceptions import ConflictError, UpstreamUnavailableError

logger = logging.getLogger(__name__)

# Module-level singleton, built on first use. One pool per process, for the same reason `database.py` holds
# one engine: two pools means twice the connections against a provider that counts them.
_client: Redis | None = None


@dataclass(frozen=True, slots=True)
class RedisHealth:
    """What `aeris doctor` prints for the Redis row."""

    is_reachable: bool
    server_version: str | None
    # `None` means the server refused to report it - several managed providers disable `CONFIG GET`. That is
    # not the same as a wrong policy, and the two must not be collapsed: one is unknown, the other is unsafe.
    maxmemory_policy: str | None
    maxmemory_bytes: int | None
    latency_ms: float | None
    # Populated whenever something needs attention, including when the server is reachable but configured in
    # a way that lets it evict a held lock. Phrased for someone deciding what to do next.
    failure_reason: str | None


async def get_client() -> Redis:
    """Return the process-wide client, creating it on first call."""
    global _client
    if _client is None:
        _client = Redis.from_url(
            str(settings.redis_url),
            # Values come back as `str`. Everything stored here is JSON text or a lock token, and redis-py's
            # `Lock` re-encodes its token itself, so decoding costs nothing and removes a `.decode()` from
            # every cache read.
            decode_responses=True,
            max_connections=settings.redis_max_connections,
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
            # Bounds a command that has been sent to a server which then stops answering. A blocking Redis
            # command - `BLPOP` and friends - would have to pass its own longer timeout; nothing here does,
            # because `held_lock` polls with `asyncio.sleep` rather than blocking inside the server.
            socket_timeout=settings.redis_connect_timeout_seconds,
            # Detects a connection the far end has dropped - a container restart, a managed provider's idle
            # timeout - on checkout rather than on the next command that needed it.
            health_check_interval=30,
        )
    return _client


async def _build_key(namespace: KeyNamespace, name: str) -> str:
    """`aeris:lock:<name>` or `aeris:cache:<name>`. The only place a Redis key is assembled."""
    return f"{KEY_PREFIX}{KEY_SEPARATOR}{namespace.value}{KEY_SEPARATOR}{name}"


# --- Cache. Every function here degrades rather than raises. ---------------------------------------------


async def cache_get(key: str) -> Any | None:
    """Read a cached value. `None` when it is absent, expired, or Redis is unavailable.

    Three situations collapse into one return value on purpose: the caller's response to all three is
    identical - compute the value - and distinguishing them would push a Redis outage into the branch logic
    of every call site.
    """
    try:
        client = await get_client()
        raw_value = await client.get(await _build_key(KeyNamespace.CACHE, key))
    except RedisError as error:
        logger.warning(
            "cache read failed; treating it as a miss",
            extra={"cache_key": key, "error": str(error)},
        )
        return None

    if raw_value is None:
        return None

    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        # Either something wrote a non-JSON value under our prefix, or a cached shape changed between
        # deployments. Discarding is safer than handing back a string the caller will mishandle, and it
        # self-heals on the next write.
        logger.warning("cached value was not valid JSON; discarding it", extra={"cache_key": key})
        await cache_delete(key)
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int | None = None) -> bool:
    """Write a cached value with a TTL. Returns whether it was actually stored.

    **Every cache entry expires.** `ttl_seconds` has a configured default rather than an "unset" option,
    because the server runs `maxmemory-policy noeviction` (`constants/redis_keys.py`): nothing here is
    evicted under memory pressure, so a key without a TTL is a permanent one, and enough of those fill the
    instance and start failing *lock* writes. The TTL on a cache entry is what stops the cache breaking the
    locks.
    """
    try:
        client = await get_client()
        await client.set(
            await _build_key(KeyNamespace.CACHE, key),
            json.dumps(value),
            ex=settings.redis_cache_default_ttl_seconds if ttl_seconds is None else ttl_seconds,
        )
        return True
    except RedisError as error:
        logger.warning("cache write failed", extra={"cache_key": key, "error": str(error)})
        return False
    except (TypeError, ValueError) as error:
        # A value that will not serialise is our bug, not an outage. Logged at ERROR so it is separable from
        # the line above - reported as a cache miss it would look like an infrastructure problem forever -
        # and still non-fatal, because a failed cache write must never fail the run that made it.
        logger.error(
            "cache value is not JSON-serialisable; nothing was stored",
            extra={"cache_key": key, "value_type": type(value).__name__, "error": str(error)},
        )
        return False


async def cache_delete(key: str) -> None:
    """Remove one cached value. A failure is logged and swallowed, like every other cache operation."""
    try:
        client = await get_client()
        await client.delete(await _build_key(KeyNamespace.CACHE, key))
    except RedisError as error:
        logger.warning("cache delete failed", extra={"cache_key": key, "error": str(error)})


async def clear_cache_namespace(name_prefix: str = "") -> int:
    """Delete every cache key under a prefix. Returns how many were removed.

    Uses `SCAN`, and never `FLUSHDB`. `FLUSHDB` would also delete every *lock*, freeing locks that live
    processes still believe they hold - the one outcome this keyspace layout exists to make impossible, and
    the reason the two namespaces can share a server at all. `SCAN` additionally avoids `KEYS`, which stalls
    the server for the length of the scan.
    """
    pattern = await _build_key(KeyNamespace.CACHE, f"{name_prefix}*")
    deleted_count = 0
    batch: list[str] = []
    try:
        client = await get_client()
        async for key in client.scan_iter(match=pattern, count=NAMESPACE_SCAN_BATCH_SIZE):
            batch.append(key)
            if len(batch) >= NAMESPACE_SCAN_BATCH_SIZE:
                deleted_count += await client.delete(*batch)
                batch.clear()
        if batch:
            deleted_count += await client.delete(*batch)
    except RedisError as error:
        logger.warning(
            "cache namespace clear failed part-way through",
            extra={"pattern": pattern, "deleted_count": deleted_count, "error": str(error)},
        )
    return deleted_count


# --- Locks. Every function here raises rather than degrades. ---------------------------------------------


@asynccontextmanager
async def held_lock(
    name: str,
    *,
    timeout_seconds: float | None = None,
    blocking_timeout_seconds: float | None = None,
) -> AsyncIterator[Lock]:
    """Hold a distributed lock for the duration of the block, or raise before entering it.

    Used as `async with held_lock(f"model:{model_id}"):` around a load into VRAM.

    **A fresh `Lock` object is constructed per acquisition, and that is the reason this is a context manager
    rather than a cached lock object.** redis-py keeps the acquisition token in `threading.local()`, and every
    coroutine on one event loop shares a thread - so two concurrent acquisitions through a *shared* `Lock`
    would share one token, and whichever released first would delete the other's key while it was still
    working. A per-call object makes that impossible.

    Two failures, deliberately distinguished:

    - Redis is unreachable, so we cannot know whether anyone holds it: `UpstreamUnavailableError`, which is
      the project's one retryable error class.
    - Redis answered and somebody else holds it: `ConflictError`. Nothing is broken; the resource is busy,
      and the caller may reasonably queue, refuse, or route elsewhere.

    Both are raised rather than returned, because the only alternative - carrying on unlocked - is the
    failure the lock exists to prevent.
    """
    key = await _build_key(KeyNamespace.LOCK, name)
    lock_timeout = settings.redis_lock_timeout_seconds if timeout_seconds is None else timeout_seconds
    wait_timeout = (
        settings.redis_lock_blocking_timeout_seconds
        if blocking_timeout_seconds is None
        else blocking_timeout_seconds
    )

    client = await get_client()
    lock = client.lock(key, timeout=lock_timeout, blocking=True, blocking_timeout=wait_timeout)

    try:
        was_acquired = await lock.acquire()
    except RedisError as error:
        raise UpstreamUnavailableError(
            "Could not reach Redis to take a lock.",
            details={"upstream": "redis", "lock": name, "reason": f"{type(error).__name__}: {error}"},
        ) from error

    if not was_acquired:
        raise ConflictError(
            f"The lock {name!r} is held by another process.",
            details={"lock": name, "waited_seconds": wait_timeout, "lock_timeout_seconds": lock_timeout},
        )

    try:
        yield lock
    except BaseException:
        # The body failed. Release best-effort and let the original exception propagate untouched: raising a
        # release error from here would replace a more informative failure with a less informative one, and
        # would swallow `RunCancelledError` on the barge-in path.
        with suppress(LockError, RedisError):
            await lock.release()
        raise

    # The body succeeded, so there is no exception to mask and a release failure is worth surfacing.
    try:
        await lock.release()
    except LockNotOwnedError:
        # The critical section outlived the lock's TTL, so another process may have been running inside it
        # concurrently. Nothing can undo that now, but it must not pass silently - the fix is a longer
        # `timeout_seconds` or an `extend()` from the holder, and neither happens if this is swallowed.
        logger.error(
            "lock expired before the work finished; another holder may have run concurrently",
            extra={"lock": name, "lock_timeout_seconds": lock_timeout},
        )
        raise
    except RedisError as error:
        # We could not tell Redis to release. Benign: the key expires on its own within `lock_timeout`. The
        # cost is a delay, not a correctness failure, so it is a warning and not an exception.
        logger.warning(
            "could not release the lock; it will expire on its own",
            extra={"lock": name, "lock_timeout_seconds": lock_timeout, "error": str(error)},
        )


# --- Health. Never raises; this is what a diagnostic command calls. ---------------------------------------


async def check_health() -> RedisHealth:
    """Probe Redis. Never raises - a diagnostic that crashes when its subject is down is useless.

    Reports the eviction policy alongside reachability because reachability is not the interesting question
    here. A Redis that answers `PING` while configured to evict keys under pressure will drop a *held* lock
    without a word (`constants/redis_keys.py`), and no amount of correct code on this side detects that. One
    row in `aeris doctor` does.
    """
    started_at = perf_counter()
    try:
        client = await get_client()
        await client.ping()
        latency_ms = (perf_counter() - started_at) * 1000

        server_information = await client.info("server")
        maxmemory_policy, maxmemory_bytes = await _read_memory_configuration(client)
    except Exception as error:
        return RedisHealth(
            is_reachable=False,
            server_version=None,
            maxmemory_policy=None,
            maxmemory_bytes=None,
            latency_ms=None,
            failure_reason=f"{type(error).__name__}: {error}",
        )

    return RedisHealth(
        is_reachable=True,
        server_version=server_information.get("redis_version"),
        maxmemory_policy=maxmemory_policy,
        maxmemory_bytes=maxmemory_bytes,
        latency_ms=round(latency_ms, 2),
        failure_reason=await _describe_eviction_risk(maxmemory_policy),
    )


async def _read_memory_configuration(client: Redis) -> tuple[str | None, int | None]:
    """Read `maxmemory-policy` and `maxmemory`, or `(None, None)` where `CONFIG GET` is disabled.

    Managed Redis providers commonly disable `CONFIG`. That is a reason to report the policy as unknown, not
    a reason to fail the health check - the server is working, we simply cannot verify one thing about it.
    """
    try:
        configuration = await client.config_get("maxmemory*")
    except RedisError:
        return None, None

    raw_maxmemory = configuration.get("maxmemory")
    return configuration.get("maxmemory-policy"), int(raw_maxmemory) if raw_maxmemory is not None else None


async def _describe_eviction_risk(maxmemory_policy: str | None) -> str | None:
    """The `failure_reason` for a reachable server whose configuration is unknown or unsafe."""
    if maxmemory_policy is None:
        return (
            "Redis is reachable but `CONFIG GET` is disabled, so the eviction policy cannot be read. "
            f"Confirm with the provider that it is `{REQUIRED_MAXMEMORY_POLICY}` - any other setting lets "
            "Redis delete a lock that a process is still holding."
        )
    if maxmemory_policy != REQUIRED_MAXMEMORY_POLICY:
        return (
            f"Redis is reachable but `maxmemory-policy` is {maxmemory_policy!r}, not "
            f"{REQUIRED_MAXMEMORY_POLICY!r}. Under this policy Redis may evict a *held* lock when memory "
            "fills, after which two processes both believe they hold it. Set it with "
            f"`CONFIG SET maxmemory-policy {REQUIRED_MAXMEMORY_POLICY}`, or start the server with "
            f"`--maxmemory-policy {REQUIRED_MAXMEMORY_POLICY}` as docker-compose.yml does."
        )
    return None


async def require_healthy_redis() -> None:
    """Raise `UpstreamUnavailableError` unless Redis is reachable and cannot evict a held lock.

    Called at the start of a run rather than at process start, so that a failure is a run which refuses
    immediately with a code the frontend can branch on, instead of a stage that fails once the expensive work
    has already been paid for.

    An *unknown* policy warns rather than refuses. Refusing would make AERIS unable to run against every
    managed provider that disables `CONFIG`, which is a larger failure than the one being guarded against.
    """
    health = await check_health()

    if not health.is_reachable:
        raise UpstreamUnavailableError(
            "Redis is not available.",
            details={"upstream": "redis", "reason": health.failure_reason},
        )

    if health.maxmemory_policy is None:
        logger.warning("could not verify the Redis eviction policy", extra={"reason": health.failure_reason})
        return

    if health.maxmemory_policy != REQUIRED_MAXMEMORY_POLICY:
        raise UpstreamUnavailableError(
            "Redis is configured in a way that would let it evict a held lock.",
            details={
                "upstream": "redis",
                "maxmemory_policy": health.maxmemory_policy,
                "required_maxmemory_policy": REQUIRED_MAXMEMORY_POLICY,
                "reason": health.failure_reason,
            },
        )


async def close_client() -> None:
    """Close every pooled connection. Called on CLI exit and, in Phase 2, on application shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None
