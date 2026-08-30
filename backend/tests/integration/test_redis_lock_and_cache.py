"""The Phase 0.3 gate: a value round-trips through the cache, and a lock held by one holder blocks a second and releases when that holder dies.

what  : Integration tests for `app/lib/redis.py` against a live Redis. Covers the gate itself, the eviction
        policy the locks depend on, and the asymmetry that is the reason the two namespaces exist - the cache
        degrades on failure, the lock refuses.
where : `tests/integration/`. Marked `integration`, so it needs `docker compose up -d`. Like the PostGIS
        tests it is not skipped when infrastructure is missing - it fails, because it is the evidence for a
        Phase 0 gate and a silently skipped gate is an unproven one.
how   : Every test names its keys with a fresh identifier, so two runs never collide and a test that fails
        part-way cannot leave a lock that breaks the next run - the abandoned key expires on its own.

        Two tests are worth more than the others.

        `test_a_crashed_holders_lock_is_released_by_its_expiry` is the half of the gate that cannot be proven
        by reading the code. A crash is simulated the only honest way: acquire the lock exactly as
        `held_lock` does and then never release it. What follows - that a second acquirer is refused
        immediately, then succeeds after waiting out the TTL - is the whole crash-recovery mechanism, and it
        lives in the Redis server rather than in anything this repository can unit-test.

        `test_clearing_the_cache_does_not_touch_a_held_lock` is the concrete payoff of the keyspace layout in
        `constants/redis_keys.py`. Clearing a cache is a routine operation; if it were written as `FLUSHDB`
        it would also free every lock that a live process still believed it held, and nothing would report
        it. This test is what stops that being written later.

        One test needs no server, because it proves the *absence* path. It lives here anyway: the asymmetry
        it demonstrates is the subject of this file, and separating it would hide the pair.
"""

from time import perf_counter
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.constants.errors import ErrorCode
from app.constants.redis_keys import (
    KEY_PREFIX,
    KEY_SEPARATOR,
    REQUIRED_MAXMEMORY_POLICY,
    KeyNamespace,
)
from app.lib import redis as aeris_redis
from app.lib.exceptions import ConflictError, UpstreamUnavailableError
from app.lib.redis import (
    _build_key,
    cache_delete,
    cache_get,
    cache_set,
    check_health,
    clear_cache_namespace,
    get_client,
    held_lock,
)

pytestmark = pytest.mark.integration

# Short enough that waiting one out keeps the suite fast, long enough that the wait is unambiguous on a
# loaded machine. Only used where a test deliberately abandons a lock.
ABANDONED_LOCK_TIMEOUT_SECONDS = 1.0


@pytest.fixture
def unique_name() -> str:
    """A key name no other test or previous run uses. Contains no glob metacharacters, so it is safe in a
    `SCAN MATCH` pattern."""
    return f"test-{uuid4().hex}"


async def test_redis_is_reachable_and_will_not_evict_a_held_lock() -> None:
    """The precondition for everything else, and the row `aeris doctor` prints.

    The eviction policy is asserted rather than assumed because it is a property of the *server*, not of this
    code. Under `allkeys-*` or `volatile-*` Redis may delete a lock while a process still holds it, and every
    other test in this file would keep passing while the guarantee they demonstrate had quietly gone.
    """
    health = await check_health()

    assert health.is_reachable, f"Redis unreachable: {health.failure_reason}"
    assert health.server_version is not None
    assert health.maxmemory_policy == REQUIRED_MAXMEMORY_POLICY, health.failure_reason
    # A reachable, correctly configured server has nothing to report.
    assert health.failure_reason is None
    assert health.latency_ms is not None


