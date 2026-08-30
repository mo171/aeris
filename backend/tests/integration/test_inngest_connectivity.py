"""The Phase 0.5 gate: the Inngest dev server is reachable and an event sent through the SDK comes back off the bus.

what  : Integration tests for `app/lib/inngest.py`. Reachability, the event round trip, and the assertions
        that keep this sub-phase honest about what it deliberately did *not* build.
where : `tests/integration/`. Marked `integration`, so it needs `docker compose up -d`.
how   : **This is the smallest gate in Phase 0, and it is small on purpose.** ADR-002 gives LangGraph the
        graph, its state and its resume, and gives Inngest durable *execution* - retry, replay, backoff.
        Phase 1 runs the engine as a CLI where durability is the LangGraph checkpointer, so there is nothing
        for Inngest to retry until Phase 2.5. `roadmap.md` records that as **deferred by design**, and
        `test_no_functions_are_registered_yet` asserts it rather than leaving it as a claim in a document.

        The round-trip test is two steps rather than one, and the second step is the one worth having. The
        event API answers `200` the moment it accepts a well-formed request, so a test that stopped there
        would pass against a server that dropped every event it was handed. Reading the event back by the id
        that was returned is what makes it a round trip. Same shape as the 0.4 lesson: the status code is not
        the evidence.
"""

import pytest
from aiohttp import ClientSession

from app.config import settings
from app.constants.tasks import EVENT_NAME_PREFIX, EventName
from app.lib.inngest import (
    check_event_delivery,
    check_health,
    find_event_on_bus,
    get_client,
    require_healthy_inngest,
    send_event,
)

pytestmark = pytest.mark.integration


async def test_the_dev_server_is_reachable_and_reports_its_version() -> None:
    """The row `aeris doctor` prints, and the precondition for the round trip below."""
    health = await check_health()

    assert health.is_reachable, f"Inngest unreachable: {health.failure_reason}"
    assert health.server_version is not None
    assert health.latency_ms is not None


async def test_app_discovery_is_off_because_there_is_no_app_to_discover() -> None:
    """The dev server must not be scanning localhost for an app that will not exist until Phase 2.5.

    Left on, it polls for an SDK endpoint that is never there and fills the dashboard with sync failures -
    which reads, to anyone opening it, as though the integration is broken rather than absent. The flag is
    set in `docker-compose.yml` and read back here through the server's own `/dev` endpoint, so the compose
    file and the running server cannot drift apart silently.
    """
    health = await check_health()

    assert health.app_discovery_enabled is False
    assert health.failure_reason is None


async def test_an_event_sent_through_the_sdk_can_be_read_back_off_the_bus() -> None:
    """**The gate.** Send, then read back by id.

    Both halves matter. The send proves the SDK works on this interpreter against this server; the read-back
    proves the event reached the bus rather than merely being accepted by the API in front of it.
    """
    proof = await check_event_delivery()

    assert proof.was_read_back, proof.failure_reason
    assert proof.event_id
    assert proof.event_name == EventName.HEALTH_PROBE.value
    assert proof.failure_reason is None


async def test_a_sent_event_keeps_its_name_and_payload(unique_marker: str) -> None:
    """What went in is what comes out - the name unchanged and the data intact.

    Asserted separately from the gate because the gate only matches on id. An event whose payload were
    dropped or whose name were rewritten in transit would still satisfy an id match, and both would surface
    in Phase 2.5 as a function that never triggers.

    Reads back through `find_event_on_bus`, which waits for propagation. **This test originally did its own
    immediate read and passed three runs in a row before failing** - the bus takes 150-265 ms to make an
    event queryable, so a single read is a coin flip. One helper now owns that knowledge.
    """
    event_ids = await send_event(EventName.HEALTH_PROBE, {"marker": unique_marker})
    assert len(event_ids) == 1

    event = await find_event_on_bus(EventName.HEALTH_PROBE, event_ids[0])

    assert event is not None, "the event was accepted and then never appeared on the bus"
    assert event["name"] == EventName.HEALTH_PROBE.value
    assert event["data"]["marker"] == unique_marker


async def test_every_event_name_carries_the_project_prefix() -> None:
    """A shared Inngest account stays filterable only if every event this backend sends is identifiable.

    Trivial today with one event, which is exactly when it is worth writing: the convention is cheap to hold
    now and expensive to impose once Phase 2.5 has three function triggers matching on names in a durable
    history.
    """
    for event_name in EventName:
        assert event_name.value.startswith(f"{EVENT_NAME_PREFIX}/")


