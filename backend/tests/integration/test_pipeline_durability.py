"""Measures what actually survives a process being killed mid-run, and pins the durability setting to that measurement.

what  : A hard-kill test - a real child process, terminated without cleanup partway through a stage - plus
        the three-way comparison that chose `PIPELINE_DURABILITY=sync`.
where : `tests/integration/`. Needs no Docker; it needs a second process and a temporary directory.
how   : The roadmap's 1.0 gate says "a run killed mid-pipeline resumes from its last checkpoint, not from
        the beginning". A graceful `asyncio` cancellation does **not** test that: LangGraph flushes its
        pending writes on the way out, so all three durability modes look identical under it. That was
        measured first, and it is why this test kills a real process instead.

        `Popen.kill()` on Windows is `TerminateProcess`, and on POSIX it is `SIGKILL`. Either way no
        `finally` runs, no `atexit` fires, and no connection is closed - which is the point. What is left
        in the database is exactly what had been committed before the process stopped existing.

        The measured result, recorded at the bottom of this file, is what `config.py` cites:

            exit   -> ZERO checkpoints. The entire run is recomputed.
            async  -> committed, but in a background write whose window can be missed.
            sync   -> committed before the next node starts.

        A pipeline stage here is model inference measured in minutes and a SQLite commit is
        sub-millisecond, so `sync` is not a close decision. `async` only narrows the window rather than
        closing it, and `exit` is disqualified outright.
"""

import sqlite3
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

# Long enough that the parent can reliably kill the child inside it, short enough that a failure to kill
# does not hang the suite for a noticeable time.
CHILD_STAGE_SECONDS = 60

CHILD_PROGRAM = textwrap.dedent(
    """
    import asyncio, sys
    from operator import add
    from typing import Annotated, TypedDict

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.graph import END, START, StateGraph

    DURABILITY, DATABASE, STAGE_SECONDS = sys.argv[1], sys.argv[2], float(sys.argv[3])


    class State(TypedDict):
        done: Annotated[list[str], add]


    async def first(state: State) -> dict:
        await asyncio.sleep(0.05)
        return {"done": ["first"]}


    async def second(state: State) -> dict:
        # Printed only once the first node's update has been committed, so the parent kills the child at a
        # known point rather than after a guessed delay.
        print("READY", flush=True)
        await asyncio.sleep(STAGE_SECONDS)
        return {"done": ["second"]}


    async def main() -> None:
        async with AsyncSqliteSaver.from_conn_string(DATABASE) as saver:
            builder = StateGraph(State)
            builder.add_node("first", first)
            builder.add_node("second", second)
            builder.add_edge(START, "first")
            builder.add_edge("first", "second")
            builder.add_edge("second", END)
            graph = builder.compile(checkpointer=saver)
            async for _ in graph.astream(
                {"done": []}, {"configurable": {"thread_id": "t"}},
                stream_mode="updates", durability=DURABILITY,
            ):
                pass


    asyncio.run(main())
    """
)


