"""Writes the record that lets an evaluator walk any claim back to pixels, parameters and model versions - the run's provenance, and its evidence graph.

what  : `ProvenanceRecord` and `EvidenceGraph` (Pydantic, camelCase), `hash_file()`, and the two writers
        that put them beside the run's journal: `runs/<run_id>/provenance.json` and
        `runs/<run_id>/evidence-graph.json`.
where : S19 (`services/pipeline/nodes/provenance_logging.py`) assembles both from the state and writes
        them. Phase 2.3 serves the evidence graph from `GET /investigations/{id}/evidence`, and 1.9's run
        row is this record's columns.
how   : PDF §21.2 lists what reproducibility needs: model versions, parameters, input hashes, CRS and
        processing level, per-stage timings, the confidence aggregation rule, and the intermediate
        artefacts as object-storage URIs. The journal already carries the events an operator saw; this is
        the record of *what was computed from what*, and it is the part the wire does not carry - an
        artefact's object key is not on any event, only the layer that draws it is.

        `EvidenceGraph` mirrors the frontend's `evidenceGraphSchema` field for field, so the file validates
        against the vendored contract the same way the journal does. Flat arrays keyed by id, as the
        frontend asks, because claims, evidence and layers are a graph rather than a tree.

        Input files are hashed with SHA-256 over their bytes. A scene re-fetched from the catalogue after a
        reprocessing is a different input with the same name; the hash is what tells the two apart, and it
        costs a fraction of a second per band.
"""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from app.config import settings
from app.constants.stages import PipelineStage
from app.lib.responses import CamelCaseModel
from app.schemas.events import Claim, EvidenceItem, EvidenceLayer

PROVENANCE_FILE_NAME = "provenance.json"
EVIDENCE_GRAPH_FILE_NAME = "evidence-graph.json"
HASH_CHUNK_BYTES = 1 << 20


class InputFileRecord(CamelCaseModel):
    """One file a run read, identified by content rather than by name."""

    path: str
    band_id: str
    role: str
    sha256: str
    crs: str | None
    processing_level: str
    width: int
    height: int
    resolution_metres: float


class ArtefactRecord(CamelCaseModel):
    """One intermediate a stage retained, and the layer that draws it where one exists."""

    stage: PipelineStage
    name: str
    object_key: str
    storage_uri: str
    local_path: str
    layer_id: str | None = None


class ModelRecord(CamelCaseModel):
    """`model@version`, and the stage it ran at. Registry entries are immutable (PDF §21.2)."""

    stage: PipelineStage
    model_id: str
    model_version: str
    confidence: float | None = None


class ProvenanceRecord(CamelCaseModel):
    """What was computed, from what, with which versions and parameters."""

    run_id: str
    query: str
    intent: str
    scene_id: str
    generated_at: datetime
    inputs: list[InputFileRecord]
    parameters: dict[str, Any]
    models: list[ModelRecord]
    artefacts: list[ArtefactRecord]
    trace_step_ids: list[str]
    claim_ids: list[str]
    figure_ids: list[str]
    confidence_aggregation_rule: str
    confidence: float | None
    # The S14 reading, if any: what the model said about which figure, and whether the answer carried it.
    reading: dict[str, Any] | None = None


class EvidenceGraph(CamelCaseModel):
    """The frontend's `evidenceGraphSchema`: claims, evidence and layers, flat, keyed by id."""

    claims: list[Claim]
    evidence: list[EvidenceItem]
    layers: list[EvidenceLayer]
    # UTC, so it serialises with the `Z` the frontend's `z.iso.datetime()` insists on (0.7 measured it).
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def provenance_path(run_id: str) -> Path:
    return settings.journal_directory / run_id / PROVENANCE_FILE_NAME


def evidence_graph_path(run_id: str) -> Path:
    return settings.journal_directory / run_id / EVIDENCE_GRAPH_FILE_NAME


async def hash_file(path: Path) -> str:
    """SHA-256 of a file's bytes, read in chunks so a 245 MB band never sits in memory twice."""
    return await asyncio.to_thread(_hash_file, path)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


async def write_provenance(record: ProvenanceRecord) -> Path:
    """Indented: a person reads this one."""
    return await _write_json(provenance_path(record.run_id), record, indent=2)


async def write_evidence_graph(run_id: str, graph: EvidenceGraph) -> Path:
    """Compact: a vector layer's rings make this the run's largest file, and a machine reads it."""
    return await _write_json(evidence_graph_path(run_id), graph, indent=None)


async def _write_json(destination: Path, model: CamelCaseModel, *, indent: int | None) -> Path:
    # The same two serialisation rules as every event (`schemas/events/base.py`): aliases and JSON mode,
    # so the file is wire-shaped and validates against the vendored contract without translation.
    payload = model.model_dump_json(by_alias=True, indent=indent)
    await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(destination.write_text, payload, encoding="utf-8")
    return destination
