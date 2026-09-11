# AERIS Backend Study Guide

This is the starting document for learning, running, and reviewing the AERIS backend.

AERIS is an agentic Earth-observation backend. It accepts a question about satellite imagery, runs scientific and specialist analysis, and returns an evidence-grounded answer. The language model explains validated results; it must not invent measurements.

The central flow is:

```text
user question or voice
        -> session and run
        -> LangGraph pipeline
        -> imagery and scientific processing
        -> specialist model result
        -> evidence and claims
        -> written, spoken, and visual output
```

## 1. Read This First

The backend has two kinds of documentation:

- **Learning and product intent:** this file and `bcontext/product-truth.md`
- **Implementation authority:** the remaining `bcontext` documents

Read the authoritative documents in this order when you begin a serious study session:

1. [`bcontext/product-truth.md`](bcontext/product-truth.md) - what the product must do and why.
2. [`bcontext/roadmap.md`](bcontext/roadmap.md) - what is built, what comes next, and each phase's gate.
3. [`bcontext/architecture-context.md`](bcontext/architecture-context.md) - layers, dependencies, and invariants.
4. [`bcontext/folder-archtecture.md`](bcontext/folder-archtecture.md) - where each responsibility belongs.
5. [`bcontext/code-standards.md`](bcontext/code-standards.md) - how backend code is written.
6. [`bcontext/api-contract.md`](bcontext/api-contract.md) - the frontend/backend wire contract.
7. [`bcontext/architecture-decisions.md`](bcontext/architecture-decisions.md) - why important technologies and boundaries were chosen.
8. [`bcontext/memory.md`](bcontext/memory.md) - verified discoveries and previous implementation notes.

The documents above are more authoritative than a convenient assumption or an old comment. In particular, the roadmap is the plan of record, while this guide is a map for studying it.

## 2. What the Backend Owns

The backend is responsible for:

- acquiring and cataloguing satellite datasets;
- reading and validating raster imagery;
- converting imagery into Cloud-Optimized GeoTIFFs (COGs);
- storing large files in S3-compatible object storage;
- serving raster tiles through TiTiler;
- preprocessing optical and SAR imagery;
- computing spectral indices and geospatial statistics;
- running specialist models for detection, segmentation, change detection, grounding, and VQA;
- producing spatially located evidence and claims;
- rendering deterministic figures that the operator and VLM can inspect;
- orchestrating runs through LangGraph;
- preserving run checkpoints and long-term memory;
- streaming trace, layer, claim, answer, figure, speech, and UI-command events;
- eventually accepting browser voice input and returning speech.

The most important product rule is:

```text
specialist model -> structured result -> evidence -> validation -> language explanation
```

A fluent answer is not evidence. A claim needs a location, model provenance, confidence, and a trace back to the operation that produced it.

## 3. Architecture in One View

### 3.1 Request and execution flow

```text
CLI in Phase 1 / HTTP route in Phase 2
        |
        v
controller and service
        |
        v
LangGraph StateGraph
        |
        +--> checkpoint after graph progress
        +--> custom stream events
        +--> scientific services
                 |
                 +--> PostGIS for structured spatial data
                 +--> MinIO/S3 for large files and figures
                 +--> Redis for cache and locks
                 +--> specialist models
```

Phase 1 uses the CLI and runs locally. Phase 2 adds FastAPI, SSE, WebSockets, authentication, and Inngest without changing the core graph. The same graph should work from both adapters.

### 3.2 Layer responsibilities

| Layer | Responsibility | Must not do |
|---|---|---|
| CLI or route | Adapter and input/output boundary | Contain business logic |
| Controller | Validate input, call one service, shape output | Compute scientific results |
| Service | Own a use case and coordinate dependencies | Know about HTTP or contain numerical methods |
| Pipeline node | Execute one S-stage, update state, emit events | Call another node directly or retry itself |
| Domain function | Apply business meaning to plain data | Perform infrastructure I/O |
| `math/` | Pure numerical method | Know about runs, scenes, or databases |
| Agent | Plan, route, call tools, explain validated results | Invent evidence or compute measurements |
| SQLAlchemy model | Describe persistence | Carry business logic |
| `lib/` | Own infrastructure clients and cross-cutting utilities | Import services or routes |

Two rules shape almost every file:

1. Everything is `async def` except pure numerical code in `math/`.
2. Numerical methods never live in the service that selects them.

## 4. Infrastructure and Data Boundaries

### PostgreSQL + PostGIS

