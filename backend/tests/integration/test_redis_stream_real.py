"""Live integration test for the Redis Pub/Sub stream bridge.

Verifies that RedisEventPublisher publishes to a live Redis server and
redis_event_subscriber receives, deserializes, and yields the events until completion.
"""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.constants.intents import Intent
from app.lib.redis import get_client
from app.schemas.events import (
    AnalysisStreamEvent,
    RunCompleteEvent,
    RunStartEvent,
)
from app.services.sessions.redis_stream import (
    RedisEventPublisher,
    redis_event_subscriber,
)

pytestmark = pytest.mark.integration


async def test_live_redis_pubsub_streaming_round_trip() -> None:
    client = await get_client()
    investigation_id = f"inv-live-{uuid4().hex[:8]}"
    run_id = f"run-live-{uuid4().hex[:8]}"

    publisher = RedisEventPublisher(investigation_id, client)

    start_event = RunStartEvent(
        run_id=run_id,
        intent=Intent.DETECT,
        started_at=datetime.now(UTC),
    )
    complete_event = RunCompleteEvent(
        run_id=run_id,
        confidence=0.88,
        total_duration_ms=450,
    )

    received_events: list[AnalysisStreamEvent] = []

    async def consume():
        async for ev in redis_event_subscriber(investigation_id, client, timeout_seconds=5.0):
            received_events.append(ev)

    consumer_task = asyncio.create_task(consume())

    # Wait 50ms for subscriber to register with Redis
    await asyncio.sleep(0.05)

    await publisher(start_event)
    await publisher(complete_event)

    await asyncio.wait_for(consumer_task, timeout=5.0)

    assert len(received_events) == 2
    assert isinstance(received_events[0], RunStartEvent)
    assert received_events[0].run_id == run_id
    assert isinstance(received_events[1], RunCompleteEvent)
    assert received_events[1].confidence == 0.88
