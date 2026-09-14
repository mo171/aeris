"""Projects the canonical report narrative into safe, complete Markdown for chat."""

from app.schemas.report import ReportDocument


async def render_chat_markdown(report: ReportDocument) -> str:
    answer = report.final_summary + "\n\n### Established findings\n" + report.executive_summary if report.is_evidence_limited else report.executive_summary
    lines = ["## Answer", answer, "", "## Question and direct answer"]
    for item in report.questions_and_answers:
        lines.extend([f"**{item.question}**", item.answer, ""])
    lines.append("## Key facts")
    lines.extend(f"- **{item.label}:** {item.value} — {item.interpretation}" for item in report.key_facts)
    if report.evidence_narratives:
        lines.extend(["", "## Evidence interpretation"])
        for item in report.evidence_narratives:
            lines.extend([f"### {item.title}", item.what_it_shows, f"**Supports:** {item.what_it_supports}", f"**Evidence basis:** {item.why_it_is_credible}"])
    lines.extend(["", "## Final assessment", report.final_summary])
    return "\n".join(lines).strip() + "\n"
