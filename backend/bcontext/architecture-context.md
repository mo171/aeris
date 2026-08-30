# The authoritative layering, dependency rules and invariants for the AERIS backend.

**what** : Defines the layers, what each one may and may not do, which direction dependencies run, the
async rule, where maths is allowed to live, the scientific-correctness boundaries, and the numbered
invariants that every change is checked against.
**where**: Binding on every human and every AI agent writing backend code. `ai-workflow-rules.md` closes a
unit of work by asserting that no invariant in this document was violated — §13 is that list.
**how**  : Layering plus domain-oriented scientific pipelines, orchestrated entirely by LangGraph. The goal
is not maximum abstraction; it is a predictable, testable, **scientifically correct** system whose numbers
can be trusted.

> Read `product-truth.md` first for *why* the phases and seams are shaped this way.
> Read `folder-archtecture.md` for *where* a file goes. This document says *what may depend on what*.

---

# 1. What this backend is

AERIS is an agentic Earth-observation intelligence backend. It takes satellite imagery and a question in
natural language or speech, and returns an **evidence-grounded answer**: a claim, the georeferenced region
that supports it, the model and version that produced it, a confidence, and a full execution trace.

It combines:

- Imagery ingestion, validation and Cloud-Optimised GeoTIFF conversion
- Geospatial preprocessing — cloud masking, reprojection, co-registration, resampling, SAR calibration
- Deterministic analysis — spectral indices, geometry, area and count statistics
- Specialist model inference — segmentation, detection, change detection, grounding
- Vision-language reasoning over rendered figures and tiles
- **Visual rendering** — colourised index maps, mask overlays, annotated detections, before/after comparisons,
  sent to the frontend as finished images (`product-truth.md` §1.5, `api-contract.md` §6)
- Cross-modal optical–SAR late fusion
- Evidence localisation, confidence estimation and provenance
- Query understanding and deterministic routing
- Agent orchestration over two tool surfaces — analysis and interface
- A voice loop: recognition, spoken response, barge-in
- Report generation

**The central design rule of the whole system:** specialist models produce structured, checkable results;
the language model explains those results and is never permitted to invent one. The pipeline is strictly

```
Specialist model → structured result → spatial/temporal evidence → validation → language explanation
```

Every layer below exists to keep that ordering enforceable rather than merely intended.

# 2. Separation of responsibilities

These seven concerns stay separate. Collapsing any two of them is the failure mode this architecture exists
to prevent:

1. API / CLI concerns
2. Application logic
3. Scientific computation
4. Long-running execution
5. Agent orchestration
6. Data persistence
7. Infrastructure

# 3. The three flows

**Ordinary application flow**

```
Route (Phase 2)  |  CLI command (Phase 1)
  ↓
Controller
  ↓
Service
  ↓
Domain / helper function
  ↓
Model (SQLAlchemy)
  ↓
Database / infrastructure
```

**Scientific and long-running flow**

```
Phase 1: CLI command ─────────────────────────────┐
Phase 2: Route → Controller ──▶ Inngest function ─┤   (Inngest = trigger, retry, replay)
                                                  ↓
                                       Service (async def)
                                                  ↓
                            LangGraph StateGraph ──▶ checkpointer (resume point)
                                                  ↓
                       Pipeline node (async def) ──writes──▶ get_stream_writer()
                                                  ↓              (stream_mode="custom")
                       Domain scientific function (async def)
                                                  ↓
                      ┌───────────────────────────┴──────────────────────┐
                      ↓                                                  ↓
    math/ kernel (pure, sync, via asyncio.to_thread)      Database / object storage
```

Both phases invoke the **same graph**. Phase 1 calls `graph.astream()` from the CLI; Phase 2 calls it from
inside an Inngest function. Nothing in the graph knows which.

**Agent flow**

```
Operator (voice or text)
  ↓
Agent graph  ──▶ LangChain chat model (init_chat_model, bind_tools, with_structured_output)
  ↓
interrupt()  ──▶ plan returned for operator approval, run paused at a checkpoint
  ↓
Tool dispatch ─┬─▶ Analysis tool ─▶ Service ─▶ pipeline graph ─▶ scientific engine
               └─▶ Interface tool ─▶ `ui-command` event ─▶ frontend command bus (validates, then dispatches)
  ↓
Validated claims
  ↓
Answer generation  +  speech generation
  ↓
LangGraph stream ─▶ terminal renderer (Phase 1) | SSE / WebSocket (Phase 2)
```