PostgreSQL stores structured application data: investigations, runs, scenes, evidence, claims, trace steps, missions, and geometry metadata. PostGIS adds points, polygons, spatial indexes, intersections, distances, and coordinate-aware operations.

Local configuration is in [`docker-compose.yml`](docker-compose.yml) and [`app/config.py`](app/config.py). The async SQLAlchemy engine and the PostGIS health check are in [`app/lib/database.py`](app/lib/database.py).

Large image pixels do not belong in PostgreSQL. PostgreSQL stores metadata and references; object storage stores the files.

### Redis

Redis has two deliberately separate uses:

- short-lived cache entries;
- locks around shared resources such as GPU/model loading.

Redis is not the source of truth for business data. The local instance has no persistence by design.

Study [`app/lib/redis.py`](app/lib/redis.py) and [`app/constants/redis_keys.py`](app/constants/redis_keys.py).

### MinIO / S3

MinIO is local S3-compatible object storage. The application talks to the S3 API so production can use S3, R2, or another compatible provider.

It stores raw scenes, COGs, figures, artefacts, and reports. Study [`app/lib/storage.py`](app/lib/storage.py) and [`app/constants/storage.py`](app/constants/storage.py).

### SQLite

Phase 1 uses two SQLite files:

- `data/checkpoints.sqlite`: LangGraph run checkpoints. This lets a stopped run resume.
- `data/memory.sqlite`: long-term memories deliberately saved for future sessions.

They are not interchangeable. A checkpoint is execution state for one run; long-term memory is information meant to survive runs. Study [`app/services/pipeline/checkpointer.py`](app/services/pipeline/checkpointer.py) and [`app/services/pipeline/memory_store.py`](app/services/pipeline/memory_store.py).

### TiTiler

TiTiler is not a database. It reads COGs from MinIO/S3 and returns small, reprojected map tiles to the frontend. The browser requests only the tiles needed for its current map viewport instead of downloading an entire satellite scene.

Study the COG writer at [`app/services/imagery/cog.py`](app/services/imagery/cog.py) and the `titiler` service in [`docker-compose.yml`](docker-compose.yml).

## 5. What Has Been Built

The roadmap records the following completed work.

### Phase 0: foundation and infrastructure

- `uv` project setup, locked dependencies, configuration, logging, and exceptions;
- PostgreSQL/PostGIS connection and Alembic migrations;
- Redis client, cache, and distributed lock;
- MinIO/S3 client, buckets, presigned URLs, and CORS checks;
- Inngest development server connectivity, intentionally not yet bound to application workflows;
- `aeris doctor` health diagnostics;
- frontend contract export and backend fixture validation.

The setup gate is:

```powershell
cd backend
docker compose up -d
uv run alembic upgrade head
uv run aeris doctor
```

### Phase 1.0: LangGraph pipeline spine

Built:

- Typer CLI;
- typed pipeline state;
- LangGraph checkpointer;
- run start, resume, replay, and explicit abandonment;
- detached run handles so a session can have work in progress;
- stream event models;
- terminal trace renderer;
- JSONL journal writer;
- two-node probe graph;
- empty but configured long-term memory store.

The core files are [`app/services/pipeline/state.py`](app/services/pipeline/state.py), [`app/services/sessions/session.py`](app/services/sessions/session.py), [`app/services/sessions/run_handle.py`](app/services/sessions/run_handle.py), and [`app/cli/run.py`](app/cli/run.py).

### Phase 1.1: datasets

Built:

- dataset catalogue;
- licensing and redistribution metadata;
- STAC search and acquisition;
- dataset enumeration and layout handling;
- `aeris dataset list`, `show`, `fetch`, and `search`.

Start with [`app/services/datasets/`](app/services/datasets/) and [`app/cli/dataset.py`](app/cli/dataset.py).

### Phase 1.2: raster engine and tiles

Built:

- raster driver and metadata inspection;
- validation and quality checks;
- COG conversion;
- windowed tiling;
- TiTiler in Docker Compose;
- browser tile gate using EPSG:3857 XYZ tiles, CORS, alpha transparency, and TileJSON.

Start with [`app/services/imagery/`](app/services/imagery/) and [`app/cli/ingest.py`](app/cli/ingest.py).

### Phase 1.2.1: visual products

Built:

- deterministic array-to-image rendering;
- color ramps and stretches;
- RGB composite, index map, and mask overlay figures;
- figure metadata, legends, and render specifications;
- MinIO storage and JSONL figure events;
- byte-identical rerender tests.

Start with [`app/services/rendering/`](app/services/rendering/) and [`app/schemas/events/figure.py`](app/schemas/events/figure.py).

