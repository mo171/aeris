"""Inngest background execution package for AERIS (Phase 2.5).

what  : Client accessors and functions registry for Inngest durable workers.
where : Mounted into FastAPI at `/api/inngest` via `inngest.fast_api.serve`.
"""

from app.inngest.functions import fn_ingest_scene, fn_run_investigation
from app.lib.inngest import get_client, get_inngest_client

INNGEST_FUNCTIONS = [
    fn_run_investigation,
    fn_ingest_scene,
]

__all__ = [
    "INNGEST_FUNCTIONS",
    "fn_ingest_scene",
    "fn_run_investigation",
    "get_client",
    "get_inngest_client",
]