# 4. Orchestration ownership — see ADR-002

Three libraries, three concerns, no overlap. **We do not rebuild what they provide.**

| Concern | Owner |
|---|---|
| Graph topology, typed state, conditional routing | **LangGraph** `StateGraph`, `add_conditional_edges` |
| Run state, resume from the last completed node | **LangGraph** checkpointer — SQLite in Phase 1, Postgres in Phase 2 |
| Plan approval before execution | **LangGraph** `interrupt()` |
| Streaming trace steps, ready layers, claims, tokens | **LangGraph** `get_stream_writer()` / `astream(stream_mode="custom")`, carrying our Pydantic event models |
| Cancellation and voice barge-in | `asyncio` task cancellation plus the checkpoint, so a cancelled run stays resumable |
| LLM calls, structured output, tool binding | **LangChain** — `init_chat_model`, `with_structured_output`, `bind_tools` |
| Durable background execution, retry with backoff, replay, dashboard | **Inngest**, Phase 2 (ADR-001) |

**We write no orchestration protocol of our own.** An earlier draft of the Phase 1 plan proposed three —
`StepRunner`, `EventSink` and `LLMProvider`. All three are **deleted** (ADR-002); each one reimplemented
something LangGraph or LangChain already ships, and the engineering days belong to co-registration, change
detection and evidence binding instead. If any document in this folder still describes them as things to
build, that document is stale and this section wins. What survives from them is the **event models** — they
are the wire contract with the frontend (`api-contract.md` §3) and are what nodes write into the stream.

"Custom stream" throughout these documents means **LangGraph's `stream_mode="custom"`**, a library feature.
It never means a streaming mechanism we wrote.

**One Inngest function wraps one graph invocation.** Inngest guarantees the run happens and is retryable;
LangGraph knows what the run is and where it got to. On retry the graph resumes from its checkpoint rather
than re-executing completed nodes. **The retry loop lives in Inngest and nowhere else** — no node, service
or domain function implements backoff, and no `try/except` re-runs a stage. In Phase 1, before Inngest is
bound, a failed run is re-invoked from the CLI and the checkpointer supplies the resume point.

**Consequence for every pipeline node:** it is an `async def` that takes typed state, returns a state update,
writes events to the stream, and is individually resumable. It does not know whether it is running under a
CLI, an HTTP request or an Inngest function, and it must not be able to find out.

**The one containment rule.** Chat-model and graph construction happen in `app/lib/llm/`; `agents/` and
`pipeline/nodes/` import a project module rather than a vendor package. This is an *import-location* rule of
roughly forty lines, and it is what makes the model and provider configurable from `config.py`. It is **not**
a wrapper — structured output, tool calling and streaming are used directly from the library.

# 5. Layer responsibilities

| Layer | Must | Must never |
|---|---|---|
| **Route** (Phase 2) | Declare path, method, status codes, request/response models | Contain logic. Touch a database. Call a model |
| **CLI command** (Phase 1) | Parse arguments, choose a stream renderer, call a controller | Contain logic that a route would also need |
| **Controller** | Validate input, call one service, shape the response | Perform computation. Compose multiple services into new behaviour |
| **Service** | Own a use case end to end; orchestrate domain functions and persistence | Know about HTTP, SSE, Typer or WebSockets. Contain a numerical method |
| **Pipeline node** | One stage (S1–S20). Take typed state, return a state update, emit events, check cancellation | Call another node directly. Reach into the database. Retry itself |
| **Domain function** | Pure computation on plain data; call into its `math/` module | Do I/O, read config, log business meaning, hold state |
| **`math/` module** | The numerical method itself — formulae, transforms, statistics, thresholds | Know what a scene, a claim or a run is. Import anything from the project except `constants/` |
| **Agent** | Plan, route, dispatch tools, synthesise from validated results | Compute a number. Invent evidence. Call a database |
| **Model** (SQLAlchemy) | Persistence shape | Carry business logic |
| **Worker / Inngest function** | Trigger, execute, retry, report | Decide what should run. Contain a stage's logic |
| **`lib/`** | Infrastructure clients and cross-cutting utilities | Import anything from `services/`, `agents/` or `routes/` |
| **`constants/`** | Fixed vocabularies | Import anything at all |

