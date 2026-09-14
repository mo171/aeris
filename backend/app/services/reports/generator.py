"""Builds the canonical research narrative from validated investigation facts.

what  : Creates the deterministic dossier, asks the configured LLM to author the reader prose, and validates
    only the hard evidence boundaries before accepting the editorial draft.
where : Called once after a completed pipeline run; all report surfaces consume the returned document.
how  : Deterministic text remains the fallback for provider failure or a hard evidence violation. Style,
    terminology and refusal placement are soft editorial guidance and are logged rather than discarded.
"""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.constants.reports import REPORT_SECTION_ORDER, ReportSection
from app.schemas.report import (
    EditorialReportDraft,
    EvidenceNarrative,
    KeyFact,
    ModelNarrative,
    QuestionAnswer,
    ReportDocument,
    ReportFigure,
    ReportFinding,
    ReportSectionDocument,
)
from app.services.prompts.report import REPORT_EDITORIAL_PROMPT

logger = logging.getLogger(__name__)
_NUMBER = re.compile(r"(?<![A-Za-z_])[-+]?\d[\d,.]*(?:%|\b)")
_INTERNAL = re.compile(r"(?:run|fig|clm|stp|lyr|ev)_[A-Za-z0-9_]+|S[12][A-Z0-9_]+", re.IGNORECASE)
_AUDIT_VOICE = re.compile(
    r"\b(?:the report compares|final page records|were analysed|was analysed|we analysed)\b",
    re.IGNORECASE,
)
_BODY_REFUSAL = re.compile(r"\b(?:cannot produce a fused conclusion|requires a third observation)\b", re.IGNORECASE)
_SCIENTIFIC_ASSERTIONS = frozenset({"cloud", "shadow", "nodata", "atmospheric", "calibrated", "terrain", "registered", "registration"})
_CONTEXTUAL_ASSERTIONS = frozenset({"synthesis map", "cross-sensor"})


class ReportEditorialUnavailable(RuntimeError):
    """Raised when a customer-facing report cannot get an accepted editorial draft."""


def _get(data: dict[str, Any], name: str, default: Any = None) -> Any:
    camel = "".join((name.split("_")[0], *[part.title() for part in name.split("_")[1:]]))
    return data.get(name, data.get(camel, default))


def _claims(values: dict[str, Any]) -> list[dict[str, Any]]:
    claims = list(_get(values, "claims", []) or [])
    return sorted(claims, key=lambda item: (not bool(_get(item, "is_primary", False)), str(_get(item, "id", ""))))


def _reader_text(text: str, values: dict[str, Any]) -> str:
    for record in _get(values, "input_records", []) or []:
        scene_id = str(_get(record, "scene_id", ""))
        modality = str(_get(record, "modality", "observation")).lower()
        label = "the radar observation" if modality == "sar" else "the optical observation"
        if scene_id:
            text = text.replace(scene_id, label)
    return text.strip()


def _sentence(text: str, *, question: bool = False) -> str:
    value = text.strip().rstrip("?" if question else ".")
    if not value:
        return ""
    value = value[:1].upper() + value[1:]
    value = re.sub(r"\b(sar|ndbi|mndwi|ndvi|aeris)\b", lambda match: match.group(1).upper(), value, flags=re.IGNORECASE)
    return value + ("?" if question else ".")


def _figure_subject(title: str, query: str) -> tuple[str, str]:
    lower = title.lower()
    query_lower = query.lower()
    if "detector" in lower and "shown" in lower:
        return "Source", "image supplied to the object detector"
    if "detection" in lower:
        subject = "basketball courts" if "basketball" in query_lower else "requested objects"
        return "Detection", subject
    sensor = "Radar" if "radar" in lower or "sar" in lower else "Optical"
    subject = "built-up land" if "built" in lower else "surface water" if "water" in lower else "cross-sensor agreement"
    if "agreement" in lower or "fusion" in lower:
        sensor = "Cross-sensor"
    return sensor, subject


