"""Writes the run's provenance to disk as it happens, so a run that dies halfway still leaves a readable record.

what  : `JournalWriter`, an append-only consumer of the event stream, and `read_journal()` for reading one
        back.
where : Registered first on the fan-out by `cli/run.py`. Read by `aeris run --replay`, and by
        `tests/contracts/test_run_journal.py`, which validates it against the frontend's schemas.
how   : One JSON object per line, in the order the events were emitted, each one exactly the object Phase
        2 will put on the wire (`api-contract.md` §3: "In Phase 1 these are exactly the objects the CLI
        prints and journals"). That equivalence is what makes Phase 2 a transport swap - and it is checked,
        not asserted: the journal of a real run is validated against the vendored Zod contracts.

        **JSONL, not JSON.** A run killed at S13 leaves a file whose every line is complete and parseable.
        The same run written as a JSON array leaves an unclosed bracket, which is unreadable exactly when
        the record matters most.

        **Flushed after every line.** The cost is one `write` syscall per event against a producer whose
        steps take minutes; the alternative is a killed process losing the last few events, which are the
        ones describing what it was doing when it died.

        **Nothing but wire events goes in.** No header, no metadata line, no timestamps of our own. A
        journal that mixes envelope with content cannot be validated against the frontend's union without
        the validator first being taught to skip lines, and everything a header would carry is already in
        `run-start`.

        Files land in `settings.journal_directory`, which `.gitignore` excludes - a run journal is an
        artefact of an execution, not source.

        **Known hazard, deliberately not solved in 1.0: nothing stops two processes appending to the same
        run's journal.** Found by accident while demonstrating the resume gate - a `kill -9` reached the
        `uv` wrapper rather than the Python process, the orphan finished its stage half a minute later, and
        its events interleaved with the resumed run's in one file. The application behaved correctly; the
        record did not, and reading it afterwards is genuinely confusing.

        It is left open because in Phase 1 a run is one CLI process and the situation cannot arise without
        an orphan. **Phase 2.5 makes it real** - several Inngest workers, any of which could be handed the
        same run - and the fix belongs there, where the Redis lock from 0.3 already exists and the
        checkpointer has moved to Postgres. What identified it here is that two attempts at one stage carry
        two different `stp_` ids, which is exactly how a reader tells them apart.
"""

import json
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TextIO

from app.config import settings
from app.constants.pipeline import JOURNAL_FILE_SUFFIX
from app.lib.exceptions import ResourceNotFoundError
from app.schemas.events import AnalysisStreamEvent, parse_event, serialise_event

logger = logging.getLogger(__name__)


def journal_path(run_id: str) -> Path:
    """Where one run's journal lives. One file per run, named by the run id and nothing else."""
    return settings.journal_directory / f"{run_id}{JOURNAL_FILE_SUFFIX}"


class JournalWriter:
    """Appends every event of one run to `runs/<run_id>.jsonl`."""

    def __init__(self, run_id: str, handle: TextIO) -> None:
        self.run_id = run_id
        self.path = journal_path(run_id)
        self._handle = handle
        self.written_count = 0

    async def __call__(self, event: AnalysisStreamEvent) -> None:
        """The fan-out consumer. Writes one line and flushes it.

        The file write is sync inside an `async def`, and that is deliberate rather than an oversight
        (`code-standards.md` §7 asks for async where there is I/O). A line of JSON to a local file is a
        single buffered `write`, and `aiofiles` would move it to a thread-pool round trip that costs more
        than the write it replaces. The signature is async because the fan-out awaits its consumers, and
        because Phase 2.3's network consumer genuinely will be.
        """
        self._handle.write(json.dumps(serialise_event(event), separators=(",", ":")) + "\n")
        self._handle.flush()
        self.written_count += 1


@asynccontextmanager
async def open_journal(run_id: str) -> AsyncIterator[JournalWriter]:
    """Open a run's journal for the lifetime of the block.

    Opened in append mode, not write mode, so that resuming a run adds to its record rather than replacing
    it. A resumed run's journal is the whole history of that run across every process that worked on it,
    which is what provenance means - and truncating on resume would delete the evidence of the stages that
    already succeeded.
    """
    path = journal_path(run_id)
    with path.open("a", encoding="utf-8") as handle:
        writer = JournalWriter(run_id, handle)
        logger.debug("journal opened", extra={"run_id": run_id, "path": str(path)})
        try:
            yield writer
        finally:
            logger.info(
                "journal written", extra={"run_id": run_id, "events": writer.written_count, "path": str(path)}
            )


def read_journal(run_id: str) -> Iterator[AnalysisStreamEvent]:
    """Read a run's journal back, one typed event at a time.

    A generator so that replaying a long run does not load its whole journal into memory, and sync because
    it reads a local file line by line.

    A malformed or unknown line raises rather than being skipped. A journal this process cannot fully parse
    is one written by a different version of the contract, and replaying the part of it we happen to
    understand would present a partial record as a complete one.
    """
    path = journal_path(run_id)
    if not path.exists():
        raise ResourceNotFoundError(
            f"No journal for run {run_id}. Looked in {path}.", details={"runId": run_id, "path": str(path)}
        )

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield parse_event(json.loads(stripped))
            except Exception as error:
                raise ResourceNotFoundError(
                    f"Journal for {run_id} is unreadable at line {line_number}: {error}",
                    details={"runId": run_id, "line": line_number},
                ) from error
