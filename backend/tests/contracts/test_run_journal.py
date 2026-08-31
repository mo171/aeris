"""Proves the run journal is already wire-shaped: every line of a real run validates against the frontend's own schemas.

what  : A real probe run, journalled to disk, with every line validated against
        `analysisStreamEventSchema` from the vendored contracts.
where : `tests/contracts/`, not `tests/integration/`, because what it checks is the contract rather than
        the plumbing - and because it needs no Docker, like everything else in this directory.
how   : **This is the fifth statement of the Phase 1.0 gate, and it is the one that makes Phase 2 a
        transport swap rather than a rewrite.** `api-contract.md` §3: "In Phase 1 these are exactly the
        objects the CLI prints and journals."

        `tests/contracts/test_stream_events.py` validates *hand-built* events, which proves the models are
        right. This validates the events **a run actually produced**, which is a different claim: it covers
        the serialisation path, the journal writer, the ordering, and everything the fan-out does in
        between. A model can be correct and still reach the file wrong.

        The distinction matters because the failure it catches is invisible until Phase 2. A journal full
        of `run_id` instead of `runId` looks completely fine in a terminal, replays perfectly, and is
        rejected wholesale the first time a browser reads it.
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from app.cli.renderers.journal_writer import journal_path, open_journal
from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.constants.intents import Intent
from app.services.pipeline.checkpointer import open_checkpointer
from app.services.pipeline.graphs.probe import build_probe_graph
from app.services.pipeline.memory_store import open_memory_store
from app.services.sessions.fanout import EventFanout
from app.services.sessions.session import open_session

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
ANALYSIS_UNION = CONTRACTS["features/investigation/schemas/analysis.schema.ts"]["analysisStreamEventSchema"]

# Format checking on, so `date-time` is enforced rather than advisory - the `Z`-suffix rule 0.7 measured.
UNION_VALIDATOR = Draft202012Validator(
    ANALYSIS_UNION, format_checker=Draft202012Validator.FORMAT_CHECKER
)


async def journal_one_real_run(query: str) -> list[dict[str, Any]]:
    """Run the probe graph for real and return its journal, parsed as raw JSON.

    Read back as raw JSON rather than through `read_journal()` on purpose. `read_journal` parses through
    the same Pydantic models that wrote the file, so it would agree with a wrong file - the whole point
    here is to hand the bytes to a validator that knows nothing about our models.
    """
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = build_probe_graph().compile(checkpointer=checkpointer, store=store)

        async with open_session() as session:
            fanout = EventFanout()
            handle = await session.start(
                graph=graph,
                query=query,
                intent=Intent.CHANGE_DETECT,
                fanout=fanout,
                extra_state={"probe_pause_seconds": 0.0},
            )
            async with open_journal(handle.run_id) as journal:
                fanout.register("journal", journal)
                await handle.wait()

            path = journal_path(handle.run_id)

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def test_every_line_of_a_real_run_validates_against_the_frontend_union(
    isolated_pipeline_paths: Path,
) -> None:
    """**Gate 5.** Not a fixture, not a hand-built event - the file a real run left behind."""
    lines = await journal_one_real_run("Did the built-up area increase?")

    assert lines, "the run journalled nothing"
    for index, payload in enumerate(lines):
        errors = sorted(UNION_VALIDATOR.iter_errors(payload), key=str)
        assert not errors, f"journal line {index + 1} ({payload.get('type')}) is not a valid event: {errors}"


async def test_the_journal_is_camel_case_throughout(isolated_pipeline_paths: Path) -> None:
    """No snake_case key survives anywhere in the file, at any nesting depth.

    The union validator above would catch a wrong *required* key, but JSON Schema permits extra
    properties by default - so a payload carrying both `runId` and `run_id` validates. This is the check
    that says the boundary rule held rather than merely that the required fields were present.
    """
    lines = await journal_one_real_run("anything")

    def every_key(payload: Any) -> list[str]:
        if isinstance(payload, dict):
            return [key for k, v in payload.items() for key in [k, *every_key(v)]]
        if isinstance(payload, list):
            return [key for item in payload for key in every_key(item)]
        return []

    offenders = sorted({key for payload in lines for key in every_key(payload) if "_" in key})
    assert not offenders, (
        f"these journal keys are snake_case: {offenders}. Something serialised without `by_alias=True` - "
        "see `app/schemas/events/base.py`."
    )


async def test_the_journal_timestamps_carry_their_z(isolated_pipeline_paths: Path) -> None:
    """`startedAt` ends in `Z`, which is what makes `mode="json"` part of the contract.

    Pinned on a real run because the three ways to serialise the same instant disagree, and only one of
    them is accepted: `.isoformat()` gives `+00:00` and is rejected, the default dump mode gives a
    `datetime` object that is not a string at all.
    """
    lines = await journal_one_real_run("anything")
    start = next(line for line in lines if line["type"] == "run-start")

    assert start["startedAt"].endswith("Z")


async def test_the_journal_opens_with_run_start_and_closes_with_a_terminal_event(
    isolated_pipeline_paths: Path,
) -> None:
    """The envelope is the journal's own structure, and replay depends on it.

    A journal with no terminal event is a run whose outcome nobody recorded - which is exactly the shape a
    single-task design produces when it is hard-cancelled, and the reason `run_handle.py` emits terminal
    events from a task that is never cancelled itself.
    """
    lines = await journal_one_real_run("anything")

    assert lines[0]["type"] == "run-start"
    assert lines[-1]["type"] in {"run-complete", "run-error"}
    assert all(line["runId"] == lines[0]["runId"] for line in lines), "one journal holds exactly one run"