def _model_narrative(model: dict[str, Any]) -> ModelNarrative:
    model_id = str(_get(model, "model_id", "unknown"))
    version = str(_get(model, "model_version", "not recorded"))
    descriptions = {
        "co-registration": ("Image co-registration", "The spatial grids of the supplied observations.", "To ensure the same map location was compared across inputs.", "Recorded the residual alignment used by downstream analysis."),
        "index-engine": ("Spectral-index analysis", "Multispectral reflectance relationships associated with the requested land-surface classes.", "Spectral indices provide deterministic, interpretable evidence from optical bands.", "Produced the optical classification layer and its measurements."),
        "sar-preprocess": ("SAR backscatter processing", "Calibrated radar backscatter after speckle filtering and terrain correction.", "Radar supplies an independent observation that is not based on visible colour.", "Produced the radar evidence used in the comparison."),
        "optical-sar-fusion": ("Spatial late-fusion ledger", "The location-by-location relationship between independently derived optical and radar evidence.", "Late fusion preserves agreement and conflict instead of concealing disagreement in a blended score.", "Catalogued corroborated, single-sensor, conflicting, and non-informative regions."),
        "dota-detector": ("DOTA object detector", "Visible objects matching the requested overhead-imagery class vocabulary.", "A specialist detector is required when the request asks for a count or location of discrete objects.", "Produced confidence-scored detections and the annotated evidence overlay."),
        "rs-vlm": ("Remote-sensing vision-language reader", "The retained visual figure associated with the completed analysis.", "It adds a qualitative visual reading while quantitative findings remain owned by specialist claims.", "Contributed descriptive context only; it did not create a measurement."),
        "segformer": ("SegFormer semantic segmentation", "Image pixels associated with the requested land-cover classes.", "Semantic segmentation maps continuous regions rather than isolated objects.", "Produced per-class masks used for area and region measurements."),
        "changeformer": ("ChangeFormer change detector", "Registered before-and-after image content.", "A paired change model localises spatial change across two dates.", "Produced the change mask used for area and region measurements."),
    }
    name, analysed, reason, contribution = descriptions.get(model_id, (
        model_id.replace("-", " ").title(), "The validated input assigned to this analytical stage.",
        "It was selected by the investigation route for the requested evidence type.", "Contributed a retained analytical result to the evidence chain.",
    ))
    return ModelNarrative(name=name, version=version, what_was_analysed=analysed, why_it_was_used=reason, contribution=contribution)