async def test_a_cached_value_round_trips_and_carries_an_expiry(unique_name: str) -> None:
    """Set/get, half of the gate - plus the invariant that makes the cache safe to share with the locks.

    The TTL assertion is the part worth having. Under `noeviction` nothing is ever evicted, so a cache entry
    written without an expiry is a permanent one; enough of those fill the instance, and the first thing that
    then fails is a *lock* write. The expiry on a cache key is what keeps the cache from breaking the locks,
    so it is checked rather than trusted.
    """
    value = {"scene_id": "scn_01", "cloud_cover": 0.12, "bands": ["B04", "B08"], "usable": True}

    assert await cache_set(unique_name, value) is True
    assert await cache_get(unique_name) == value

    client = await get_client()
    # The literal key layout is pinned here, once, rather than in every test. Anything that changes the
    # prefix is a change to a keyspace shared with anyone inspecting the server by hand.
    key = f"{KEY_PREFIX}{KEY_SEPARATOR}{KeyNamespace.CACHE.value}{KEY_SEPARATOR}{unique_name}"
    assert await client.exists(key) == 1
    assert 0 < await client.ttl(key) <= 300

    await cache_delete(unique_name)
    assert await cache_get(unique_name) is None


async def test_a_held_lock_blocks_a_second_acquirer(unique_name: str) -> None:
    """The other half of the gate. A second acquirer waits, then is refused - it never proceeds unlocked."""
    async with held_lock(unique_name, timeout_seconds=10):
        started_at = perf_counter()

        with pytest.raises(ConflictError) as raised:
            async with held_lock(unique_name, timeout_seconds=10, blocking_timeout_seconds=0.5):
                pytest.fail("the second acquirer entered a lock that was already held")

        waited_seconds = perf_counter() - started_at

    # It genuinely waited and retried rather than failing on the first attempt - which is what makes this a
    # queue rather than a coin toss. The bound is loose because redis-py polls on a 0.1 s sleep and stops one
    # sleep short of the deadline.
    assert waited_seconds >= 0.3

    # `ConflictError`, not `UpstreamUnavailableError`: Redis answered correctly and the resource is busy.
    # The frontend branches on this code, so the distinction is part of the contract rather than wording.
    assert raised.value.code is ErrorCode.CONFLICT
    assert raised.value.status == 409
    assert raised.value.details is not None
    assert raised.value.details["lock"] == unique_name


async def test_a_crashed_holders_lock_is_released_by_its_expiry(unique_name: str) -> None:
    """The rest of the gate: a holder that dies without releasing does not deadlock the system.

    The crash is simulated the only honest way - acquire the lock exactly as `held_lock` does, then drop it
    without releasing. Recovery is the key's TTL expiring inside Redis, so this asserts the TTL exists, that
    the lock really does block while it is counting down, and that a patient acquirer gets in afterwards.
    """
    client = await get_client()
    key = await _build_key(KeyNamespace.LOCK, unique_name)

    abandoned_lock = client.lock(key, timeout=ABANDONED_LOCK_TIMEOUT_SECONDS, blocking=False)
    assert await abandoned_lock.acquire() is True
    del abandoned_lock  # the holder is gone; nothing will ever call release()

    # The TTL is the entire release mechanism. Without it this key would outlive the process forever.
    remaining_ms = await client.pttl(key)
    assert 0 < remaining_ms <= ABANDONED_LOCK_TIMEOUT_SECONDS * 1000

    # While it counts down the lock is real: an acquirer unwilling to wait is refused.
    with pytest.raises(ConflictError):
        async with held_lock(unique_name, blocking_timeout_seconds=0):
            pytest.fail("acquired a lock that an abandoned holder still owns")

    # One willing to wait longer than the abandoned TTL gets it - and had to wait for it.
    started_at = perf_counter()
    async with held_lock(
        unique_name,
        timeout_seconds=10,
        blocking_timeout_seconds=ABANDONED_LOCK_TIMEOUT_SECONDS + 2,
    ):
        waited_seconds = perf_counter() - started_at

    assert waited_seconds >= ABANDONED_LOCK_TIMEOUT_SECONDS * 0.5, (
        "the lock was acquired without waiting, so the abandoned holder was never actually holding it"
    )