**Every layer in that table is `async def` except `math/`.** Routes, CLI commands, controllers, services,
pipeline nodes, domain functions, agents and tools are all coroutines; `math/` is the single sync surface in
the backend. §11 states the rule and the reason.

# 6. Dependency direction

```
routes / cli  →  controllers  →  services  →  domain  →  lib  →  constants
                                     ↓            ↓
                                  models        math/  →  constants
```

**One-way, always.** A service never imports a controller. Domain code never imports `lib`. A `math/` module
imports NumPy and `constants/` and nothing else from the project. `constants` imports nothing.

`cli/` and `routes/` are **sibling adapters over the same core.** Neither imports the other, and neither may
hold logic the other needs — if it is needed by both, it belongs in a service.

# 7. Domain boundaries

Each subsystem owns one question and exposes a typed interface — data in, artefacts out (PDF §16, the
M1–M22 module table).

| Subsystem | Owns | Stages |
|---|---|---|
| `imagery/` | Ingest, metadata, validation, COG conversion, tiling | S1–S6, S11 |
| `preprocessing/` | Cloud mask, reprojection, co-registration, resampling, SAR calibration | S7–S10 |
| `spectral/` | Index arithmetic and thresholds | S12 |
| `detection/` `segmentation/` `change_detection/` | Specialist inference and post-processing | S13 |
| `optical_sar/` | Per-sensor runs and late fusion | S13, S15 |
| `vqa/` `captioning/` `grounding/` | Vision-language reading | S14 |
| `evidence/` | Vectorisation, evidence and claim building, confidence, trace | S15, S18, S19 |
| `rendering/` | Array → finished image. Colour ramps, stretches, overlays, annotation, composition | S12, S13, S14, S17 |
| `pipeline/` | LangGraph state, nodes and graph composition | S1–S20 |
| `agents/` | Intent, planning, routing, tool dispatch | — |
| `voice/` | Transcription, synthesis, barge-in | — |
| `models/` | Registry, loading, VRAM-profiled residency | — |

**Every subsystem above that computes a number carries its own `math/`** (§12). `pipeline/` and `agents/` do
not, and must not: they orchestrate, and arithmetic inside a node or a planner is a boundary violation.

The **20-stage pipeline (PDF §15.1) is the domain spine.** Every trace step names its stage code. Not every
stage runs for every query — the SAR branch replaces S7 with radiometric calibration, speckle filtering and
terrain flattening, and an optical–SAR run executes both branches and joins at S15 under the late-fusion
policy (PDF §9, p.19).

# 8. Scientific-computing boundaries

This is where a backend of this kind actually fails. Each rule below has a specific wrong answer attached to
breaking it, and a confident wrong number is worse than an error.

1. **The cloud and shadow mask is applied before index arithmetic, never after.** Index values over cloud,
   shadow and water are not meaningful; they are masked, not reported.
2. **The co-registration residual gates the comparison.** Above tolerance the pipeline **refuses** to run
   change detection. A residual larger than the feature under discussion invalidates the comparison; it does
   not merely degrade it, and lowering a confidence score is not an honest substitute for refusing.
3. **Areas are computed in an equal-area projection.** Never from degrees. Hectares get quoted in reports.
4. **Nodata is never treated as zero.** It propagates as a mask through every operation.
5. **Band arithmetic runs on calibrated reflectance, not digital numbers.** Processing level is checked at
   S3 and carried; an index over uncorrected DN is a different quantity wearing the same name.
6. **Resampling method follows the data type** — nearest for categorical rasters and masks, bilinear or
   cubic for continuous. Interpolating a class label invents classes.
7. **SAR order is fixed**: calibration → speckle filtering → terrain correction. **Layover and shadow masks
   are retained**, because they are what distinguishes "radar saw nothing" from "radar could not see".
8. **Fusion is late, never early** (PDF §9). Keeping each sensor's evidence separable is what makes the
   joint answer auditable, and fusion **refuses** when co-registration is worse than sub-pixel.
