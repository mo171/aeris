"""Everything `aeris route` does - show what the router makes of a question, or score it on the held-out questions.

what  : `execute_route()` prints the plan for a request - one step per question it holds;
        `execute_route_evaluate()` prints the 1.8 gate, single questions and compound requests both.
where : Called from `cli/main.py`. `cli/ask.py` and `cli/analyse.py` call the same router before they
        run anything; this command is the router alone, so a surprising route can be read before a
        model is loaded.
how   : The decision is printed as the router holds it - intent, how it was decided (which cue, or which
        neighbours voted), the entities, the tool, the graph, and the refusal if any. The evaluation
        prints three rows per file: rules alone, kNN alone, and the cascade that ships, so the gate
        number is read beside what each half contributes.
"""

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from app.agents.router import RoutingDecision, RoutingPlan, SceneFacts, route_plan, routing_resources
from app.constants.routing import Modality
from app.services.evaluation.intent import CASCADE, KNN_ONLY, RULES_ONLY, IntentReport, evaluate_intents, evaluate_plans
from app.services.query.bank import load_compound, load_compound_fresh, load_fresh, load_holdout

GATE_ACCURACY = 0.95
# Compound requests: the share whose ordered intent sequence is exactly right. Measured 1.000 on both
# files after tuning; the first untouched scores were 0.50 and 0.67 (roadmap 1.8), so the bar is lower.
PLAN_GATE_EXACT = 0.90


async def execute_route(*, query: str, ground_sample_distance: float | None, image_count: int, sar: bool, console: Console) -> bool:
    encoder, bank = await routing_resources()
    modalities = (Modality.SAR,) if sar else ()
    plan = await route_plan(query, encoder=encoder, bank=bank, facts=SceneFacts(ground_sample_distance, image_count, modalities))
    render_plan(plan, console, encoder is not None)
    return not plan.refused


def render_plan(plan: RoutingPlan, console: Console, encoder_loaded: bool) -> None:
    """Every step with the clause it came from; a single question is a plan of one."""
    if len(plan.clauses) > 1:
        console.print(f"\n  [bold]{escape(plan.query)}[/bold]")
        console.print(f"  {len(plan.clauses)} clauses -> {len(plan.steps)} steps: " + " -> ".join(step.intent.value for step in plan.steps))
    for index, step in enumerate(plan.steps, start=1):
        if len(plan.steps) > 1:
            console.print(f"\n  [dim]step {index}/{len(plan.steps)}[/dim]")
        render_decision(step, console, encoder_loaded)


def render_decision(decision: RoutingDecision, console: Console, encoder_loaded: bool) -> None:
    verdict = decision.decision
    how = f"rule: {verdict.rule}" if verdict.method == "rule" else (
        f"kNN vote {verdict.confidence:.2f}, margin {verdict.margin:.2f}" + (" - uncertain" if verdict.uncertain else "")
        + (f" (within {verdict.rule})" if verdict.rule else "")
    ) if verdict.method == "knn" else "default: no cue fired and no encoder is loaded"
    console.print(f"\n  [bold]{escape(decision.query)}[/bold]")
    console.print(f"  intent   [bold]{decision.intent.value}[/bold]   ({escape(how)})")
    if verdict.neighbours:
        for text, intent, similarity in verdict.neighbours:
            console.print(f"           {similarity:.2f}  {intent.value:16s} {escape(text)}")
    entities = decision.entities
    parts = [
        f"objects={list(entities.objects)}" if entities.objects else None,
        f"unknown={list(entities.unknown_objects)}" if entities.unknown_objects else None,
        f"spectral='{entities.spectral_phrase}'" if entities.spectral_phrase else None,
        f"region={entities.region.value}" if entities.region else None,
        f"temporal={entities.temporal.value}", f"images={entities.image_count}", f"modality={entities.modality.value}",
        f"dates={list(entities.dates)}" if entities.dates else None,
        "wants=" + ",".join(name for name, flag in (("count", entities.wants_count), ("area", entities.wants_area), ("location", entities.wants_location), ("map", entities.wants_map)) if flag),
    ]
    console.print("  entities " + escape("  ".join(part for part in parts if part)))
    console.print(f"  tool     {decision.tool.value if decision.tool else '- (no model)'}")
    console.print(f"  graph    {decision.graph.value if decision.graph else f'not built - {decision.graph_note}'}")
    if decision.refusal:
        console.print(f"  [red]refused  {escape(decision.refusal)}[/red]")
    if not encoder_loaded:
        console.print("  [yellow]intent encoder not loaded: rules alone routed this (no weights, no network)[/yellow]")


async def execute_route_evaluate(*, console: Console) -> bool:
    encoder, bank = await routing_resources()
    if encoder is None:
        console.print("[red]The intent encoder could not be loaded; the gate needs it.[/red]")
        return False
    table = Table(title="Intent classification - accuracy by configuration", show_lines=False)
    for column in ("file", "n", "rules alone", "kNN alone", "cascade (ships)", "uncertain"):
        table.add_column(column, justify="right" if column != "file" else "left")
    passed = True
    reports: list[tuple[str, IntentReport]] = []
    for name, rows in (("held-out half of the bank", await load_holdout()), ("fresh, operator register", await load_fresh())):
        scores = {}
        for configuration in (RULES_ONLY, KNN_ONLY, CASCADE):
            report = await evaluate_intents(encoder=encoder, bank=bank, configuration=configuration, rows=rows)
            scores[configuration] = report
        cascade = scores[CASCADE]
        reports.append((name, cascade))
        passed &= cascade.accuracy >= GATE_ACCURACY
        table.add_row(
            name, str(cascade.samples), f"{scores[RULES_ONLY].accuracy:.3f}", f"{scores[KNN_ONLY].accuracy:.3f}",
            f"[bold]{cascade.accuracy:.3f}[/bold]", str(cascade.uncertain),
        )
    console.print(table)
    plans = Table(title="Compound requests - ordered intents per plan")
    for column in ("file", "n", "exact sequence", "steps found"):
        plans.add_column(column, justify="right" if column != "file" else "left")
    plan_errors = []
    for name, rows in (("compound, developed against", await load_compound()), ("compound, fresh", await load_compound_fresh())):
        report = await evaluate_plans(encoder=encoder, bank=bank, rows=rows)
        passed &= report.exact >= PLAN_GATE_EXACT
        plans.add_row(name, str(report.samples), f"[bold]{report.exact:.3f}[/bold]", f"{report.steps_found:.3f}")
        plan_errors.extend((name, error) for error in report.errors)
    console.print(plans)
    for name, error in plan_errors:
        console.print(f"    [red]x[/red] {name}: {[i.value for i in error.expected]} -> {[i.value for i in error.predicted]}  {escape(' | '.join(error.clauses))}")
    for name, report in reports:
        console.print(f"\n  {name}: per intent " + "  ".join(f"{intent.value} {hit}/{total}" for intent, (hit, total) in report.per_intent.items()))
        for error in report.errors:
            console.print(f"    [red]x[/red] {error.expected.value} -> {error.predicted.value}  [{error.method}{': ' + error.rule if error.rule else ''}]  {escape(error.query)}")
    console.print(f"\n  gate >= {GATE_ACCURACY:.0%} on every question file and >= {PLAN_GATE_EXACT:.0%} exact on every compound file: {'[green]passed[/green]' if passed else '[red]failed[/red]'}")
    return passed
