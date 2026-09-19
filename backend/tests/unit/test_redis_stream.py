"""Tests for the Phase 2.5 Redis Pub/Sub stream bridge.

Validates that:
1. RedisEventPublisher serializes stream events and publishes them to the proper channel.
2. redis_event_subscriber subscribes, parses events into AnalysisStreamEvent models,
   and terminates cleanly when a terminal event (RunCompleteEvent / RunErrorEvent) is received.
3. Errors and pubsub cleanup happen cleanly on generator exit.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.constants.intents import Intent
from app.schemas.events import (
    AnalysisStreamEvent,
    RunCompleteEvent,
    RunErrorEvent,
    RunStartEvent,
)
from app.services.sessions.redis_stream import (
    RedisEventPublisher,
    get_stream_channel,
    redis_event_subscriber,
)


@pytest.mark.unit
async def test_get_stream_channel() -> None:
    channel = get_stream_channel("inv_123")
    assert "inv_123" in channel
    assert channel.startswith("aeris:stream:investigation:")


@pytest.mark.unit
async def test_redis_event_publisher_publishes_serialized_json() -> None:
    mock_redis = AsyncMock()
    investigation_id = "inv_test_pub"
    publisher = RedisEventPublisher(investigation_id, mock_redis)

    event = RunStartEvent(
        run_id="run_001",
        intent=Intent.SCENE_VQA,
        started_at=datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC),
    )
    await publisher(event)

    channel = get_stream_channel(investigation_id)
    mock_redis.publish.assert_awaited_once()
    called_channel, called_payload = mock_redis.publish.call_args[0]
    assert called_channel == channel
    assert '"type":"run-start"' in called_payload or '"type": "run-start"' in called_payload
    assert '"runId":"run_001"' in called_payload or '"runId": "run_001"' in called_payload


@pytest.mark.unit
async def test_redis_event_subscriber_yields_events_and_stops_on_run_complete() -> None:
    mock_redis = MagicMock()
    mock_pubsub = MagicMock()

    start_event = RunStartEvent(
        run_id="run_002",
        intent=Intent.INDEX_QUERY,
        started_at=datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC),
    )
    complete_event = RunCompleteEvent(
        run_id="run_002",
        confidence=0.95,
        total_duration_ms=1200,
    )

    messages = [
        {"type": "subscribe", "data": 1},
        {"type": "message", "data": start_event.model_dump_json(by_alias=True)},
        {"type": "message", "data": complete_event.model_dump_json(by_alias=True)},
    ]

    async def mock_listen():
        for msg in messages:
            yield msg

    mock_pubsub.listen = mock_listen
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.aclose = AsyncMock()
    mock_pubsub.close = AsyncMock()
    mock_redis.pubsub.return_value = mock_pubsub

    investigation_id = "inv_test_sub"
    received_events: list[AnalysisStreamEvent] = []

    async for ev in redis_event_subscriber(investigation_id, mock_redis, timeout_seconds=2.0):
        received_events.append(ev)

    assert len(received_events) == 2
    assert isinstance(received_events[0], RunStartEvent)
    assert received_events[0].run_id == "run_002"
    assert isinstance(received_events[1], RunCompleteEvent)
    assert received_events[1].confidence == 0.95
    assert received_events[1].total_duration_ms == 1200

    mock_pubsub.subscribe.assert_awaited_once_with(get_stream_channel(investigation_id))
    mock_pubsub.unsubscribe.assert_awaited_once_with(get_stream_channel(investigation_id))
    mock_pubsub.aclose.assert_awaited_once()


@pytest.mark.unit
async def test_redis_event_subscriber_stops_on_run_error() -> None:
    mock_redis = MagicMock()
    mock_pubsub = MagicMock()

    error_event = RunErrorEvent(run_id="run_err_01", message="Model out of bounds")

    messages = [
        {"type": "subscribe", "data": 1},
        {"type": "message", "data": error_event.model_dump_json(by_alias=True)},
    ]

    async def mock_listen():
        for msg in messages:
            yield msg

    mock_pubsub.listen = mock_listen
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.aclose = AsyncMock()
    mock_pubsub.close = AsyncMock()
    mock_redis.pubsub.return_value = mock_pubsub

    received_events: list[AnalysisStreamEvent] = []
    async for ev in redis_event_subscriber("inv_err", mock_redis, timeout_seconds=2.0):
        received_events.append(ev)

    assert len(received_events) == 1
    assert isinstance(received_events[0], RunErrorEvent)
    assert received_events[0].message == "Model out of bounds"
    mock_pubsub.unsubscribe.assert_awaited_once()
    mock_pubsub.aclose.assert_awaited_once()