9. **The language model never produces a figure.** It is handed claim objects and asked to phrase them.
   Enforced by construction, then tested for.
10. **Confidence is `float | None`.** `None` means AERIS declines to assert one. It is never coerced to
    `0.0`, which is the different and stronger claim that confidence is zero.
11. **Insufficient evidence is a successful outcome**, returned with remedies (PDF p.38) — not an exception.
12. **Every intermediate that a stage marks as producing an artefact is retained and addressable** (PDF
    §21.2). Provenance is not reconstructable after the fact.
13. **A rendered figure is evidence, not decoration.** The colour ramp and the stretch bounds decide what the
    operator — and the VLM at S14 — actually *sees*: widen a stretch and a drought disappears, narrow it and
    healthy crop looks stressed. So every figure records its render spec (bands, stretch, ramp, resampling,
    CRS, whether the mask was applied) and the `traceStepId` behind it, ships a machine-readable legend, and
    re-renders identically from that spec. **No number is drawn onto a figure that no claim carries.**
    Rendering happens here rather than in the browser for exactly this reason (ADR-004).

# 9. Tech stack

| Layer | Technology | Purpose |
|---|---|---|
| Language / env | **Python + `uv`** | `pyproject.toml` + `uv.lock`, `.venv` |
| Concurrency | **`asyncio`** | Every layer is `async def`; CPU-bound maths is offloaded with `asyncio.to_thread` — §11 |
| Phase 1 interface | **Typer** | The CLI adapter — the whole application before HTTP exists. Commands are async, run through `asyncio.run` at the command boundary |
| Phase 2 API | **FastAPI** | REST + SSE + WebSocket, async endpoints |
| Validation | **Pydantic** (+ `pydantic-settings`) | Schemas and configuration, camelCase on the wire |
| **Orchestration** | **LangGraph** `StateGraph` | Graph topology, typed state, conditional routing, checkpointer, `interrupt()`, `stream_mode="custom"` — ADR-002. **All of it. We write no orchestration code of our own** |
| Run persistence | **LangGraph checkpointer** | SQLite in Phase 1, Postgres in Phase 2. Resume-from-node, replay, plan approval |
| **Durable execution and retry** | **Inngest** (Phase 2) | Trigger, background execution, **retry with backoff**, replay, operator dashboard — ADR-001. One Inngest function wraps one graph invocation |
| LLM access | **LangChain** — `init_chat_model`, `with_structured_output`, `bind_tools` | Completion, structured output, tool calling. Constructed only in `app/lib/llm/` so the provider is a `config.py` change |
| Broker, cache, locks | **Redis** (docker) | Model-manager locks, short-lived cache, rate limits |
| Database | **Supabase Postgres + PostGIS** | Application data and spatial geometry |
| ORM / migrations | **SQLAlchemy (async) + Alembic** | `asyncpg` driver, `AsyncSession` |
| Object storage | **MinIO** (S3 API) | Raw scenes, COGs, artefacts, rendered figures, reports |
| Tile server | **TiTiler** | XYZ EPSG:3857 over COGs, server-side band selection and stretch |
| **Figure rendering** | **Matplotlib** (Agg backend) + **Pillow** | Colourbars, annotated overlays, side-by-side comparisons → WebP/PNG for the reference surface (`api-contract.md` §6). Headless and deterministic; never an interactive backend |
| Raster / geospatial | **Rasterio, GDAL, pyproj, Shapely, GeoPandas** | Sync libraries — called from `math/` or through `asyncio.to_thread` |
| Numerics | **NumPy, SciPy, scikit-image, scikit-learn** | Live in `math/` modules only |
| ML | **PyTorch** | Specialist models and the RS-VLM |
| Model residency | **`ModelManager`** | VRAM profile, lazy load, LRU eviction under an async lock |
| Speech | **faster-whisper** (STT), **Piper / Kokoro** (TTS) | Offline, in-backend, barge-in capable |
| Streaming | **LangGraph stream** → terminal (P1) / SSE + WebSocket (P2) | One producer, two transports, no adapter of ours in between |
| Auth | **Supabase JWT / OAuth2** (Phase 2.8) | |
| Containers | **Docker + Docker Compose** | Redis, MinIO, TiTiler, Inngest dev server |
| Testing | **Pytest** (+ `pytest-asyncio`), **HTTPX**, `jsonschema` | Unit, integration, and contract tests against vendored schemas |
| Logging / config | Structured JSON logging · `pydantic-settings` + `.env` | |