def kill_a_run_midway(durability: str, working_directory: Path) -> Path:
    """Start a two-node run, wait until it is inside the second node, and kill the process outright."""
    program = working_directory / f"child_{durability}.py"
    program.write_text(CHILD_PROGRAM, encoding="utf-8")
    database = working_directory / f"{durability}.sqlite"

    process = subprocess.Popen(
        [sys.executable, str(program), durability, str(database), str(CHILD_STAGE_SECONDS)],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "READY", "the child never reached its second node"
        # No cleanup, no finally, no flush. Whatever is in the database is what was committed.
        process.kill()
    finally:
        process.wait(timeout=30)

    return database


# How long to keep retrying the read after the child has been killed. Measured, not guessed: the first
# read succeeds immediately about two runs in three, and fails with `disk I/O error` on the other one.
READ_RETRY_SECONDS = 5.0
READ_RETRY_INTERVAL_SECONDS = 0.1


def committed_checkpoints(database: Path) -> int:
    """How many checkpoints survived, read with a plain sqlite3 connection.

    Read synchronously and directly rather than through LangGraph's saver, because the saver's `setup()`
    writes to the database it is inspecting - and a reader that repairs what it is measuring measures
    nothing.

    **The retry is a Windows file-handle race, not a data property, and it is written so it cannot hide
    one.** `TerminateProcess` returns before the OS has finished releasing the dead process's handles on
    the `-wal` and `-shm` files, so a read issued immediately afterwards can raise `disk I/O error` while
    SQLite tries to recover the write-ahead log. That was diagnosed rather than assumed: the same read a
    tenth of a second later returns the checkpoints, and the failure reproduces on roughly one run in
    three.

    A zero is only ever returned by a **successful** read. If the database never becomes readable the last
    error is raised, so a genuinely broken file fails the test instead of being counted as "nothing was
    committed" - which is the assertion `test_exit_durability_would_lose_the_whole_run` makes, and the one
    a silent zero would falsify.
    """
    deadline = time.monotonic() + READ_RETRY_SECONDS
    while True:
        try:
            connection = sqlite3.connect(database)
            try:
                return connection.execute("SELECT count(*) FROM checkpoints").fetchone()[0]
            finally:
                connection.close()
        except sqlite3.OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(READ_RETRY_INTERVAL_SECONDS)


@pytest.mark.parametrize("durability", ["sync", "async"])
async def test_a_hard_killed_run_leaves_a_checkpoint_to_resume_from(
    durability: str, isolated_pipeline_paths: Path
) -> None:
    """**Gate 2.** A process killed mid-stage leaves the completed stages committed.

    Both modes the backend would consider are checked, because the point is not that one number is bigger
    - it is that the setting in `config.py` is chosen from a measurement rather than from documentation.
    """
    database = kill_a_run_midway(durability, isolated_pipeline_paths)

    assert committed_checkpoints(database) > 0, (
        f"durability={durability!r} lost everything when the process was killed; "
        "the interrupted run would restart from S1"
    )


async def test_exit_durability_would_lose_the_whole_run(isolated_pipeline_paths: Path) -> None:
    """Why `exit` is not the setting, demonstrated rather than asserted.

    This is the measurement `config.py` cites. It is a test rather than a comment because "we chose sync
    for a reason" decays into folklore within a phase or two, and the reason is one line of evidence away.
    """
    database = kill_a_run_midway("exit", isolated_pipeline_paths)

    assert committed_checkpoints(database) == 0, (
        "durability='exit' unexpectedly committed a checkpoint on a hard kill. If LangGraph has changed "
        "this, the reasoning in config.py and checkpointer.py needs revisiting rather than the assertion "
        "being relaxed."
    )


async def test_the_configured_durability_is_the_one_that_was_measured() -> None:
    """The setting and the evidence must not drift apart.

    Without this, someone changes `PIPELINE_DURABILITY` to `exit` for speed, every test above still
    passes - they parametrise their own values - and the reason recorded in `config.py` quietly becomes
    false.
    """
    from app.config import settings

    assert settings.pipeline_durability == "sync", (
        "config.py's default was measured. Changing it means re-running the comparison in this file and "
        "rewriting the reasoning there, not just the value."
    )


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/integration/test_pipeline_durability.py -q                   2026-08-31
#
#   ....                                                                     [100%]
#   4 passed in 6.02s
#
# The measurement `config.py` and `checkpointer.py` both cite. A two-node run, the child process killed with
# TerminateProcess the moment it entered its second node, and the database read afterwards:
#
#   durability=exit   -> checkpoints=0   writes=0     everything lost; the run restarts from S1
#   durability=async  -> checkpoints=3   writes=4
#   durability=sync   -> checkpoints=3   writes=4
#
# `exit` is disqualified outright. `async` and `sync` are indistinguishable at this granularity because the
# background write had time to land - the difference between them is a race whose window this test does not
# try to measure, and `sync` closes it rather than narrowing it. A stage here is model inference measured in
# minutes; a SQLite commit is sub-millisecond.
#
# Two things were measured before this test was written, and both changed how it is built:
#
#   1. A graceful asyncio cancellation does NOT distinguish the three modes. LangGraph flushes pending
#      writes on the way out, so all three leave the same state and `next=('second',)`. Testing durability
#      with `task.cancel()` would have passed against `exit` and proved nothing. Hence a real killed process.
#
#   2. `sqlite3.connect` immediately after the kill raises `disk I/O error` on roughly one run in three -
#      Windows has not finished releasing the dead process's handles on the -wal and -shm files. Diagnosed
#      by retrying: the same read a tenth of a second later returns the checkpoints. The retry in
#      `committed_checkpoints` is bounded and only ever returns a count from a *successful* read, so a
#      genuinely unreadable database fails the test rather than being counted as zero.
