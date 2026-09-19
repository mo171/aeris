"""Inngest function registrations."""

from app.inngest.functions.ingest_scene import fn_ingest_scene
from app.inngest.functions.run_investigation import fn_run_investigation

__all__ = [
    "fn_ingest_scene",
    "fn_run_investigation",
]