def _fallback_document(*, run_id: str, values: dict[str, Any], figure_events: list[dict[str, Any]], generated_at: datetime) -> ReportDocument:
    claims = _claims(values)
    primary = next((item for item in claims if _get(item, "is_primary", False)), claims[0] if claims else None)
    primary_text = _reader_text(str(_get(primary or {}, "text", "A validated conclusion could not be established.")), values)
    query = str(_get(values, "query", "")).strip()
    findings = [ReportFinding(text=_reader_text(str(_get(item, "text", "")), values), is_primary=bool(_get(item, "is_primary", False)), confidence=_get(item, "confidence")) for item in claims]
    key_facts: list[KeyFact] = []
    for claim in claims:
        text = _reader_text(str(_get(claim, "text", "")), values)
        metrics = _get(claim, "metrics", []) or []
        if metrics:
            metric = metrics[0]
            key_facts.append(KeyFact(label=str(_get(metric, "label", "Validated finding")), value=text, interpretation="This value is taken directly from the retained claim and its spatial evidence."))
        elif text:
            key_facts.append(KeyFact(label="Validated finding", value=text, interpretation="This conclusion is retained as a claim rather than inferred from the report layout."))
    figures: list[ReportFigure] = []
    narratives: list[EvidenceNarrative] = []
    for event in figure_events:
        sensor, subject = _figure_subject(str(_get(event, "title", "")), query)
        figure_id = str(_get(event, "figure_id", ""))
        title = "Input image before analysis" if sensor == "Source" else "Basketball-court detections" if sensor == "Detection" else f"{sensor} evidence for {subject}"
        if sensor == "Source":
            caption = "The complete image supplied to the detector, shown without analytical annotations."
        elif sensor == "Detection":
            caption = "Each retained detection is outlined and labelled so the reported count can be reviewed visually."
        else:
            caption = _reader_text(str(_get(event, "caption", "")), values)
        claim_ids = list(_get(event, "claim_ids", []) or [])
        figures.append(ReportFigure(id=figure_id, title=title, caption=caption, claim_ids=claim_ids, is_primary=bool(_get(event, "is_primary", False))))
        if sensor == "Source":
            shows = "The source panel shows the complete visible image presented to the object detector before annotations were added."
            supports = "It establishes the visual input and context against which the reported detections can be reviewed."
        elif sensor == "Detection":
            shows = f"The annotated panel localises each detected {subject} and displays the spatial basis of the reported count."
            supports = "It allows the reader to compare the quantitative count with the detector's visible annotations."
        elif sensor == "Cross-sensor":
            shows = "The synthesis map distinguishes corroborated evidence, single-sensor evidence, and spatial conflicts across the common study area."
            supports = "It shows whether the independent sensor interpretations support a fused conclusion or require the disagreement to remain explicit."
        else:
            shows = f"The {sensor.lower()} analysis maps the pixels identified as {subject} in the supplied observation."
            supports = "It provides the mapped spatial evidence behind the principal finding." if bool(_get(event, "is_primary", False)) else "It provides an independent spatial result used in the cross-sensor comparison."
        credibility = "The figure is rendered from retained analysis output and is linked to a validated claim." if claim_ids else "The figure was produced in the same audited run and retains its rendering specification and processing trace."
        narratives.append(EvidenceNarrative(figure_id=figure_id, title=title, what_it_shows=shows, what_it_supports=supports, why_it_is_credible=credibility))
    models = [_model_narrative(item) for item in (_get(values, "stage_models", []) or [])]
    refused = bool(_get(_get(_get(values, "cross_modal_result", {}) or {}, "verdict", {}) or {}, "blocked_by_conflict", False)) or "cannot" in primary_text.lower()
    limitations = (
        primary_text + " The individual sensor findings remain usable, but the unresolved relationship must not be presented as a single fused classification."
        if refused else "The assessment is bounded by the supplied imagery, its stated resolution and quality, the requested classes, and the retained model evidence. Results should not be extended beyond the observed area or acquisition context."
    )
    if "basketball" in query.lower():
        title = "Basketball Court Detection and Count"
    elif "built" in query.lower() and "water" in query.lower():
        title = "Optical and Radar Assessment of Built-up Land and Surface Water"
    else:
        title = "Earth Observation Evidence Assessment"
    if refused:
        objective = (
            "Assess built-up land and surface water independently in the supplied optical and radar observations, "
            "then compare their spatial evidence without concealing agreement or disagreement between sensors."
        )
    elif query.lower().startswith("count "):
        objective = f"Determine {_sentence(query[6:]).lower()} and retain the visible evidence used to verify the count."
    else:
        objective = f"Assess {_sentence(query).lower()} using the supplied observations and retain the spatial evidence behind each conclusion."
    supporting_text = " ".join(item.text for item in findings if not item.is_primary)
    if refused and supporting_text:
        executive_summary = (
            "The supplied optical and radar observations were analysed independently for built-up land and surface water. "
            "Each branch produced spatially explicit area and region measurements with retained map evidence. The report "
            "compares those sensor-specific results through a spatial ledger so corroborated, single-sensor, and conflicting "
            "locations remain reviewable. Complete validated measurements follow, and the final page records the boundary on "
            "a combined conclusion."
        )
        direct_answer = "The supplied observations produced separate, reviewable optical and radar findings; the final page records the boundary on a combined conclusion."
    else:
        executive_summary = primary_text + (" Supporting results are reported separately so the established evidence remains useful." if len(findings) > 1 else "")
        direct_answer = primary_text
    subtitle = "Independent optical and radar evidence with spatial cross-comparison" if refused else "AERIS evidence-led remote-sensing investigation"
    report = ReportDocument(
        id=f"rpt_{run_id}", investigation_id=run_id, trace_id=run_id, title=title,
        subtitle=subtitle, question=query,
        objective=objective,
        executive_summary=executive_summary,
        generated_at=generated_at, questions_and_answers=[QuestionAnswer(question=_sentence(query, question=True), answer=direct_answer)],
        key_facts=key_facts, findings=findings, figures=figures, evidence_narratives=narratives,
        model_narratives=models, limitations=limitations, final_summary=primary_text,
        voice_narration=primary_text.replace("AERIS", "The analysis"), is_evidence_limited=refused, sections=[],
    )
    return report.model_copy(update={"sections": _sections(report, values)})


def _sections(report: ReportDocument, values: dict[str, Any]) -> list[ReportSectionDocument]:
    claims = _claims(values)
    claim_ids = [str(_get(item, "id", "")) for item in claims if _get(item, "id", "")]
    layer_ids = [str(_get(item, "id", "")) for item in (_get(values, "layers", []) or []) if _get(item, "id", "")]
    model_text = "\n".join(f"{item.name}: {item.what_was_analysed} {item.why_it_was_used}" for item in report.model_narratives)
    bodies = {
        ReportSection.SUMMARY: report.executive_summary, ReportSection.INPUTS: report.objective,
        ReportSection.FINDINGS: "\n".join(item.text for item in report.findings),
        ReportSection.EVIDENCE: "\n".join(item.what_it_shows + " " + item.what_it_supports for item in report.evidence_narratives),
        ReportSection.MODELS: model_text, ReportSection.CONFIDENCE: "Confidence values are reported only where a contributing method asserted them.",
        ReportSection.LIMITATIONS: report.limitations, ReportSection.CONCLUSION: report.final_summary,
    }
    return [ReportSectionDocument(id=f"sec_{report.investigation_id}_{kind.value}", kind=kind, heading=kind.value.title(), body=bodies[kind], layer_ids=layer_ids if kind is ReportSection.EVIDENCE else [], claim_ids=claim_ids if kind in {ReportSection.SUMMARY, ReportSection.FINDINGS, ReportSection.CONCLUSION} else []) for kind in REPORT_SECTION_ORDER]