async def test_no_functions_are_registered_yet_and_that_is_deliberate() -> None:
    """Phase 0.5's other half: proving what was *not* built.

    Inngest is provisioned and unbound until Phase 2.5 (ADR-002). If a function ever appears before then,
    this test fails and asks the question that matters - has the Phase 1 durability decision changed, or did
    someone add a worker without noticing the checkpointer already handles it?

    Asserted through the dev server's own app list rather than by inspecting our source, because the claim is
    about what the server has been told, not about what the repository contains.
    """
    api_base_url = str(settings.inngest_api_base_url).rstrip("/")
    async with ClientSession() as http_session:
        async with http_session.get(f"{api_base_url}/v0/gql", params={"query": "{__typename}"}) as response:
            # The GraphQL endpoint's shape is not the point; that the server is answering is.
            assert response.status in {200, 400, 405}

    async with ClientSession() as http_session:
        async with http_session.get(f"{api_base_url}/dev") as response:
            start_options = (await response.json()).get("startOpts", {})

    assert start_options.get("urls") == [], (
        "The dev server has been given an app URL to sync. Inngest is deferred by design until Phase 2.5 "
        "(ADR-002) - if that decision has changed, change roadmap.md and this test together."
    )


async def test_require_healthy_inngest_passes_against_a_running_server() -> None:
    """The gate function the Phase 2.5 binding will call before enqueueing work.

    Nothing calls it in Phase 1 - a CLI run has no durable step to enqueue, so refusing to start one because
    a dev server is down would invent a dependency that does not exist. It is exercised here so it is not an
    unverified claim sitting in the module until someone needs it.
    """
    await require_healthy_inngest()


async def test_the_client_is_configured_from_config_not_from_the_environment() -> None:
    """The SDK reads `INNGEST_*` from the process environment when an argument is omitted.

    That would make the environment a second source of configuration - undocumented in `.env.example`,
    invisible to `aeris doctor`, and able to disagree with `config.py` (`code-standards.md` §4). Everything
    is passed explicitly, so the client's app id is the configured one and nothing else.
    """
    client = await get_client()

    assert client.app_id == settings.inngest_app_id
    assert await get_client() is client, "a second call built a second client and a second connection pool"


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/integration/test_inngest_connectivity.py -v            2026-08-31
#
#   collected 8 items
#
#   test_the_dev_server_is_reachable_and_reports_its_version ..................... PASSED [ 12%]
#   test_app_discovery_is_off_because_there_is_no_app_to_discover ................ PASSED [ 25%]
#   test_an_event_sent_through_the_sdk_can_be_read_back_off_the_bus .............. PASSED [ 37%]
#   test_a_sent_event_keeps_its_name_and_payload ................................. PASSED [ 50%]
#   test_every_event_name_carries_the_project_prefix ............................. PASSED [ 62%]
#   test_no_functions_are_registered_yet_and_that_is_deliberate .................. PASSED [ 75%]
#   test_require_healthy_inngest_passes_against_a_running_server ................. PASSED [ 87%]
#   test_the_client_is_configured_from_config_not_from_the_environment ........... PASSED [100%]
#
#   ============================== 8 passed in 3.57s ==============================
#
# Against inngest/inngest:v1.44.0 in the `aeris-inngest` container, started by docker-compose.yml with
# `--no-discovery --no-poll`; /dev reports autodiscover=False, urls=[], poll=False.
#
# Checked by mutation. Two of the three are *server* mutations rather than code ones, because the claims
# they check are about how the dev server was started, not about what this repository contains:
#
#   A (code)   read-back queries an event name never sent
#              -> test_an_event_sent_through_the_sdk_can_be_read_back_off_the_bus         FAILED
#   B (server) started with `-u http://localhost:3000/api/inngest`, an app URL to sync
#              -> test_no_functions_are_registered_yet_and_that_is_deliberate             FAILED
#   C (server) started with no flags at all, so autodiscover comes up True
#              -> test_app_discovery_is_off_because_there_is_no_app_to_discover           FAILED
#
# C was run because B did NOT fail the discovery test: passing `-u` turns autodiscover *off* while filling
# `urls`, so B alone would have left that assertion unproven and possibly vacuous. Measured values:
#
#   no flags                  autodiscover=True   urls=[]                          poll=True
#   -u <url>                  autodiscover=False  urls=['http://localhost:3000/…'] poll=True
#   --no-discovery --no-poll  autodiscover=False  urls=[]                          poll=False   <- ours
#
# The code was restored from a pre-mutation copy and byte-compared; the container was recreated from
# docker-compose.yml and its flags re-read from /dev.
