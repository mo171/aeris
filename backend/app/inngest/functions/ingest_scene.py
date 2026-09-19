"""Durable scene ingestion function for Inngest (Phase 2.5).

what  : `fn_ingest_scene`, an Inngest function triggered on `aeris/scene.ingest_requested`.
where : `app/inngest/functions/ingest_scene.py`. Registered in `INNGEST_FUNCTIONS`.
how   : Executes S1-S6 raster inspection and Cloud-Optimized GeoTIFF transformation
        durably via Inngest steps, ensuring automatic retries if an S3 or compute error occurs.
"""

import logging
from typing import Any

import inngest

from app.constants.tasks import EventName
from app.lib.inngest import get_inngest_client
from app.services.imagery.ingest_task import run_scene_ingest

logger = logging.getLogger(__name__)

inngest_client = get_inngest_client()


@inngest_client.create_function(
    fn_id="aeris-ingest-scene",
    name="Ingest Earth Observation Scene",
    trigger=inngest.TriggerEvent(event=EventName.SCENE_INGEST_REQUESTED),
    retries=3,
)
async def fn_ingest_scene(
    ctx: inngest.Context, step: inngest.Step | None = None
) -> dict[str, Any]:
    """Execute durable scene ingestion."""
    step_runner = step or ctx.step
    event_data = ctx.event.data or {}
    scene_id: str = event_data["scene_id"]
    raw_object_key: str = event_data["raw_object_key"]

    logger.info(
        "Inngest fn_ingest_scene triggered",
        extra={"scene_id": scene_id, "key": raw_object_key, "attempt": ctx.attempt},
    )

    async def _execute_ingest() -> dict[str, Any]:
        return await run_scene_ingest(scene_id, raw_object_key, raise_on_failure=True)

    return await step_runner.run(
        "run_scene_ingest",
        _execute_ingest,
    )
