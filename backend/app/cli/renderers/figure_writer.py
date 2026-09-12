"""Pulls every rendered figure back out of storage and onto disk, so the whole capability is checkable in a terminal with no browser.

what  : `FigureWriter`, a fan-out consumer of `figure-ready` events, and `open_figure_writer()`.
where : Registered on the fan-out beside the journal writer and the trace renderer. Phase 2.3 replaces it
        with the frontend loading `imageUrl`, and neither knows about the other.
how   : Same relationship to figures that `journal_writer.py` has to the wire: it makes a Phase 2
        capability exercisable in Phase 1, before any route exists. `aeris ingest figures` prints the paths
        and an operator opens them.

        **It downloads rather than being handed the bytes, and that is the point.** The image never travels
        on the stream (`api-contract.md` §6 rule 7) - the event carries `imageUrl` and metadata only. So
        this consumer does exactly what the frontend will do: take the identifiers off the event, fetch the
        object, and write what came back. That means a figure which uploaded badly, or under a key nobody
        can reconstruct, fails **here**, in Phase 1, rather than as a broken image in a browser in Phase 2.

        A failure is logged and skipped rather than raised. The fan-out detaches a consumer that throws
        (`services/sessions/fanout.py`), and losing a ten-minute analysis because a figure could not be
        written to disk would be the wrong trade by a wide margin.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from app.config import settings
from app.constants.storage import Bucket
from app.lib import storage
from app.schemas.events import AnalysisStreamEvent, FigureReadyEvent
from app.services.rendering.figures import figure_object_key

logger = logging.getLogger(__name__)


def figures_directory(run_id: str) -> Path:
    """`runs/<run_id>/figures/`. Beside the run's journal, so one run is one place on disk."""
    return settings.journal_directory / run_id / "figures"


class FigureWriter:
    """Writes every figure of one run to disk, fetching each from storage as the frontend would."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.directory = figures_directory(run_id)
        self.written: list[Path] = []

    async def __call__(self, event: AnalysisStreamEvent) -> None:
        """The fan-out consumer. Ignores every event that is not a figure."""
        if not isinstance(event, FigureReadyEvent):
            return

        # Derived through the renderer's own key function rather than parsed out of `imageUrl`: the URL is
        # a Phase 2 route, and reconstructing a storage key from a route is a coupling that breaks the
        # first time the route changes.
        suffix = event.image_url.rsplit(".", 1)[-1]
        object_key = figure_object_key(event.run_id, event.figure_id, suffix)

        try:
            payload = await storage.get_object(Bucket.FIGURES, object_key)
        except Exception:
            logger.exception(
                "figure could not be fetched from storage; the run continues",
                extra={"run_id": self.run_id, "figure_id": event.figure_id, "object_key": object_key},
            )
            return

        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / f"{event.figure_id}.{suffix}"
        destination.write_bytes(payload)
        self.written.append(destination)

        logger.info(
            "figure written",
            extra={
                "run_id": self.run_id, "figure_id": event.figure_id,
                "kind": event.kind.value, "path": str(destination), "bytes": len(payload),
            },
        )


@asynccontextmanager
async def open_figure_writer(run_id: str) -> AsyncIterator[FigureWriter]:
    """Collect a run's figures for the lifetime of the block, and report what was written."""
    writer = FigureWriter(run_id)
    try:
        yield writer
    finally:
        logger.info(
            "figures written",
            extra={"run_id": run_id, "count": len(writer.written), "directory": str(writer.directory)},
        )