### Phase 1.3: preprocessing

Built:

- optical cloud and shadow masking;
- reprojection and grid alignment;
- co-registration with residual checks;
- SAR calibration;
- speckle filtering;
- terrain correction;
- layover and shadow masks;
- refusal when registration quality is not good enough.

Start with [`app/services/preprocessing/`](app/services/preprocessing/) and its `math/` modules.

### Phase 1.4 and later

The roadmap marks later analysis work as partially built or planned depending on the current session. Before studying a module, use the status and gate in [`bcontext/roadmap.md`](bcontext/roadmap.md) as the source of truth.

The intended sequence is:

```text
1.4 spectral indices and geospatial statistics
1.5 evidence localisation and confidence
1.6 specialist models
1.7 VLM and constrained answer generation
1.8 query understanding and routing
1.9 agent and tool calling
1.10 pipeline graphs
1.11 optical-SAR fusion
1.12 reports
1.13 voice loop
1.14 evaluation
```

Some architecture, schemas, constants, and contracts for these phases already exist before their runtime behavior is complete. Do not mistake a planned file or a contract entry for a finished feature.

## 6. What Is Not Complete Yet

Treat these as planned unless the roadmap gate says otherwise:

- persistent mission/session conversation history;
- a general `messages` array for the assistant conversation;
- browser audio upload and transcription;
- the full agent graph and tool-calling loop;
- the full voice loop with faster-whisper and speech synthesis;
- FastAPI routes and controllers;
- SSE and WebSocket serving;
- Inngest workflow binding and retry behavior;
- authentication;
- all specialist model integrations;
- final report generation and evaluation harness.

The design already describes these features. The implementation status must be checked against the roadmap and source, not inferred from the design documents alone.

## 7. A Practical Study Sequence

### Stage 1: run the system

From PowerShell:

```powershell
cd C:\movin\projects\hackathon\sih\aeris\backend
.venv\Scripts\Activate.ps1
docker compose up -d
uv run alembic upgrade head
uv run aeris doctor
```

Useful commands:

```powershell
uv run aeris --help
uv run aeris dataset --help
uv run aeris ingest --help
uv run aeris preprocess --help
uv run aeris run --help
```

If `uv` is not on `PATH`, use the installed executable or install uv first. Do not replace `uv run` with a random system Python: the project is pinned to CPython 3.14.

### Stage 2: understand one complete vertical slice

Do not start by reading every model. Follow one probe run:

1. [`app/cli/run.py`](app/cli/run.py) creates the graph and infrastructure.
2. [`app/services/sessions/session.py`](app/services/sessions/session.py) creates a run ID and initial state.
3. [`app/services/sessions/run_handle.py`](app/services/sessions/run_handle.py) starts `graph.astream()`.
4. [`app/services/pipeline/graphs/probe.py`](app/services/pipeline/graphs/probe.py) defines two nodes.
5. [`app/services/pipeline/node.py`](app/services/pipeline/node.py) adds trace behavior and cancellation checks.
6. [`app/services/pipeline/state.py`](app/services/pipeline/state.py) defines state and reducers.
7. [`app/services/pipeline/checkpointer.py`](app/services/pipeline/checkpointer.py) persists resumable state.
8. [`app/cli/renderers/`](app/cli/renderers/) consumes the stream.

Then answer these questions in your own notes:

- What is the difference between a session, a run, a thread ID, and a checkpoint?
- Which values are in state, and which values are only in stream events?
- What happens if the process dies between two nodes?
- Why does the run continue independently of the command that started it?
- Which component owns retries, and which component owns resume?

### Stage 3: study scientific correctness

Study one raster operation end to end:

```text
CLI command
  -> service
  -> metadata and validation
  -> math kernel
  -> COG or figure
  -> storage
  -> event
```

Recommended order:

1. imagery metadata and validation;
2. COG creation;
3. preprocessing;
4. spectral index math;
5. rendering;
6. evidence and claims.

For every numerical method, identify:

- input units and CRS;
- nodata behavior;
- masking order;
- numerical guard conditions;
- output units;
- the test that would catch a plausible but wrong result.

### Stage 4: study the persistence boundary

Read the SQLAlchemy models under [`app/db/models/`](app/db/models/), then compare them with the Alembic migrations under [`migrations/versions/`](migrations/versions/).

Check:

- which tables are authoritative;
- which relationships use foreign keys;
- which columns are spatial;
- which data is durable in PostgreSQL;
- which data is deliberately temporary in Redis;
- which large files are only referenced by object-storage keys;
- why SQLite checkpoints are separate from long-term memory.