def _editorial_source(report: ReportDocument) -> dict[str, Any]:
    useful_conclusion = next((item.text for item in report.findings if not item.is_primary), report.final_summary)
    return {
        "question": report.question,
        "principalConclusion": useful_conclusion if report.is_evidence_limited else report.findings[0].text if report.findings else report.final_summary,
        "finalBoundary": report.final_summary if report.is_evidence_limited else "",
        "validatedFindings": [item.text for item in report.findings],
        "currentObjective": report.objective, "currentSummary": "" if report.is_evidence_limited else report.executive_summary,
        "keyFacts": [item.model_dump() for item in report.key_facts],
        "figures": [{"figureIndex": index, "currentTitle": item.title, "caption": item.caption,
                     "validatedExplanation": report.evidence_narratives[index].model_dump(exclude={"figure_id"})}
                    for index, item in enumerate(report.figures)],
        "methods": [item.model_dump() for item in report.model_narratives], "limitations": report.limitations,
    }


async def apply_editorial_draft(report: ReportDocument, draft: EditorialReportDraft) -> ReportDocument:
    prose = " ".join([draft.title, draft.subtitle, draft.objective, draft.executive_summary, draft.limitations, draft.final_summary, draft.voice_narration] + [item.question + " " + item.answer for item in draft.questions_and_answers] + [item.label + " " + item.value + " " + item.interpretation for item in draft.key_facts] + [item.title + " " + item.what_it_shows + " " + item.what_it_supports + " " + item.why_it_is_credible for item in draft.evidence_narratives] + [item.name + " " + item.version + " " + item.what_was_analysed + " " + item.why_it_was_used + " " + item.contribution for item in draft.model_narratives])
    rejection_reason = _editorial_rejection_reason(report, draft, prose)
    if rejection_reason is not None:
        logger.warning("report editorial pass rejected by evidence guard: %s", rejection_reason)
        return report
    soft_warnings = _editorial_soft_warnings(report, draft, prose)
    if soft_warnings:
        logger.warning("report editorial pass accepted with soft evidence warnings: %s", soft_warnings)

    evidence_by_index = {item.figure_index: item for item in draft.evidence_narratives}
    narratives = [EvidenceNarrative(figure_id=figure.id, **evidence_by_index[index].model_dump(exclude={"figure_index"})) for index, figure in enumerate(report.figures)]
    questions_and_answers = [
        QuestionAnswer(question=_sentence(item.question, question=True), answer=item.answer)
        for item in draft.questions_and_answers
    ]
    executive_summary = draft.executive_summary
    title = report.title if report.is_evidence_limited and "joint" in draft.title.lower() else draft.title
    subtitle = draft.subtitle
    objective = draft.objective
    updated = report.model_copy(update={
        "title": title, "subtitle": subtitle, "objective": objective,
        "executive_summary": executive_summary, "questions_and_answers": questions_and_answers,
        "key_facts": draft.key_facts, "evidence_narratives": narratives, "model_narratives": draft.model_narratives,
        "limitations": draft.limitations, "final_summary": draft.final_summary, "voice_narration": draft.voice_narration,
    })
    return updated.model_copy(update={"sections": _sections(updated, {})})


def _editorial_rejection_reason(report: ReportDocument, draft: EditorialReportDraft, prose: str) -> str | None:
    """Return only violations that make an AI draft unsafe to publish.

    Numeric invention, leaked internal references and incomplete figure coverage remain hard boundaries.
    Editorial style and terminology are advisory so useful AI prose is not replaced wholesale by fallback
    text.
    """
    if _INTERNAL.search(prose):
        return "internal identifier in reader prose"
    source_text = json.dumps(_editorial_source(report), ensure_ascii=False)
    permitted = set(_NUMBER.findall(source_text))
    invented = [number for number in _NUMBER.findall(prose) if number not in permitted]
    if invented:
        return f"unvalidated numerals: {invented}"
    if {item.figure_index for item in draft.evidence_narratives} != set(range(len(report.figures))):
        return "figure editorial coverage does not match retained figures"
    return None


