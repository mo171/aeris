"""Keeps what a stage produced, on disk and in storage, so a later stage - or a resumed run - reads the artefact rather than the memory it came from.

what  : `store_artefact()` - an array becomes a COG under the run's directory and in the `artefacts`
        bucket; `store_json_artefact()` - the same for a document (a detector's boxes); `read_artefact()` -
        the way back, from disk or, failing that, from the bucket.
where : Called by the S7, S12 and S15 nodes. From 1.5, the URI it returns is what a trace step and an
        evidence record point at (`api-contract.md` §1 rule 10).
how   : `architecture-context.md` §8 rule 12: every intermediate a stage marks as producing an artefact is
        retained and addressable. This module is also what keeps arrays out of the checkpoint - the state
        carries a path and an object key (`services/pipeline/state.py`: a checkpoint holds data, never
        objects), and a node that needs the array reads it back through here.

        **Two copies, one truth.** The local file is what this process reads; the object in storage is
        what a process on another machine - or Phase 2's Inngest worker - reads. `read_artefact` prefers
        the local copy and fetches the object when it is missing, which is what makes a run resumable
        after the working directory is gone.

        One run is one place on disk: `runs/<run_id>/artefacts/` beside `runs/<run_id>/figures/` and the
        journal, for the reason `services/sessions/figure_writer.py` gives.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio

from app.config import settings
from app.constants.raster import NODATA_FLOAT
from app.constants.stages import PipelineStage
from app.constants.storage import Bucket
from app.lib import storage
from app.services.imagery.cog import upload_cog, write_cog_from_array
from app.services.imagery.metadata import RasterMetadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StoredArtefact:
    """Where one stage's intermediate lives, locally and in storage."""

    path: Path
    object_key: str
    storage_uri: str
    stage: PipelineStage


def artefact_directory(run_id: str) -> Path:
    return settings.journal_directory / run_id / "artefacts"


def artefact_object_key(run_id: str, stage: PipelineStage, name: str) -> str:
    return f"{run_id}/{stage.value}/{name}"


async def store_artefact(
    array: np.ndarray,
    *,
    run_id: str,
    stage: PipelineStage,
    name: str,
    reference: RasterMetadata,
    nodata: float = NODATA_FLOAT,
    categorical: bool = False,
) -> StoredArtefact:
    """Write `array` as a COG georeferenced from `reference`, locally and to the `artefacts` bucket."""
    destination = artefact_directory(run_id) / f"{stage.value}_{name}"
    await write_cog_from_array(
        array, reference=reference, destination=destination, nodata=nodata, categorical=categorical
    )
    result = await upload_cog(
        destination, object_key=artefact_object_key(run_id, stage, name), bucket=Bucket.ARTEFACTS
    )
    logger.info(
        "artefact stored",
        extra={"run_id": run_id, "stage": stage.value, "object_key": result.object_key, "bytes": result.size_bytes},
    )
    return StoredArtefact(
        path=destination, object_key=result.object_key, storage_uri=result.storage_uri, stage=stage
    )


async def store_json_artefact(payload: Any, *, run_id: str, stage: PipelineStage, name: str) -> StoredArtefact:
    """Write a JSON document - a detector's boxes, a registration measurement - locally and to the
    `artefacts` bucket. The same two copies as a raster artefact, for the same reason (1.10)."""
    destination = artefact_directory(run_id) / f"{stage.value}_{name}"
    text = json.dumps(payload, indent=None, sort_keys=True)
    await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(destination.write_text, text, "utf-8")
    object_key = artefact_object_key(run_id, stage, name)
    await storage.put_object(Bucket.ARTEFACTS, object_key, text.encode("utf-8"), content_type="application/json")
    logger.info("artefact stored", extra={"run_id": run_id, "stage": stage.value, "object_key": object_key, "bytes": len(text)})
    return StoredArtefact(
        path=destination, object_key=object_key, storage_uri=f"s3://{await storage.bucket_name(Bucket.ARTEFACTS)}/{object_key}", stage=stage,
    )


async def read_artefact(path: Path, object_key: str) -> np.ndarray:
    """The artefact's first band, from the local copy or from storage when the local copy is gone."""
    if not await asyncio.to_thread(path.exists):
        payload = await storage.get_object(Bucket.ARTEFACTS, object_key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, payload)
        logger.info("artefact restored from storage", extra={"object_key": object_key, "path": str(path)})
    return await asyncio.to_thread(_read_first_band, path)


def _read_first_band(path: Path) -> np.ndarray:
    with rasterio.open(path) as dataset:
        return dataset.read(1)
