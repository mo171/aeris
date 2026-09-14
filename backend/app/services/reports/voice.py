"""Returns the short speakable narrative authored from the same validated report."""

from app.schemas.report import ReportDocument


async def render_voice_narration(report: ReportDocument) -> str:
    return " ".join(report.voice_narration.split())
