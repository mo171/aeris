"""Artifact retrieval service for figures from MinIO/S3 storage.

Follows the invariant:
HTTP layer merely retrieves the finished artifact; it never renders or executes math.
"""

import logging
from typing import Any

from sqlalchemy import select

from app.constants.storage import Bucket
from app.db.models.run import Run as DbRun
from app.lib import storage
from app.lib.exceptions import ResourceNotFoundError
from app.schemas.events.figure import FigureReadyEvent
from app.services.sessions.journal_writer import read_journal

logger = logging.getLogger(__name__)


async def list_investigation_figures(investigation_id: str) -> list[FigureReadyEvent]:
    """Retrieve all figure-ready event metadata for an investigation, newest first."""
    from app.lib import database

    figures: list[FigureReadyEvent] = []
    async with database.get_session() as session:
        stmt = (
            select(DbRun.id)
            .where(DbRun.investigation_id == investigation_id)
            .order_by(DbRun.started_at.desc())
        )
        res = await session.execute(stmt)
        run_ids = list(res.scalars().all())

    for r_id in run_ids:
        try:
            for event in read_journal(r_id):
                if isinstance(event, FigureReadyEvent):
                    figures.append(event)
        except Exception:
            # Run journal might not exist yet or empty
            continue

    return figures


async def get_figure_bytes(figure_id: str) -> tuple[bytes, str]:
    """Retrieve raw image bytes and media type from Bucket.FIGURES in object storage."""
    # Normalize figure_id: strip extension if provided
    clean_id = figure_id
    ext = "webp"
    if "." in figure_id:
        clean_id, ext = figure_id.rsplit(".", 1)

    # 1. Try common keys
    candidate_keys = [
        figure_id,
        f"{clean_id}.{ext}",
        f"{clean_id}.webp",
        f"{clean_id}.png",
    ]

    for key in candidate_keys:
        if await storage.object_exists(Bucket.FIGURES, key):
            image_bytes = await storage.get_object(Bucket.FIGURES, key)
            media_type = "image/png" if key.endswith(".png") else "image/webp"
            return image_bytes, media_type

    # 2. Try searching by prefix in Bucket.FIGURES
    try:
        matching = await storage.list_objects(Bucket.FIGURES, prefix=clean_id)
        if matching:
            found_key = matching[0]
            image_bytes = await storage.get_object(Bucket.FIGURES, found_key)
            media_type = "image/png" if found_key.endswith(".png") else "image/webp"
            return image_bytes, media_type
    except Exception:
        pass

    raise ResourceNotFoundError(
        f"Figure {figure_id} not found in storage bucket {Bucket.FIGURES.value}",
        details={"figureId": figure_id},
    )