**Celery is not used.** ADR-001 rejected it in favour of Inngest. **`StepRunner`, `EventSink` and
`LLMProvider` are not used either** — ADR-002 deleted all three in favour of the libraries above.

# 10. Configuration and constants

Every environment-varying or one-time-decided value is read from `.env` through `config.py` and from nowhere
else — URLs, credentials, bucket names, model paths, VRAM profile, thresholds, timeouts, the LLM provider.
`os.environ` is read only inside `config.py`. Validation happens at import, so a bad variable fails at
startup rather than inside a worker an hour later.

Every fixed set lives in `app/constants/`. Two of those sets are **shared vocabulary with the frontend and
may not be invented here**: the S1–S20 stage codes and the twelve model ids (`api-contract.md` §7).

# 11. The backend is async. `math/` is the only exception.

**Every function in `app/` is declared `async def`.** Routes, CLI commands, controllers, services, pipeline
nodes, domain functions, agents, tools, `lib/` clients, model loaders, voice handlers — all of them. There is
no sync path through the application.

Why the rule is absolute rather than case-by-case: a single sync function in the middle of an async call
chain forces every caller above it to choose between blocking the event loop and wrapping the call. That
choice gets made differently in different files, and the result is a codebase where you cannot tell from a
signature whether calling something is safe. Uniformity is the point — `await` everywhere means no reader
ever has to check.

It is also what the rest of the stack already assumes. LangGraph nodes are awaited by `graph.astream()`,
FastAPI endpoints are coroutines, SQLAlchemy runs on `asyncpg` with `AsyncSession`, the voice loop needs
concurrent capture and synthesis, and barge-in is `asyncio` task cancellation. Async is not a preference
here; it is the shape of the surrounding libraries.

**The one exception, and why it exists.** A pure numerical kernel — an NDVI array operation, a reprojection,
a polygon simplification — is CPU-bound. Declaring it `async def` would be a lie: it never yields, so it
blocks the event loop for its whole duration while presenting a signature that says it does not. That is
strictly worse than being honest about it. So:

- **`math/` modules are sync `def`.** They are the only sync functions in `app/`.
- **Every call into `math/` from async code goes through `asyncio.to_thread(...)`** (or a process pool for
  work heavy enough to fight the GIL). The offload is written at the call site, where it is visible.
- Third-party sync libraries — Rasterio, GDAL, Shapely, pyproj, PyTorch's synchronous calls — are treated the
  same way: reached from a `math/` module or wrapped in `to_thread` at the boundary.

This is why the maths lives in its own module rather than inline: it makes the sync surface a **place** rather
than a scattering of exceptions, so "is this function safe to await" has a structural answer.

**Not negotiable, because it is not free later.** Converting a sync codebase to async is a rewrite of every
call site. Starting async costs nothing.

# 12. Maths lives in its own module, never inside the service that uses it

**A service, node or domain file that needs a numerical method does not contain that method.** The maths goes
in a sibling `math.py`, or a `math/` package when there is more than one file of it, inside that subsystem's
own folder.

```
services/spectral/
├── indices.py            # async. Chooses the index, maps bands per sensor, applies the mask, returns a result object.
└── math/
    ├── index_formulae.py # sync, pure. ndvi(nir, red) -> ndarray. No knowledge of scenes or sensors.
    └── thresholds.py     # sync, pure. Otsu, fixed cut-offs, histogram statistics.
```

**Why the separation is structural and not stylistic** — four reasons, each one a cost paid without it:

1. **The maths is the part that has to be provably right.** `code-standards.md` §11 requires deterministic
   numerics to be tested against values computed by hand or by an independent tool such as QGIS. A formula
   tangled up with band lookup, mask application, config reads and database writes cannot be tested that way
   without standing the whole system up. Isolated in `math/`, it is a pure function over arrays, and the test
   is three lines.
