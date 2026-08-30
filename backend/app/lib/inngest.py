"""The Inngest client, proven reachable and deliberately left unbound: Phase 1 has no durable workers, and that is a decision rather than an omission.

what  : `get_client()`, `send_event()`, `check_health()` for `aeris doctor`, and `EventDeliveryProof` - what
        a connectivity check returns when it has actually watched an event go out and come back.
where : The only module that constructs an Inngest client. `app/inngest/functions/` arrives in **Phase 2.5**
        and will import from here; nothing between now and then defines a function, a trigger or a step.
        Same relationship as `lib/database.py` to `app/db/models/`: the client lives in `lib/`, the thing
        built on it lives in its own package.
how   : **Read this before wondering where the workers are.** ADR-002 divides the work three ways: LangGraph
        owns the graph, its state, its checkpointing and its resume; Inngest owns durable *execution* -
        retry, replay, backoff, the dashboard; LangChain owns LLM access. Phase 1 runs the whole engine as a
        CLI, where durability comes from the LangGraph checkpointer and a killed run resumes from its last
        checkpoint with no queue involved. So there is nothing for Inngest to retry yet.

        Provisioning it now anyway is deliberate, and it is not busywork: it proves the SDK works on this
        interpreter, that the dev server runs alongside the rest of the stack, and that the event round trip
        is real - three things that would otherwise be discovered in Phase 2.5, at the point where they block
        binding rather than inform it. `roadmap.md` records this as **deferred by design**.

        **Every value the SDK could read from the environment is passed explicitly.** The Inngest client
        falls back to `INNGEST_EVENT_KEY`, `INNGEST_SIGNING_KEY`, `INNGEST_DEV` and `INNGEST_BASE_URL` when
        an argument is omitted, which would make the process environment a second source of configuration
        that `.env.example` does not document and `aeris doctor` cannot report. `code-standards.md` §4 says
        `config.py` or nowhere, and a library's own defaults do not get an exemption.

        `check_health()` targets the **dev server**, whose `/dev` endpoint reports its version and the flags
        it started with. Inngest Cloud does not serve that endpoint, so Phase 2.5 revisits this function when
        there is a production binding to probe. Saying so here is cheaper than a health check that quietly
        means nothing in production.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from time import perf_counter
from typing import Any

import inngest
from aiohttp import ClientSession, ClientTimeout

from app.config import settings
from app.constants.tasks import EventName
from app.lib.exceptions import UpstreamUnavailableError

logger = logging.getLogger(__name__)

# How long to wait for a sent event to become visible on the bus, and how often to look. **Measured, not
# guessed**: against the v1.44.0 dev server a health-probe event took 150-265 ms across five runs to appear
# on `/v1/events`. A single immediate read is therefore a coin flip - which is exactly how the Phase 0.5 test
# passed three times in a row while `aeris doctor` failed on the same code. The deadline is an order of
# magnitude above the observed spread, because the failure this guards is a *flaky gate*, and a flaky gate is
# worse than no gate: it teaches people to re-run.
EVENT_VISIBILITY_DEADLINE_SECONDS = 3.0
EVENT_VISIBILITY_POLL_SECONDS = 0.05

# Handed to the Inngest client so its own output is separable from ours. Without this the SDK logs through
# `app.lib.inngest` and inherits our level, which means silencing its DEBUG narration would also silence the
# messages this module writes about it. `constants/logs.py` sets the floor for this name.
sdk_logger = logging.getLogger(f"{__name__}.sdk")

# One client per process, built on first use - the same shape as the engine, the Redis pool and the S3
# client. The Inngest client holds an HTTP session, so a second one is a second pool for no reason.
_client: inngest.Inngest | None = None


@dataclass(frozen=True, slots=True)
class InngestHealth:
    """What `aeris doctor` prints for the Inngest row."""

    is_reachable: bool
    server_version: str | None
    # The dev server can be told to scan localhost for apps to sync. AERIS registers none until Phase 2.5, so
    # discovery being *off* is the expected state, and seeing it on means someone is about to be confused by
    # a dashboard full of sync failures against an app that does not exist.
    app_discovery_enabled: bool | None
    latency_ms: float | None
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class EventDeliveryProof:
    """Evidence that an event was accepted *and* can be read back, not merely that a POST returned 200.

    The distinction is the whole point of the Phase 0.5 gate. A 200 from the event API says the request was
    well formed; it does not say the event reached the bus. Reading it back by id does.
    """

    event_id: str
    event_name: str
    was_read_back: bool
    failure_reason: str | None


async def get_client() -> inngest.Inngest:
    """Return the process-wide Inngest client, creating it on first call."""
    global _client
    if _client is None:
        _client = inngest.Inngest(
            app_id=settings.inngest_app_id,
            event_key=settings.inngest_event_key.get_secret_value(),
            signing_key=settings.inngest_signing_key.get_secret_value(),
            api_base_url=str(settings.inngest_api_base_url).rstrip("/"),
            event_api_base_url=str(settings.inngest_event_api_base_url).rstrip("/"),
            # Derived from `environment`, never configured on its own - see `config.py`. Wrong in one
            # direction a deployed process posts events at a dev server that is not there; wrong in the
            # other a local run writes into the production event history.
            is_production=settings.inngest_is_production,
            # A `timedelta`, never the bare int the signature also accepts: **the SDK reads an int as
            # milliseconds** (`client.py`: `request_timeout / 1000`), while every other timeout in this
            # backend - and in botocore, redis-py and asyncpg - is seconds. Passing
            # `inngest_request_timeout_seconds` directly made every send time out after 10 ms, and the SDK
            # reported it as "never received response while sending events" with no mention of a timeout.
            request_timeout=timedelta(seconds=settings.inngest_request_timeout_seconds),
            logger=sdk_logger,
        )
    return _client


async def send_event(name: EventName | str, data: dict[str, Any] | None = None) -> list[str]:
    """Put one event on the bus and return the ids Inngest assigned it.

    The only write path this module has, and in Phase 1 the only caller is the connectivity check. It exists
    now rather than in Phase 2.5 so that the failure mapping is settled: every other `lib/` client turns its
    provider's errors into ours, and leaving Inngest as the exception would hand Phase 2.5 an untyped failure
    path at the point where it is enqueueing real work.
    """
    client = await get_client()
    event_name = name.value if isinstance(name, EventName) else name

    try:
        return await client.send(inngest.Event(name=event_name, data=data or {}))
    except Exception as error:
        raise UpstreamUnavailableError(
            "Could not send an event to Inngest.",
            details={"upstream": "inngest", "event": event_name, "reason": f"{type(error).__name__}: {error}"},
        ) from error


async def check_health() -> InngestHealth:
    """Probe the Inngest dev server. Never raises - this is what a diagnostic command calls."""
    started_at = perf_counter()
    try:
        payload = await _get_json(f"{str(settings.inngest_api_base_url).rstrip('/')}/dev")
        latency_ms = (perf_counter() - started_at) * 1000
    except Exception as error:
        return InngestHealth(
            is_reachable=False,
            server_version=None,
            app_discovery_enabled=None,
            latency_ms=None,
            failure_reason=f"{type(error).__name__}: {error}",
        )

    start_options = payload.get("startOpts") or {}
    discovery_enabled = start_options.get("autodiscover")

    return InngestHealth(
        is_reachable=True,
        server_version=payload.get("version"),
        app_discovery_enabled=discovery_enabled,
        latency_ms=round(latency_ms, 2),
        failure_reason=(
            None
            if discovery_enabled is not True
            else "The dev server is scanning localhost for apps to sync, and AERIS registers none until "
            "Phase 2.5 (ADR-002). The dashboard will fill with sync failures against an app that does not "
            "exist. Start it with `--no-discovery`, as docker-compose.yml does."
        ),
    )


async def check_event_delivery() -> EventDeliveryProof:
    """Send a health-probe event and read it back off the bus. Never raises.

    **This is the Phase 0.5 gate.** It is two steps rather than one because the first step alone proves
    almost nothing: the event API answers `200` as soon as it has accepted the request, so a check that
    stopped there would pass against a server that dropped every event it received. Reading the event back by
    the id that was handed out is what makes the round trip real.

    The read goes through the dev server's REST API rather than the SDK, because the SDK has no "fetch an
    event" call - it is a client for *producing* events and *serving* functions, and there are no functions
    here to serve.
    """
    try:
        event_ids = await send_event(EventName.HEALTH_PROBE, {"source": "aeris doctor"})
    except UpstreamUnavailableError as error:
        return EventDeliveryProof(
            event_id="",
            event_name=EventName.HEALTH_PROBE.value,
            was_read_back=False,
            failure_reason=error.message,
        )

    event_id = event_ids[0]

    try:
        was_read_back = await find_event_on_bus(EventName.HEALTH_PROBE, event_id) is not None
    except Exception as error:
        return EventDeliveryProof(
            event_id=event_id,
            event_name=EventName.HEALTH_PROBE.value,
            was_read_back=False,
            failure_reason=f"The event was accepted but could not be read back: {type(error).__name__}: {error}",
        )

    return EventDeliveryProof(
        event_id=event_id,
        event_name=EventName.HEALTH_PROBE.value,
        was_read_back=was_read_back,
        failure_reason=(
            None
            if was_read_back
            else f"Inngest accepted event {event_id} and did not return it within "
            f"{EVENT_VISIBILITY_DEADLINE_SECONDS:g} s. The event API answers 200 on receipt, so acceptance "
            "alone is not delivery - something between the API and the bus is dropping events."
        ),
    )


async def find_event_on_bus(event_name: EventName | str, event_id: str) -> dict[str, Any] | None:
    """Read one event back off the bus by id, waiting for it to propagate. `None` if it never appears.

    **Public, and it has to be, because anything verifying a send needs it.** Polling rather than reading
    once is not defensive coding: the bus is asynchronous, so the event API answers `200` when it has
    *accepted* the request and the event becomes queryable a little later. A single immediate read tests the
    propagation delay instead of the delivery.

    That is not hypothetical. The Phase 0.5 test passed three runs in a row doing its own immediate read, and
    then `aeris doctor` failed on the same code path; measuring showed the event taking 150-265 ms to appear.
    Both callers go through here now, so there is one place that knows the bus is eventually consistent
    rather than two places that have to remember it.

    Returns the whole event, not a boolean, so a caller can also check that the name and payload survived.
    """
    api_base_url = str(settings.inngest_api_base_url).rstrip("/")
    name = event_name.value if isinstance(event_name, EventName) else event_name
    query_url = f"{api_base_url}/v1/events?name={name}"
    deadline = asyncio.get_running_loop().time() + EVENT_VISIBILITY_DEADLINE_SECONDS

    while True:
        payload = await _get_json(query_url)
        for entry in payload.get("data", []):
            if entry.get("id") == event_id:
                return dict(entry)
        if asyncio.get_running_loop().time() >= deadline:
            return None
        await asyncio.sleep(EVENT_VISIBILITY_POLL_SECONDS)


async def require_healthy_inngest() -> None:
    """Raise `UpstreamUnavailableError` unless the Inngest server is reachable.

    Nothing calls this yet, and nothing should until Phase 2.5: a Phase 1 run has no durable step to enqueue,
    so refusing to start one because a dev server is down would invent a dependency that does not exist. It
    is written here because the other three `lib/` clients have one and the shape is the pattern - and it is
    exercised by a test, so it is not an unverified claim.
    """
    health = await check_health()
    if not health.is_reachable:
        raise UpstreamUnavailableError(
            "Inngest is not available.",
            details={"upstream": "inngest", "reason": health.failure_reason},
        )


async def reset_client() -> None:
    """Drop the cached client so the next call rebuilds it from current configuration.

    Named `reset` rather than `close`, unlike its three siblings, because there is nothing here to close:
    the Inngest SDK exposes no shutdown method and its `AuthenticatedHTTPClient` has no `aclose` - checked,
    not assumed. Calling this `close_client()` for symmetry would claim connections were released when they
    are only dereferenced, and a teardown that quietly does nothing is worse than an absent one.

    It exists for tests that change configuration between cases, and for Phase 2.5 to grow into if the SDK
    ever gains a real shutdown.
    """
    global _client
    _client = None


async def _get_json(url: str) -> dict[str, Any]:
    """One JSON GET against the dev server, with the configured timeout."""
    timeout = ClientTimeout(total=settings.inngest_request_timeout_seconds)
    async with ClientSession(timeout=timeout) as http_session:
        async with http_session.get(url) as response:
            response.raise_for_status()
            return dict(await response.json())
