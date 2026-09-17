"""Turns the router's plan into the plan the operator approves: the steps are the router's, the words are the model's, checked.

what  : `build_plan(request, steps, *, model) -> (AnalysisPlan, source)`, `apply_approval(plan, enabled_ids)`.
where : `agents/graph.py`'s plan node, before `interrupt()`. Phase 2's `/plan` route returns the same
        object.
how   : PDF p.24 again: the pipeline is chosen by a table, so the plan's *steps* are not the model's to
        write. What the model writes is the summary and one description per step - the prose an
        operator reads before striking a step out - and the prose is checked: exactly as many
        descriptions as steps, and no numeral anywhere, because nothing has been measured yet and "the
        three ships" before counting is a number nobody computed. A failed check, or no model, is the
        template: the router's own words per step, which are always correct and never eloquent.

        `apply_approval` is the only mutation an operator can make: the same steps come back with
        `isEnabled` set from the ids they kept. A step that is not in the plan cannot be enabled.
"""

import logging

from pydantic import BaseModel, Field

from app.agents.state import StepRecord
from app.constants.vlm import NUMERAL_PATTERN
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.schemas.agent import NO_MODEL, PLAN_STAGES, AnalysisPlan, AnalysisPlanStep
from app.services.prompts.agent import AGENT_SYSTEM_PROMPT, PLANNER_TEMPLATE

logger = logging.getLogger(__name__)


class PlanProse(BaseModel):
    summary: str = Field(description="One sentence for the operator.")
    step_descriptions: list[str] = Field(description="One sentence per step, in the order given.")


def template_title(step: StepRecord) -> str:
    subject = ", ".join(step.get("objects") or ()) or step.get("spectral_phrase") or ", ".join(step.get("unknown_objects") or ()) or "the scene"
    verb = {
        "INDEX_QUERY": "Measure", "DETECT": "Count" if step.get("wants_count") else "Detect", "GROUND": "Locate", "SEGMENT": "Segment",
        "CHANGE_DETECT": "Map change in", "CHANGE_VQA": "Assess change in", "CROSS_MODAL": "Fuse optical and SAR over",
        "SCENE_VQA": "Read", "EVIDENCE_RECALL": "Recall evidence for",
    }[step["intent"]]
    return f"{verb} {subject}"


def template_description(step: StepRecord) -> str:
    tool = step.get("tool") or "the evidence store"
    if step.get("refusal"):
        return f"Cannot run: {step['refusal']}"
    how = step.get("rule") if step.get("method") == "rule" else f"nearest labelled questions ({step.get('method')})"
    return f"{step['intent']} with {tool}; routed by {how}."


def template_plan(steps: list[StepRecord]) -> AnalysisPlan:
    from app.constants.fleet import FLEET
    plan_steps = []
    for step in steps:
        tool = step.get("tool")
        model_val = {"id": tool, "version": FLEET[tool].version} if tool and tool in FLEET else None
        plan_steps.append(
            AnalysisPlanStep(
                id=step["id"], title=template_title(step), description=template_description(step), model=model_val,
                stage_code=PLAN_STAGES[step["intent"]], is_enabled=not step.get("refusal"),
            )
        )
    summary = f"{len(plan_steps)} step{'s' if len(plan_steps) != 1 else ''}: " + " -> ".join(step.title for step in plan_steps)
    return AnalysisPlan(id=new_identifier(IdentifierPrefix.PLAN), summary=summary, steps=plan_steps)


def verify_prose(prose: PlanProse, plan: AnalysisPlan) -> str | None:
    """`None` when the prose may be shown; otherwise why not. Numerals the template already states - a
    refusal's "8 pixels at 10 m" - may be repeated; any other is a number nobody has measured."""
    if len(prose.step_descriptions) != len(plan.steps):
        return f"{len(prose.step_descriptions)} descriptions for {len(plan.steps)} steps"
    permitted = set(NUMERAL_PATTERN.findall(plan.summary + " " + " ".join(step.title + " " + step.description for step in plan.steps)))
    if numerals := [n for n in NUMERAL_PATTERN.findall(prose.summary + " " + " ".join(prose.step_descriptions)) if n not in permitted]:
        return f"numerals before anything was measured: {numerals}"
    return None


async def build_plan(request: str, steps: list[StepRecord], *, model) -> tuple[AnalysisPlan, str]:  # noqa: ANN001 - LangChain chat model or None
    """The plan, and who wrote its prose: `llm` or `template`."""
    plan = template_plan(steps)
    if model is None or not plan.steps:
        return plan, "template"
    prompt = PLANNER_TEMPLATE.format(
        request=request,
        steps="\n".join(f"{index}. {step.title} - {step.description}" for index, step in enumerate(plan.steps, start=1)),
    )
    try:
        prose = await model.with_structured_output(PlanProse).ainvoke([("system", AGENT_SYSTEM_PROMPT), ("human", prompt)])
    except Exception as error:  # noqa: BLE001 - the template plan is always available
        logger.warning("plan prose failed; template plan used", extra={"reason": str(error)})
        return plan, "template"
    reason = verify_prose(prose, plan)
    if reason is not None:
        logger.warning("plan prose rejected; template plan used", extra={"reason": reason})
        return plan, "template"
    steps = [step.model_copy(update={"description": description.strip()}) for step, description in zip(plan.steps, prose.step_descriptions, strict=True)]
    return AnalysisPlan(id=plan.id, summary=prose.summary.strip(), steps=steps), "llm"


def apply_approval(plan: AnalysisPlan, enabled_ids: list[str] | None) -> AnalysisPlan:
    """The operator's only edit: which steps stay enabled. `None` keeps the plan as proposed."""
    if enabled_ids is None:
        return plan
    keep = set(enabled_ids)
    return plan.model_copy(update={"steps": [step.model_copy(update={"is_enabled": step.is_enabled and step.id in keep}) for step in plan.steps]})
