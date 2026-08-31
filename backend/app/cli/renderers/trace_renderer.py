"""Draws the live S1-S20 trace in the terminal, because a run that shows nothing until it finishes is indistinguishable from a hang.

what  : `TraceRenderer`, a fan-out consumer that keeps a rich `Live` table of the trace, the streamed
        answer, and the run's terminal state.
where : Registered second on the fan-out by `cli/run.py` - after the journal, because the journal is
        provenance and this is decoration. Phase 2.3 replaces it with an SSE encoder without either one
        knowing about the other.
how   : This is the Phase 1 rendering of what the frontend's execution trace panel will draw, and it is
        built against the same rule (`api-contract.md` §3.1): a step arrives `running`, then arrives again
        `completed`, **keyed on its id**, and the second replaces the first rather than appending. Getting
        that wrong here would produce a terminal that looks fine and a frontend that shows every stage
        twice, discovered in Phase 2.

        **`Live` with one table, not `print` per event.** A stage that reports `running` and then
        `completed` is two events about the same row; printing them is a log, and the operator has to
        reconstruct the current state by reading upward. Redrawing one table is what makes the trace
        legible, and it is the difference between a progress display and a transcript.

        **Every value is `escape`d.** rich reads `[local]` as a style tag and prints nothing at all - the
        `aeris version` command shipped that bug in 0.6. A stage detail is model-generated text from 1.7
        onwards, so it will eventually contain square brackets.

        **The renderer owns no state the run needs.** It can be detached mid-run by the fan-out (a broken
        terminal must not kill an analysis) and the run continues to completion with its journal intact.
"""

import logging

from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from app.constants.statuses import TraceStepState
from app.schemas.events import (
    AnalysisStreamEvent,
    AnalysisTraceStep,
    AnswerTokenEvent,
    RunCompleteEvent,
    RunErrorEvent,
    RunStartEvent,
    TraceStepEvent,
)

logger = logging.getLogger(__name__)

# What each state looks like at a glance. The symbol carries the information the colour does, so the trace
# is still readable piped to a file or on a terminal without colour. ASCII only: a run redirected to a file
# on Windows encodes with the console code page, and a `·` becomes a replacement character in the record.
STATE_APPEARANCE: dict[TraceStepState, tuple[str, str]] = {
    TraceStepState.PENDING: (".", "dim"),
    TraceStepState.RUNNING: ("*", "yellow"),
    TraceStepState.COMPLETED: ("+", "green"),
    TraceStepState.FAILED: ("x", "red"),
    TraceStepState.SKIPPED: ("-", "dim"),
}


class TraceRenderer:
    """Keeps one live table of the run and redraws it as events arrive."""

    def __init__(self, console: Console) -> None:
        self._console = console
        self._live: Live | None = None
        # Insertion-ordered, keyed by step id. The key is what makes the second emission of a step replace
        # the first instead of appending a row - the same contract the frontend's panel is written against.
        self._steps: dict[str, AnalysisTraceStep] = {}
        self._answer: list[str] = []
        self._header = ""
        self._footer: Text | None = None

    def __enter__(self) -> TraceRenderer:
        self._live = Live(self._render(), console=self._console, refresh_per_second=8, transient=False)
        self._live.__enter__()
        return self

    def __exit__(self, *exception: object) -> None:
        if self._live is not None:
            self._live.update(self._render())
            self._live.__exit__(*exception)  # type: ignore[arg-type]
            self._live = None

    async def __call__(self, event: AnalysisStreamEvent) -> None:
        """The fan-out consumer. Async because the fan-out awaits; the work itself is a redraw."""
        match event:
            case RunStartEvent():
                self._header = f"{event.run_id}  |  {event.intent.value}"
            case TraceStepEvent():
                self._steps[event.step.id] = event.step
            case AnswerTokenEvent():
                self._answer.append(event.text)
            case RunCompleteEvent():
                confidence = "not stated" if event.confidence is None else f"{event.confidence:.0%}"
                self._footer = Text(
                    f"complete in {event.total_duration_ms} ms  |  confidence {confidence}", style="green"
                )
            case RunErrorEvent():
                self._footer = Text(event.message, style="red")

        if self._live is not None:
            self._live.update(self._render())

    def _render(self) -> Table:
        """The whole display, rebuilt from the events seen so far."""
        table = Table(title=escape(self._header) if self._header else None, expand=False)
        table.add_column("", width=1)
        table.add_column("stage", style="cyan", width=5)
        table.add_column("detail", overflow="fold")
        table.add_column("ms", justify="right", width=7)

        for step in self._steps.values():
            symbol, style = STATE_APPEARANCE[step.state]
            table.add_row(
                Text(symbol, style=style),
                step.stage_code.value,
                escape(step.detail or ""),
                "" if step.duration_ms is None else str(step.duration_ms),
            )

        if self._answer:
            table.add_section()
            table.add_row("", "", escape(" ".join(self._answer)), "")

        if self._footer is not None:
            table.add_section()
            table.add_row("", "", self._footer, "")

        return table