### Stage 5: study the future agent and voice path

Read these together:

- `bcontext/product-truth.md` sections 1.1-1.6;
- `bcontext/api-contract.md` sections 3-5;
- `bcontext/roadmap.md` phases 1.8, 1.9, 1.13, and 2.4-2.7;
- the frontend command registry in `frontend/lib/constants/commands.ts`;
- the frontend assistant schemas and mock stream.

The intended path is:

```text
text or audio
  -> assistant session/thread
  -> intent and plan
  -> operator approval when required
  -> analysis tool or interface command
  -> evidence-grounded answer
  -> text, speech, and visual event
```

Keep this distinction clear:

- thread/checkpoint state is automatic execution and conversation context;
- long-term memory is deliberately saved information;
- a stored memory is context, never evidence;
- evidence must come from a specialist result and trace.

## 8. How to Review the Backend

Review in this order.

### A. Correctness review

- Can a claim be traced to a stage, model, input, and spatial region?
- Can a run resume without repeating completed work?
- Are cancellations explicit and distinguishable from failures?
- Are PostGIS geometries stored with the correct CRS?
- Are areas calculated in an equal-area projection rather than latitude/longitude degrees?
- Are nodata, clouds, shadows, layover, and registration failures handled before analysis?
- Can a figure be reproduced from its render specification?

### B. Boundary review

- Does a route know too much about a database or model?
- Does a service contain numerical code that belongs in `math/`?
- Does a pipeline node call another node directly?
- Does `lib/` import a service?
- Does a retry loop exist outside Inngest?
- Does a new abstraction have a second real caller?

### C. Data lifecycle review

For every value, ask:

```text
Where is it first created?
Where is it transformed?
Where is it persisted?
How is it retrieved?
What is its retention period?
What provenance identifies it?
```

Pay special attention to the current gap between the planned session thread memory and the current implementation: the session object and checkpoint foundation exist, but persistent assistant message history and browser audio storage are not complete.

### D. Test review

Run the narrow test first, then the full suite:

```powershell
uv run pytest tests/unit -q
uv run pytest -q
uv run ruff check .
uv run uv lock --check
```

Integration tests require Docker services:

```powershell
uv run pytest tests/integration -q
```

A passing test is not enough. Read the test's assertion and ask which failure mode it excludes. Scientific tests should include known-good, known-bad, nodata, CRS, boundary, and refusal cases.

## 9. Review Exercises

Use these as deliberate practice.

### Exercise 1: checkpoint experiment

Run the probe graph with a long pause, stop it during the second node, inspect the checkpoint, and resume it. Explain which node reruns and why.

### Exercise 2: PostGIS experiment

Write or run the existing polygon round-trip integration test. Verify that the geometry survives storage and that area is calculated only after reprojection to an appropriate equal-area CRS.

### Exercise 3: COG and TiTiler experiment

Create one COG, upload it to MinIO, request TileJSON from TiTiler, and inspect one tile. Confirm bounds, zoom range, CRS, CORS, and transparency around nodata.

### Exercise 4: scientific failure experiment

Take a preprocessing test and deliberately remove one guard, such as the co-registration refusal or cloud mask. Confirm that the test fails for the reason the guard exists.

### Exercise 5: contract experiment

Change a fixture field name or enum value and run the contract tests. Trace the failure from the exported frontend schema to the backend fixture.

### Exercise 6: architecture review

Choose one service and draw its imports. Check it against `architecture-context.md`: adapters at the edge, services in the middle, pure math below, infrastructure behind `lib/`.

## 10. A Review Notebook Template

For each subsystem, write a short note with this shape:

```text
Subsystem:
User-visible purpose:
Primary entry point:
State/data it consumes:
State/data it produces:
Durable storage:
External dependencies:
Scientific or behavioral invariant:
Failure modes:
Tests proving the invariant:
Known gaps:
One change I would review carefully:
```

Do not begin by trying to memorize every file. Learn one vertical path, verify it by running a test, then widen the path one boundary at a time.

## 11. Current Study Milestone

You have understood the backend foundation when you can explain, without looking at the code:

1. why PostGIS, Redis, MinIO, SQLite, and TiTiler all exist;
2. how a user query becomes a LangGraph run;
3. how state differs from stream events and long-term memory;
4. how a COG reaches the globe;
5. how evidence is kept separate from language generation;
6. what is already built versus only specified;
7. where the planned message/audio persistence layer will belong;
8. which test would disprove your explanation.

That last point matters most. A backend review is not a tour of files; it is a set of claims tied to executable checks.
