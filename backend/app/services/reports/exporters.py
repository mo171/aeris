"""Persists every Phase 1.12 surface from one canonical report document.

what  : Writes detailed PDF, briefing PDF, manifest, GeoJSON, Markdown, and voice-ready text.
where : The completed-run edge in `pipeline/runner.py`; future object-storage delivery wraps this service.
how   : Editorial generation occurs once, then each exporter receives the same immutable content model.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas.report import ReportDocument
from app.services.reports.generator import build_report
from app.services.reports.geojson import build_geojson
from app.services.reports.markdown import render_chat_markdown
from app.services.reports.pdf.renderer import render_pdf
from app.services.reports.voice import render_voice_narration


@dataclass(frozen=True, slots=True)
class ReportBundle:
    report: ReportDocument
    directory: Path
    pdf_path: Path
    summary_pdf_path: Path
    json_path: Path
    geojson_path: Path
    markdown_path: Path
    voice_path: Path


async def write_report_bundle(*, run_id: str, values: dict[str, Any], figure_paths: tuple[Path, ...] = (), figure_events: list[dict[str, Any]] | None = None, generated_at: datetime | None = None) -> ReportBundle:
    report = await build_report(run_id=run_id, values=values, figure_events=figure_events or [], generated_at=generated_at)
    directory = settings.journal_directory / run_id / "reports"
    await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
    paths = {
        "json": directory / "report.json", "markdown": directory / "report.md", "voice": directory / "voice.txt",
        "pdf": directory / "report.pdf", "summary": directory / "report-summary.pdf", "geojson": directory / "report.geojson",
    }
    markdown, voice, detailed_pdf, summary_pdf, geojson = await asyncio.gather(
        render_chat_markdown(report), render_voice_narration(report), render_pdf(report, figure_paths=figure_paths),
        render_pdf(report, figure_paths=figure_paths, summary_only=True), build_geojson(values),
    )
    await asyncio.gather(
        asyncio.to_thread(paths["json"].write_text, report.model_dump_json(by_alias=True, indent=2), "utf-8"),
        asyncio.to_thread(paths["markdown"].write_text, markdown, "utf-8"),
        asyncio.to_thread(paths["voice"].write_text, voice, "utf-8"),
        asyncio.to_thread(paths["pdf"].write_bytes, detailed_pdf),
        asyncio.to_thread(paths["summary"].write_bytes, summary_pdf),
        asyncio.to_thread(paths["geojson"].write_text, json.dumps(geojson, indent=2), "utf-8"),
    )
    return ReportBundle(report, directory, paths["pdf"], paths["summary"], paths["json"], paths["geojson"], paths["markdown"], paths["voice"])
