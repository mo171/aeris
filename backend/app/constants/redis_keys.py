"""The Redis keyspace: two namespaces that must never be confused, and the server policy that keeps one of them correct.

what  : `KEY_PREFIX`, `KEY_SEPARATOR`, `KeyNamespace` (`lock`, `cache`), `REQUIRED_MAXMEMORY_POLICY` and the
        SCAN batch size used to clear a namespace.
where : Read only by `app/lib/redis.py`, which is the only module that builds a Redis key. Named here rather
        than inlined there because a key prefix is a vocabulary shared with anyone inspecting the server by
        hand, and because the eviction policy below is an invariant of the design rather than a tunable -
        which is why it is a constant and not a setting in `config.py`.
how   : AERIS puts two unrelated things in one Redis: **locks, which are correctness**, and **cache entries,
        which are speed**. They are separated by key prefix rather than by logical database, because Redis
        Cluster and most managed providers expose only database 0 - `SELECT` is not portable, so a deployment
        that relied on it would silently collapse the two namespaces into one.

        `REQUIRED_MAXMEMORY_POLICY` is the non-obvious half. Under any `allkeys-*` policy Redis may evict any
        key once memory fills; under any `volatile-*` policy it may evict any key that carries a TTL - which
        every lock does, because the TTL is how a crashed holder's lock is released. Either setting therefore
        permits Redis to delete a *held* lock, after which two processes both believe they hold it and load
        two models into 8 GB of VRAM. `noeviction` instead makes writes fail when memory is full, which the
        cache absorbs as a miss and the lock reports as a refusal - a loud failure in place of a silent one.

        `app/lib/redis.py` reads the live value and `aeris doctor` prints it, because this is a property of
        the *server* and cannot be asserted from our side.
"""

from enum import StrEnum
from typing import Final

# Every key this backend writes begins with it, so a Redis shared with another service stays greppable and a
# namespace clear cannot reach a neighbour's keys.
KEY_PREFIX: Final[str] = "aeris"
KEY_SEPARATOR: Final[str] = ":"


class KeyNamespace(StrEnum):
    """The two kinds of thing AERIS stores in Redis. Nothing is written outside one of them."""

    # Mutual exclusion over a machine-scoped resource - today the GPU's VRAM. Losing one is a correctness
    # failure, so every operation on this namespace raises rather than returning a value.
    LOCK = "lock"

    # Short-lived, reconstructible values: STAC search results, tile metadata, model status. Losing one costs
    # a recomputation, so every operation on this namespace degrades silently instead of raising.
    CACHE = "cache"


REQUIRED_MAXMEMORY_POLICY: Final[str] = "noeviction"

# `SCAN COUNT` hint used when clearing a namespace. Large enough that clearing a few thousand keys is a
# handful of round trips; small enough that no single call blocks the server noticeably - SCAN's whole
# guarantee is that it never blocks for long, and a large COUNT gives that guarantee away.
NAMESPACE_SCAN_BATCH_SIZE: Final[int] = 500