2. **It is where the thirteen boundaries in §8 are enforced or broken.** Equal-area reprojection before area,
   nodata propagating as a mask, reflectance rather than digital numbers, resampling method following data
   type. When those live in one named place per subsystem, they can be **read** and reviewed. Scattered
   through service logic, they can only be hoped for.
3. **It is the sync/async boundary** (§11). `math/` being the only sync surface is what makes the rule
   checkable rather than aspirational.
4. **It separates "which formula" from "the formula".** Choosing NDVI over NDWI for a query is application
   logic and changes often. `(nir - red) / (nir + red)` is physics and does not change. Mixing the two means
   every routing change touches code that should never be edited again.

**The dividing line.** `math/` knows arrays, numbers, geometries and CRS codes. It does **not** know what a
scene, a claim, a run, an investigation or a model id is, and it performs no I/O — those belong to the async
service that calls it. If a `math/` function needs a `Scene`, the split was made in the wrong place.

Subsystems this applies to today: `imagery/` (resampling, windowing), `preprocessing/` (masking,
co-registration residual, SAR calibration and speckle), `spectral/` (index formulae, thresholds),
`detection/` `segmentation/` `change_detection/` (post-processing, morphology, vectorisation, geometry),
`optical_sar/` (alignment, late-fusion arithmetic), `evidence/` (area in an equal-area CRS, geometry
simplification, confidence aggregation), `rendering/` (colour-ramp mapping, stretch computation, array →
RGBA). See `folder-archtecture.md` for the placed files.

# 13. Invariants

`ai-workflow-rules.md` closes a unit of work by asserting that none of these was violated.

1. Dependencies run one way: `routes/cli → controllers → services → domain → lib → constants`, and
   `domain → math/ → constants`.
2. `cli/` and `routes/` are siblings. Neither imports the other; neither holds logic the other needs.
3. No pipeline node, service or domain function knows its transport. Events are written to the LangGraph
   stream (`get_stream_writer()`), never to a socket, a print or a file.
4. **No orchestration, checkpointing, streaming or retry mechanism is hand-written.** Graph, state, resume
   and stream come from LangGraph; retry with backoff and replay come from Inngest; LLM access comes from
   LangChain. No `StepRunner`, no `EventSink`, no `LLMProvider`.
5. No pipeline node performs its own retry or its own state persistence. There is no backoff loop anywhere
   in `app/`.
6. Every pipeline node is cancellable at its boundary, and a cancelled run remains resumable from its
   checkpoint.
7. **Every function in `app/` is `async def`, except functions inside a `math/` module or `math.py`, which
   are sync and are always called through `asyncio.to_thread`.**
8. **No numerical method is written inside a service, node, controller or route.** It lives in that
   subsystem's `math/`.
9. Domain functions are pure: no I/O, no config reads, no global state.
10. `os.environ` is read only in `config.py`.
11. No hardcoded fixed set outside `app/constants/`.
12. Stage codes and model ids match the frontend's vocabulary exactly.
13. Every claim resolves to georeferenced evidence, a model id, a model version, a trace step and a
    confidence that may be `None` but is never `0.0` by default.
14. Every mask is produced in both representations — raster for display, vector for evidence.
15. The language model never emits a quantity that a specialist did not produce.
16. All thirteen scientific boundaries in §8 hold.
17. Anything crossing a boundary is a Pydantic model, serialised camelCase, validated against the vendored
    contracts in `bcontext/contracts/`.
18. No vendor SDK is imported outside its adapter in `lib/`. LangChain and LangGraph construction happens in
    `app/lib/llm/`; `agents/` and `pipeline/nodes/` import a project module.
19. **Every rendered figure carries its render spec, its `traceStepId` and a machine-readable legend**, and
    re-renders identically from that spec. No figure is emitted without a stage behind it.

# 14. What this document does not own

| Question | Document |
|---|---|
| Why we are building it this way | `product-truth.md` |
| What to build next, and its gate | `roadmap.md` |
| Where a file goes | `folder-archtecture.md` |
| How a file is written | `code-standards.md` |
| The wire format | `api-contract.md` |
| Why a technology was chosen | `architecture-decisions.md` |
| What the previous session did | `memory.md` |
