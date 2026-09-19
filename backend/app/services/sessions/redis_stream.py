"""Pub/Sub stream bridge between Inngest worker execution and live HTTP consumers.

what  : `RedisEventPublisher` and `redis_event_subscriber`.
where : `services/sessions/redis_stream.py`. Registered as a consumer on `EventFanout`
        inside Inngest functions, and iterated by FastAPI SSE endpoints (`/api/v1/investigations/{id}/runs`).
how   : Per ADR-002 and Phase 2.5:
        Inngest executes background steps on distributed workers. A client waiting on an HTTP SSE connection
        needs the live events from that execution. Because the Inngest runner and FastAPI server may run in
        different processes, events are published to Redis channel `aeris:stream:investigation:{investigation_id}`.
        `RedisEventPublisher` serializes each event using `event.model_dump_json(by_alias=True)`.
        `redis_event_subscriber` subscribes to the channel, parses events back via `ANALYSIS_STREAM_EVENT_ADAPTER`,
        yields each event, and terminates when a terminal event (`RunCompleteEvent` or `RunErrorEvent`) is reached.
"""

import asyncio
from collections.abc import AsyncIterator
import logging

from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from app.constants.redis_keys import KEY_PREFIX, KEY_SEPARATOR, KeyNamespace
from app.schemas.events import (
    ANALYSIS_STREAM_EVENT_ADAPTER,
    AnalysisStreamEvent,
    TERMINAL_EVENT_TYPES,
)

logger = logging.getLogger(__name__)


def get_stream_channel(investigation_id: str) -> str:
    """Build the Redis channel name for an investigation's analysis stream."""
    return f"{KEY_PREFIX}{KEY_SEPARATOR}{KeyNamespace.STREAM.value}{KEY_SEPARATOR}investigation{KEY_SEPARATOR}{investigation_id}"


class RedisEventPublisher:
    """Consumer for `EventFanout` that publishes events to a Redis Pub/Sub channel."""

    def __init__(self, investigation_id: str, redis: Redis) -> None:
        self.investigation_id = investigation_id
        self.channel = get_stream_channel(investigation_id)
        self.redis = redis

    async def __call__(self, event: AnalysisStreamEvent) -> None:
        """Serialize and publish event to Redis."""
        payload = event.model_dump_json(by_alias=True)
        await self.redis.publish(self.channel, payload)


async def redis_event_subscriber(
    investigation_id: str,
    redis: Redis,
    *,
    timeout_seconds: float = 300.0,
    pubsub: PubSub | None = None,
) -> AsyncIterator[AnalysisStreamEvent]:
    """Async generator yielding events from Redis Pub/Sub until terminal event or timeout."""
    channel = get_stream_channel(investigation_id)
    if pubsub is None:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message is None:
                continue
            msg_type = message.get("type")
            if msg_type != "message":
                continue

            raw_data = message.get("data")
            if not raw_data:
                continue

            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")

            try:
                event = ANALYSIS_STREAM_EVENT_ADAPTER.validate_json(raw_data)
            except Exception:
                logger.exception("Failed to parse event from Redis pubsub channel %s", channel)
                continue

            yield event

            # Terminal event detection
            if type(event) in TERMINAL_EVENT_TYPES:
                break
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            pass
        try:
            if hasattr(pubsub, "aclose"):
                await pubsub.aclose()
            else:
                await pubsub.close()
        except Exception:
            pass


async def prepare_event_stream(
    investigation_id: str,
    redis: Redis,
    *,
    timeout_seconds: float = 300.0,
) -> tuple[PubSub, AsyncIterator[AnalysisStreamEvent]]:
    """Pre-subscribe to Redis Pub/Sub channel before initiating execution to prevent race conditions."""
    channel = get_stream_channel(investigation_id)
    pubsub: PubSub = redis.pubsub()
    await pubsub.subscribe(channel)
    stream_iterator = redis_event_subscriber(
        investigation_id, redis, timeout_seconds=timeout_seconds, pubsub=pubsub
    )
    return pubsub, stream_iterator