async def test_clearing_the_cache_does_not_touch_a_held_lock(unique_name: str) -> None:
    """Why the two namespaces are prefixed rather than mixed: clearing one must not free the other.

    `FLUSHDB` is the obvious way to write a cache clear and it would release every lock in the process,
    silently, while live holders carried on believing they were exclusive. `clear_cache_namespace` scans a
    prefix instead. This test fails the moment someone reaches for the shorter version.
    """
    client = await get_client()
    lock_key = await _build_key(KeyNamespace.LOCK, unique_name)

    async with held_lock(unique_name, timeout_seconds=30):
        assert await cache_set(f"{unique_name}:first", {"value": 1}) is True
        assert await cache_set(f"{unique_name}:second", {"value": 2}) is True

        assert await clear_cache_namespace(unique_name) == 2

        assert await cache_get(f"{unique_name}:first") is None
        assert await cache_get(f"{unique_name}:second") is None
        assert await client.exists(lock_key) == 1, "clearing the cache released a held lock"


async def test_the_cache_degrades_when_redis_is_unreachable_but_the_lock_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The asymmetry, stated as a test so it cannot drift.

    A cache miss costs a recomputation, so an outage must read as a miss and AERIS must keep working. A lock
    is exclusive access to the GPU, so an outage must raise - a caller that carried on unlocked would load a
    second model into a card with room for one, and the failure would appear stages later as a CUDA
    out-of-memory error with nothing pointing back at Redis.

    Needs no server: it is the failure path, produced by pointing the client at a port nothing listens on.
    """
    unreachable_client = Redis.from_url(
        "redis://127.0.0.1:1/0",
        decode_responses=True,
        # A quarter of a second, not the configured five. The connection is refused rather than timing out,
        # but a machine that silently drops the packet would otherwise stall the suite.
        socket_connect_timeout=0.25,
    )
    monkeypatch.setattr(aeris_redis, "_client", unreachable_client)

    try:
        assert await cache_get("anything") is None
        assert await cache_set("anything", {"value": 1}) is False
        # And deleting is survivable too - a cache operation never propagates an outage.
        await cache_delete("anything")

        with pytest.raises(UpstreamUnavailableError) as raised:
            async with held_lock("anything", blocking_timeout_seconds=0.25):
                pytest.fail("took a lock against a Redis that is not there")
    finally:
        await unreachable_client.aclose()

    # 503 with a retryable code, and the upstream named - so the failure is attributable without reading our
    # logs, and the frontend can tell "try again" apart from "this will never work".
    assert raised.value.code is ErrorCode.UPSTREAM_UNAVAILABLE
    assert raised.value.status == 503
    assert raised.value.details is not None
    assert raised.value.details["upstream"] == "redis"


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/integration/test_redis_lock_and_cache.py -v          2026-08-31
#
#   platform win32 -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0
#   asyncio: mode=Mode.AUTO, asyncio_default_test_loop_scope=session
#   collected 6 items
#
#   test_redis_is_reachable_and_will_not_evict_a_held_lock ....................... PASSED [ 16%]
#   test_a_cached_value_round_trips_and_carries_an_expiry ........................ PASSED [ 33%]
#   test_a_held_lock_blocks_a_second_acquirer .................................... PASSED [ 50%]
#   test_a_crashed_holders_lock_is_released_by_its_expiry ........................ PASSED [ 66%]
#   test_clearing_the_cache_does_not_touch_a_held_lock ........................... PASSED [ 83%]
#   test_the_cache_degrades_when_redis_is_unreachable_but_the_lock_refuses ....... PASSED [100%]
#
#   ============================== 6 passed in 4.74s ==============================
#
# Against Redis 8.2.9 in the `aeris-redis` container, `maxmemory-policy noeviction`, `maxmemory 268435456`,
# RDB and AOF both off.
#
# Passing is not by itself evidence, so each load-bearing claim was checked by breaking the code it rests on
# and confirming that exactly the intended test caught it:
#
#   `clear_cache_namespace` calls FLUSHDB    -> test_clearing_the_cache_does_not_touch_a_held_lock  FAILED
#                                               ("clearing the cache released a held lock")
#   `cache_set` omits the `ex=` expiry       -> test_a_cached_value_round_trips_and_carries_an_expiry FAILED
#                                               (ttl assertion, line 104)
#   `held_lock` proceeds without the lock    -> test_a_held_lock_blocks_a_second_acquirer            FAILED
#                                               ("the second acquirer entered a lock that was already held")
#
# Each mutation was reverted and the file byte-compared against its pre-mutation copy before this was written.