def _editorial_soft_warnings(report: ReportDocument, draft: EditorialReportDraft, prose: str) -> list[str]:
    """Collect editorial quality issues without turning them into a full-report fallback."""
    warnings: list[str] = []
    if _AUDIT_VOICE.search(prose):
        warnings.append("audit-style prose instead of AERIS product voice")
    if report.is_evidence_limited:
        body_prose = " ".join(
            [
                draft.title,
                draft.subtitle,
                draft.objective,
                draft.executive_summary,
                *[item.question + " " + item.answer for item in draft.questions_and_answers],
                *[item.label + " " + item.value + " " + item.interpretation for item in draft.key_facts],
                *[item.title + " " + item.what_it_shows + " " + item.what_it_supports + " " + item.why_it_is_credible for item in draft.evidence_narratives],
                *[item.name + " " + item.what_was_analysed + " " + item.why_it_was_used + " " + item.contribution for item in draft.model_narratives],
            ]
        )
        if _BODY_REFUSAL.search(body_prose):
            warnings.append("hard refusal language appears outside limitations and final assessment")
    source_text = json.dumps(_editorial_source(report), ensure_ascii=False).lower()
    unsupported = [term for term in _SCIENTIFIC_ASSERTIONS if term in prose.lower() and term not in source_text]
    unsupported.extend(term for term in _CONTEXTUAL_ASSERTIONS if term in prose.lower() and term not in source_text)
    if unsupported:
        warnings.append(f"unverified editorial terminology: {unsupported}")
    return warnings

async def _invoke_editorial_model(model: Any, prompt: str) -> EditorialReportDraft:
    """Ask the model twice before surfacing an editorial failure.

    A provider timeout or transient refusal must never silently publish the deterministic dossier. The
    dossier is context and a validation baseline; customer-facing prose must come from the configured AI.
    """
    structured_model = model.with_structured_output(EditorialReportDraft)
    for attempt in range(2):
        try:
            return await structured_model.ainvoke(prompt)
        except Exception as error:  # noqa: BLE001 - provider failures are retried at this boundary.
            if attempt == 1:
                logger.warning("editorial model unavailable after retry", extra={"reason": str(error)})
                raise ReportEditorialUnavailable("report editorial pass unavailable after retry") from error
            logger.warning("editorial model failed; retrying", extra={"reason": str(error)})
    raise AssertionError("editorial retry loop did not return or raise")


async def build_report(*, run_id: str, values: dict[str, Any], figure_events: list[dict[str, Any]], generated_at: datetime | None = None, use_language_model: bool = True) -> ReportDocument:
    report = _fallback_document(run_id=run_id, values=values, figure_events=figure_events, generated_at=generated_at or datetime.now(UTC))
    if not use_language_model:
        return report
    from app.lib.llm.chat_model import build_chat_model
    model = build_chat_model()
    if model is None:
        raise ReportEditorialUnavailable("report editorial model is not configured")
    prompt = REPORT_EDITORIAL_PROMPT.format(dossier=json.dumps(_editorial_source(report), ensure_ascii=False, indent=2))
    try:
        draft = await _invoke_editorial_model(model, prompt)
    except Exception as error:  # noqa: BLE001 - provider exceptions are converted to the report boundary.
        logger.warning("report editorial pass unavailable", extra={"reason": str(error)})
        raise ReportEditorialUnavailable("report editorial pass unavailable") from error
    edited = await apply_editorial_draft(report, draft)
    if edited == report:
        reason = _editorial_rejection_reason(report, draft, json.dumps(draft.model_dump(), ensure_ascii=False))
        boundary_instruction = (
            "\nFor evidence-limited reports, do not put hard refusal phrases in title, subtitle, objective, "
            "executive_summary, question answers, key facts, evidence narratives, or model narratives. In those body "
            "fields, say AERIS retained an unresolved sensor conflict for review. Keep the exact hard boundary only "
            "in limitations and final_summary."
            if reason == "hard refusal language outside limitations and final assessment" else ""
        )
        corrective_prompt = prompt + (
            "\n\nThe previous draft was rejected by a deterministic guard for this reason: " + str(reason) +
            ". Produce a corrected complete draft. Do not omit any retained figure." + boundary_instruction
        )
        try:
            corrected = await _invoke_editorial_model(model, corrective_prompt)
            edited = await apply_editorial_draft(report, corrected)
        except Exception as error:  # noqa: BLE001 - provider exceptions are converted to the report boundary.
            logger.warning("corrective report editorial pass unavailable", extra={"reason": str(error)})
            raise ReportEditorialUnavailable("corrective report editorial pass unavailable") from error
    if edited == report:
        raise ReportEditorialUnavailable("report editorial draft rejected by evidence guard")
    return edited.model_copy(update={"sections": _sections(edited, values)})
