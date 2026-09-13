"""Everything `aeris agent` does - one spoken request through the agent: the plan shown and approved, every step run, one answer.

what  : `execute_agent()`, the async function behind the Typer command in `cli/main.py`; `write_run_folder()`.
where : Called from `cli/main.py`. Phase 2's `/assistant/stream` drives the same `agents/run.py::converse`
        with a streaming approver instead of a terminal prompt.
how   : The approver prints the plan the graph paused on and, unless `--yes`, asks which steps to keep
        (`--skip step-2` strikes one out without a prompt, for scripts). Then the trace and the answer.
        `--thread` continues a conversation, so "what did you find earlier" recalls the previous request's
        claims. Everything the run produced is written under `runs/<request_id>/agent/` beside the graph
        runs it made: the plan, the results, the answer, the trace and the interface commands - the
        record the operator reads to decide whether a success was one.
"""

import json
import logging
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape

from app.agents.run import AgentOutcome, converse
from app.config import settings
from app.constants.raster import ProcessingLevel

logger = logging.getLogger(__name__)


async def execute_agent(
    *, request: str, console: Console, scene: Path | None, images: list[Path], sar: list[bool], level: ProcessingLevel | None,
    yes: bool, skip: list[str], thread: str | None, ground_sample_distance: float | None,
) -> AgentOutcome:
    async def approver(plan: dict[str, Any], source: str) -> list[str] | None:
        render_plan(plan, source, console)
        kept = [step["id"] for step in plan["steps"] if step["isEnabled"] and step["id"] not in set(skip)]
        if skip:
            console.print(f"  struck out: {', '.join(skip)}")
        elif not yes:
            answer = typer.prompt("  run these steps? (enter to run all, or step ids to keep, e.g. step-1 step-3, or 'none')", default="all")
            if answer.strip().lower() == "none":
                kept = []
            elif answer.strip().lower() != "all":
                kept = [step_id for step_id in answer.split() if step_id in kept]
        return kept

    outcome = await converse(
        request, approver=approver, agent_id=thread, scene_directory=scene, image_paths=images, sar=sar, declared_level=level,
        ground_sample_distance=ground_sample_distance,
    )
    render_outcome(outcome, console)
    folder = write_run_folder(outcome)
    console.print(f"\n  record   {escape(str(folder))}", soft_wrap=True)
    return outcome


def render_plan(plan: dict[str, Any], source: str, console: Console) -> None:
    console.print(f"\n  [bold]plan[/bold] {escape(plan['id'])}   prose by {source}")
    console.print(f"  {escape(plan['summary'])}")
    for step in plan["steps"]:
        mark = "[green]on [/green]" if step["isEnabled"] else "[red]off[/red]"
        console.print(f"  {mark} {step['id']:8s} {step['stageCode']:4s} {step['modelId']:18s} [bold]{escape(step['title'])}[/bold]")
        console.print(f"                {escape(step['description'])}")


def render_outcome(outcome: AgentOutcome, console: Console) -> None:
    console.print()
    for step in outcome.trace:
        duration = f"{step['durationMs']} ms" if step.get("durationMs") is not None else ""
        console.print(f"  {step['state']:9s} {escape(step['label']):34s} {duration:>9s}  {escape(step.get('detail') or '')}")
    console.print(f"\n  [bold]{escape(outcome.answer)}[/bold]\n")
    console.print(f"  answer by {outcome.state.get('answer_source')}   thread {outcome.agent_id}")
    for command in outcome.state.get("ui_commands") or []:
        console.print(f"  ui-command {command['commandId']} {json.dumps(command['params'])}")


def write_run_folder(outcome: AgentOutcome) -> Path:
    """The request's record on disk, beside the graph runs it made, for the operator to audit."""
    folder = settings.journal_directory / outcome.request_id / "agent"
    folder.mkdir(parents=True, exist_ok=True)
    record = {
        "agentId": outcome.agent_id, "requestId": outcome.request_id, "request": outcome.state.get("request"),
        "clauses": outcome.state.get("clauses"), "steps": outcome.state.get("steps"), "plan": outcome.plan,
        "planSource": outcome.state.get("plan_source"), "approvedStepIds": outcome.state.get("approved_step_ids"),
        "results": outcome.results, "answer": outcome.answer, "answerSource": outcome.state.get("answer_source"),
        "uiCommands": outcome.state.get("ui_commands"), "trace": outcome.trace,
        "languageModel": {"provider": settings.llm_provider, "model": settings.llm_model} if settings.llm_provider != "none" else None,
    }
    (folder / "record.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    (folder / "answer.txt").write_text(outcome.answer + "\n", encoding="utf-8")
    (folder / "README.md").write_text(_readme(outcome, record), encoding="utf-8")
    return folder


def _readme(outcome: AgentOutcome, record: dict[str, Any]) -> str:
    """What to look at to decide whether this run was the success its exit code claims."""
    lines = [
        f"# Agent request {outcome.request_id}", "", f"**Request:** {record['request']}", "",
        f"Thread `{outcome.agent_id}` - language model: {record['languageModel'] or 'none'} - plan prose by `{record['planSource']}` - answer by `{record['answerSource']}`.", "",
        "## What to check", "",
        "1. `record.json` -> `clauses`: is that how you would split the request? `steps[*].intent/tool/refusal`: is each clause routed to the right specialist, and is every refusal a reason you accept?",
        "2. `plan`: the steps the operator saw before anything ran; `approvedStepIds`: what was kept.",
        "3. `results[*].claims[*].metrics`: every number in `answer.txt` must be one of these values, formatted as the claim formats it. Any other numeral in the answer is a defect.",
        "4. For each step with a `run_id`, the graph run's own record is beside this folder: `../../<run_id>/provenance.json` (inputs hashed, engines and versions), `../../<run_id>/evidence-graph.json`, `../../<run_id>/figures/` (what the model read), and the journal `../../<run_id>.jsonl` (every event, in order).",
        "5. `uiCommands`: each names a claim or evidence id that exists in `results` - check it does.",
        "", "## Steps", "",
    ]
    for result in outcome.results:
        lines.append(f"- **{result['step_id']}** {result['intent']} via `{result.get('tool') or 'evidence-store'}` - {result['state']}: {result.get('detail') or ''}")
        for claim in result.get("claims") or []:
            metrics = ", ".join(f"{m['label']}={m['value']}{m['unit']}" for m in claim.get("metrics") or [])
            lines.append(f"  - {claim['text']}" + (f"  [{metrics}]" if metrics else ""))
        if result.get("run_id"):
            lines.append(f"  - graph run `{result['run_id']}`: journal `{result.get('journal')}`; figures: {', '.join(result.get('figures') or []) or 'none'}")
    lines += ["", "## Answer", "", record["answer"], ""]
    return "\n".join(lines)
