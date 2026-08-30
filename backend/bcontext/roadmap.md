# The build order. What to do next, and how you know it is done.

**what** : Every phase and sub-phase of the backend, each with its research inputs, its deliverable and the
**gate** that closes it. Carries the live status column.
**where**: Read at the start of every session to find the current sub-phase; updated at the end of every
session. This is the plan of record — a task not on it is out of scope until it is added here.
**how**  : Phase 0 provisions infrastructure and establishes a setup pattern. Phase 1 builds the entire
application as a CLI. Phase 2 serves it. Sub-phases are ordered by dependency, not by appeal. A gate is a
statement that can be demonstrated, not a feeling that the code looks finished.

> Read `product-truth.md` first — it explains *why* the phases are split this way.
> Status values: `todo` · `in-progress` · `gated` (built, gate not yet demonstrated) · `done`.

---

## Standing rules for every sub-phase

1. **Research first, and only as far as it changes the code.** Open the PDF pages listed. Use `notebooks/` to
   work the problem when the answer would change what you write next — a threshold, a band mapping, a failure
   mode, a refusal condition. **A notebook written because this plan says "notebook" is wasted work.** If you
   already know the answer, say so in `memory.md` and go to rule 2. If you do run one, use the conclusion:
   put it in a constant, a doc, or a comment naming the failure mode. Nothing ships out of a notebook;
   conclusions do (`README.md` → "How you are expected to work here").
2. **Then write it.** Following `code-standards.md`.
3. **Then test it.** Automated tests, then the product owner exercises it.
4. **Then record it.** Append to `memory.md`; update the status column here.

**Three rules that apply to every deliverable below and are not repeated in each one:**

- **Every function is `async def`**, except functions inside a `math/` module, which are sync and are called
  through `asyncio.to_thread` (`code-standards.md` §7).
- **No numerical method is written inside a service, node, controller or route.** It goes in that
  subsystem's `math/` (`code-standards.md` §8).
- **No orchestration, checkpointing, streaming or retry code is written at all.** LangGraph owns the graph,
  its state, its resume and its stream; Inngest owns retry and replay; LangChain owns LLM access (ADR-002).

**Phase 0 establishes the setup pattern.** Every dependency added anywhere in the project repeats it:

```
provision (docker/cloud)  →  typed client in app/lib/  →  health probe  →  a row in `aeris doctor`  →  a test
```

---

# Phase 0 — Foundation and infrastructure

Nothing is built on an unverified dependency. Phase 0 ends when one command proves every piece of
infrastructure is reachable, correctly configured, and the right version.

| # | Sub-phase | Deliverable | Gate | Status |
|---|---|---|---|---|
| 0.1 | **Project skeleton** | `uv` + `.venv` migration from `requirements.txt` to `pyproject.toml` + `uv.lock`. `config.py` as a `pydantic-settings` model. `.env` / `.env.example`. `app/constants/` seeded. `app/lib/logger.py` (structured JSON), `exceptions.py`, `responses.py`. | `uv sync` reproduces the environment from a clean clone; importing `config` with a missing variable fails loudly and names it. | **done** — `uv lock --check` and `uv sync --frozen` clean; import-time failure names the field; 12 tests pass. Python pinned `>=3.14,<3.15` after verifying cp314 wheels exist for torch/transformers/timm/ctranslate2/faster-whisper/onnxruntime. |
| 0.2 | **Supabase + PostGIS** | Connection through `app/lib/database.py` (SQLAlchemy, async). PostGIS extension enabled. Alembic initialised. First migration: `scenes`, `investigations`, `runs`, `evidence`, `claims`, `trace_steps`, `missions` with geometry columns. | A round trip that writes a polygon and reads it back with a correct area in an equal-area projection. | **done** — `alembic upgrade head` from base creates 8 tables, 7 GiST indexes, 24 check constraints; `alembic downgrade base` removes all of them; `alembic check` reports no changes (models match schema); 25/25 tests pass, including the 4 integration tests. PostGIS 3.5.2 on Postgres 17.5. Local container on host port **5433** (5432 was occupied). |
| 0.3 | **Redis (docker)** | `app/lib/redis.py`. Two uses, kept separate: model-manager locks and short-lived cache. Async client. | Set/get round trip; a lock held by one process blocks a second and releases on crash. | **done** — 6 integration tests, 33/33 suite green. Round trip preserves the value and carries a TTL; a second acquirer waits then is refused with `CONFLICT`; an abandoned lock is reacquired only after its TTL expires. Each of the three load-bearing claims was re-checked by breaking the code it rests on. Redis 8.2.9, `maxmemory-policy noeviction` — asserted, because any other policy lets the server evict a *held* lock. |
| 0.4 | **MinIO (docker)** | `app/lib/storage.py` over the S3 API, async. Buckets `raw`, `cog`, `artefacts`, `figures`, `reports`. Presigned PUT/GET. | A file uploaded through a presigned URL is readable back by key; CORS configured on the browser-facing buckets — **not** because a plain `<img>` needs it (measured: it does not) but because `fetch()` and `crossOrigin` → canvas → `getImageData` do, which is Cesium's path for every tile (`api-contract.md` §8 rule 2). | **done** — 12 integration tests, 45/45 suite green. Presigned PUT performed with no credentials and no SDK, read back byte-identical. **MinIO does not implement `PutBucketCors`** (measured: `NotImplemented`), so CORS is server-level via `MINIO_API_CORS_ALLOW_ORIGIN`; the code applies per-bucket rules where S3 supports them. Proven in a real browser at the allowed origin, and proven to fail from a disallowed one. |
| 0.5 | **Inngest (registered, not yet bound)** | Dev server in compose, event keys in config, connectivity proven. **No workflow logic** — Phase 1 durability comes from the LangGraph checkpointer, and Inngest is bound in Phase 2.5 (ADR-002). | The dev server is reachable and a hello-world event is received. Recorded as *deferred by design*. | **done, and deferred by design** — 8 integration tests, 53/53 suite green. An event sent through the SDK is read back off the bus by id; acceptance alone is not treated as delivery. `inngest/inngest:v1.44.0`, SDK 0.5.19 on cp314. **No function is registered, and a test asserts that** — if one appears before 2.5, it fails and asks whether the durability decision changed. |
| 0.6 | **`aeris doctor`** | One CLI command printing a table: every dependency, reachable yes/no, version, latency, and the config values in force (secrets masked). | `aeris doctor` is green on a clean machine after `docker compose up`. **This is the command the product owner runs to verify a setup.** | **done** — 10 tests, 63/63 suite green three runs running. 7 rows: PostGIS, schema revision, Redis, storage, storage CORS, Inngest, Inngest round trip. Exits 0/1 and the exit code is asserted from a subprocess. Demonstrated against a never-migrated database and an unused bucket prefix: exit 1 naming both problems, then exit 0 after the remedy it printed. |
| 0.7 | **Contract vendoring** | A script exports the frontend's Zod schemas to JSON Schema into `bcontext/contracts/`. A pytest validates backend fixtures against them. | A deliberately wrong field name fails the contract test. | **done** — `pnpm run contracts:export` writes **92 schemas from 14 modules** (Zod 4's own `z.toJSONSchema`, `io: "input"`, deterministic). 34 tests, 97/97 suite green. **22 of 27 backend enums are checked against the frontend's**, and every enum on either side must be classified or the suite fails. Gate written as the real mistake — `model_dump()` without `by_alias=True` — not a hand-typed typo. |

**Phase 0 is complete.** 0.1–0.7 all done; 97 tests green.

**Phase 0 gate:** on a machine that has never run this project —

```
docker compose up -d          # four services: postgis, redis, minio, inngest
uv run alembic upgrade head   # the schema. `aeris doctor` reports its absence but will not apply it
uv run aeris doctor           # exit 0, every row green
```

Three commands, not two. `aeris doctor` provisions storage buckets and proves the event round trip, but it
deliberately **does not run migrations** — a diagnostic that alters a schema is a diagnostic nobody can run
safely against a database they care about. It reports the missing revision and names the command instead.

---

# Phase 1 — The whole engine, as a CLI

No routes. No controllers. No WebSockets. At the end of Phase 1 you can hold a spoken conversation with
AERIS in a terminal and it runs real analyses over real imagery and speaks real answers back.

## 1.0 — CLI skeleton and the LangGraph spine

**Research:** LangGraph's `StateGraph`, checkpointers, `interrupt()` and `stream_mode="custom"`. Read the
docs before writing, because most of this sub-phase is *configuring* a library rather than building one.

**Deliverable**
- `app/cli/` — Typer application, sibling to the future `app/routes/` and never a dependency of it. Every
  command is `async def`; `asyncio.run()` is called in `cli/main.py` and nowhere else.
- `app/schemas/events/` — the event models, which *are* the frontend's stream events (`api-contract.md` §3).
  **Models only, no protocol.**
- `app/services/pipeline/state.py` — the `TypedDict` state schema the graph carries between nodes.
- `app/services/pipeline/checkpointer.py` — selects the SQLite checkpointer from `config.py` (Postgres in
  Phase 2). **This is the whole of resume, replay and durability.** Nothing is hand-written.
- `app/services/pipeline/stream.py` — thin helpers writing those event models through
  `get_stream_writer()`.
- `app/cli/renderers/` — two consumers of the stream: `trace_renderer.py` draws the live S1–S20 trace in the
  terminal, `journal_writer.py` appends `runs/<run_id>.jsonl`.
- A two-node throwaway graph to exercise all of the above end to end.
- **Cancellation**: `asyncio` cancellation checked at every node boundary, leaving the checkpoint intact.
  Used only by *explicit* abandonment — **not** by barge-in (`product-truth.md` §1.3, corrected 2026-08-31).
  Cheap only if it exists now.
- **The run is a detached task, not an awaited call.** `app/services/sessions/` — a session owns a thread id,
  a checkpointer thread and the set of runs launched under it; starting a run returns a handle immediately
  while `graph.astream()` is consumed by a background task that fans its events to the registered renderers.
  **This is the structural consequence of §1.3.1** and the reason it is in 1.0: a spine that awaits a run to
  completion inside the turn cannot narrate it, cannot be spoken over, and cannot answer anything else while
  it runs. Retrofitting that is a rewrite of every node signature.
- **Thread memory now, long-term memory wired but empty.** The checkpointer already gives the thread; the
  long-term namespace is a `BaseStore` selected from `config.py` alongside it, with `remember` / `recall` as
  ordinary tools the agent gains in 1.9. Nothing is hand-rolled and nothing is populated yet — what 1.0 owes
  is that the store exists, is configured in one place, and that a session carries its namespace.

**Explicitly not built**: `StepRunner`, `EventSink`, `LLMProvider`, an executor, a context object, or a retry
loop. See ADR-002 and `folder-archtecture.md` → "Folders that were deliberately removed".

**Gate**
- `aeris run --replay <run_id>` reproduces a completed run from its journal without recomputing.
- A run killed mid-pipeline resumes from its last checkpoint, not from the beginning.
- An **explicitly abandoned** run stops within one node boundary, emits `run-error` with a cancellation
  reason, and is still resumable afterwards.
- **A run survives being interrupted.** With a run in flight, a second command issued into the same session
  is accepted and answered while the run continues, and the run still reaches `run-complete` with the same
  journal it would have produced undisturbed. This is the gate that proves §1.3, and it fails on any design
  that awaits the run inline.
- The JSONL journal validates against the vendored contracts (0.7) — Phase 2 wire compatibility, proven now.

## 1.1 — Datasets

**Research:** PDF pp.21–24 (Table 5, the dataset catalogue) and p.45–47 (learning roadmap).
Notebook: `notebooks/02_data_exploration/`.

**Deliverable** — acquire, licence-check and catalogue every dataset the later phases need. One loader
interface; one notebook per dataset that loads it, plots a sample and records its quirks.

| Dataset | Unlocks | Sub-phase |
|---|---|---|
| Sentinel-2 L2A + Sentinel-1 GRD scenes over a chosen AOI | everything | 1.2–1.5 |
| **LEVIR-CD**, S2Looking | change detection training and the change gate | 1.6 |
| SECOND | semantic change | 1.6 |
| **DOTA**, DIOR | object detection | 1.6 |
| LoveDA, OpenEarthMap | land-cover segmentation | 1.6 |
| **RSVQA** LR/HR, **VRSBench** | VQA and the primary VLM benchmark | 1.7, 1.14 |
| DIOR-RSVG, RRSIS-D | grounding | 1.6 |
| **SEN12MS**, BigEarthNet-MM | optical–SAR pairing and fusion | 1.11 |
| EuroSAT | sanity checks and fast demos | throughout |

**Gate** — `aeris dataset list` reports every dataset with its on-disk location, size, licence and
redistribution status. Every one loads through a single loader. **Licences are recorded before any training
begins**, not after; most are research-licensed and several forbid redistribution.

## 1.2 — Raster engine · S1–S6, S11 · plus tiles

**Research:** PDF pp.12–14 (resolutions, sensors, formats, CRS) and §15 (the 20-stage pipeline).
Notebook: `01_remote_sensing/` — already started.

**Deliverable** — ingestion, format and driver identification, metadata extraction, CRS detection and
validation, band identification, quality checks (nodata fraction, histogram sanity, resolution report),
**COG conversion into MinIO**, and windowed tiling with overlap for inference.

Then **TiTiler** in compose, serving those COGs.

**Gate** — *an NDVI COG produced by this pipeline, stored in MinIO, rendered in a browser through TiTiler:
EPSG:3857 XYZ, CORS headers present, alpha channel transparent over nodata, and TileJSON carrying correct
`bounds` / `minzoom` / `maxzoom`.*

This gate is deliberately early. The frontend's memory names CORS as "the most common first-day failure",
and a tile contract that is wrong is far cheaper to discover now than in Phase 2.

## 1.2.1 — Visual products · the figures the backend sends

**Requirement:** `product-truth.md` §1.5. **Wire:** `api-contract.md` §6. **Invariant:** `architecture-context.md`
§8 rule 13 and invariant 19.

**Research:** none needed, and no notebook. `notebooks/01_remote_sensing/` already establishes the idiom this
sub-phase productionises — `imshow` with a named ramp and explicit `vmin`/`vmax`, a labelled colourbar, masks
as binary images, SAR as `10·log10` stretched to a dB window. The conclusion is already drawn; this turns it
into library code.

**Deliverable** — `app/services/rendering/`: the array → finished image primitive.

- `math/color_ramps.py`, `math/stretch.py`, `math/rasterize.py` — sync and pure. Named ramp → lookup table;
  percentile / min-max / fixed stretch; scaled array + ramp + alpha → RGBA with nodata transparent.
- `figures.py`, `overlays.py`, `comparisons.py`, `legends.py` — async. These *choose* the ramp and the stretch,
  compose the image, write it to MinIO's `figures` bucket and emit `figure-ready`.
- `constants/color_ramps.py` and `constants/figure_kinds.py` — the named vocabularies, shared with the
  frontend's legends and never invented in a service.
- `schemas/events/figure.py` — the `figure-ready` event, its machine-readable legend, its `renderSpec`.
- `cli/renderers/figure_writer.py` — writes each figure to `runs/<run_id>/figures/` and prints the path, so
  the whole capability is exercisable in Phase 1 with no browser, exactly as `journal_writer.py` makes the
  wire testable before a route exists.

**Matplotlib on the `Agg` backend, never an interactive one**, plus Pillow for composition. WebP with a PNG
fallback, alpha always, lossy forbidden for masks and permitted for RGB composites.

**Why here.** 1.4 produces the first index array, 1.5 the first mask polygons, 1.6 the first boxes, and 1.7
hands a rendered image to the VLM. Building the primitive before any of them means each emits its figure as it
lands instead of being retrofitted, and it keeps the boundary honest while the tile work of 1.2 is still fresh:
**a tile is a fragment for the globe with no legend; a figure is a self-contained picture that carries its own**
(`api-contract.md` §8).

**Gate** — three figures rendered from the scene that closed 1.2 and nothing more: a true-colour RGB
composite, its NDVI array as a colourised index map with a drawn colourbar, and a binary mask over that
composite. Each carries a machine-readable legend, a non-null `traceStepId` and a complete `renderSpec`; each
is written to `runs/<run_id>/figures/` and to MinIO. **Re-rendering from the recorded `renderSpec` is
byte-identical**, and a figure emitted with a null `traceStepId` fails a test.

Later sub-phases add figure *kinds*, not rendering code: 1.3 the SAR backscatter dB figure, 1.5 the
T1 | T2 | change-mask comparison, 1.6 the detection overlay with boxes and labels.

## 1.3 — Preprocessing · S7–S10 and the SAR branch

**Research:** PDF pp.12–14 and §15.1. Notebooks `04_sar_fundamentals`, `05_preprocessing` — already started.

**Deliverable** — cloud and shadow masking (`s2cloudless`), reprojection and grid alignment,
**co-registration with a reported residual**, resampling onto one grid; and for radar: radiometric
calibration, speckle filtering, terrain correction, with **layover and shadow masks retained**.

The numerical methods go in `services/preprocessing/math/` — `registration_residual.py`, `grid_alignment.py`,
`speckle_filters.py`, `terrain_flattening.py`, `cloud_probability.py`. The async service files above them
decide *when* to run each one and, critically, **when to refuse**.

Two rules that carry the correctness of everything downstream:

- **The cloud mask is applied before index arithmetic, never after.** Index values over cloud, shadow and
  water are not meaningful and are masked rather than reported.
- **The co-registration residual gates the comparison.** Above tolerance, the pipeline *refuses* to run
  change detection rather than running it and lowering a confidence score. A residual larger than the
  feature under discussion invalidates the comparison; it does not merely degrade it.

**Gate** — residual measured on a known-good and a known-bad pair; the bad pair is refused with a stated
reason. Layover/shadow masks are what let the system distinguish "radar saw nothing" from "radar could not
see", and that distinction is demonstrated.

## 1.4 — Spectral indices and geospatial statistics · S12, S15 measurement

**Research:** PDF pp.12–14 (index formulae) and p.9 (why deterministic tools, not learned approximations).

**Deliverable** — NDVI, EVI, SAVI, NDWI, MNDWI, NDBI, NBR with validated band mapping per sensor;
thresholding; and the statistics engine: area, counts, density.

**This sub-phase is the reference example of the maths rule.** The formulae go in
`services/spectral/math/index_formulae.py` and the thresholds in `math/thresholds.py` — sync, pure, arrays in
and arrays out. `services/spectral/indices.py` is async and holds only the application logic: which index the
query needs, which bands that index maps to on this sensor, applying the cloud mask first, and building the
result object. Area, counts and density land in `services/evidence/math/area.py`.

**Areas are computed by reprojecting to an equal-area CRS, never from degrees.** Hectares are a number an
operator will quote in a report.

**Gate** — the first end-to-end vertical slice: `aeris analyse --scene <id> --query "unhealthy vegetation"`
produces an NDVI map, a stressed-region mask and an area in hectares, **checked against QGIS on the same
scene**. Fully deterministic, so it is fully testable — and because the arithmetic sits in `math/`, the unit
test is a handful of lines against hand-computed values.

## 1.5 — Evidence, confidence and provenance · S15, S18, S19

**Research:** PDF p.38 (evidence-grounded answers, the answer object) and pp.38–39 (auditable trace).

**Deliverable** — mask vectorisation (raster → polygons → simplified geometry), the evidence builder, the
claim builder, confidence aggregation, and the trace/provenance writer.

Vectorisation and simplification go in `services/segmentation/math/vectorize.py` and
`services/evidence/math/simplification.py`; hectares in `evidence/math/area.py`; the aggregation rule in
`evidence/math/confidence_aggregation.py`. `builder.py` and `trace.py` stay async and hold no arithmetic.

**Every mask is produced in both representations**: raster tiles for display *and* GeoJSON polygons for
evidence. Raster alone is a picture; polygons are what make a claim clickable and auditable. Every polygon
carries `areaHectares`, `magnitude`, `confidence`, `modelId`, `modelVersion`, `traceStepId`.

**Confidence is `float | None`. `None` means AERIS declines to assert one and is never coerced to 0.**

**Figures join the same chain.** Every figure the run rendered (1.2.1) carries the `traceStepId` of the stage
it draws and the ids of the claims it supports, so "which image was that number read off, and drawn with which
stretch" is answerable from the run record alone. A figure with no stage behind it is not emitted.

**Gate** — every claim in a run resolves to pixels; every trace step that produced an intermediate carries
its artefact URI; **every figure resolves to a trace step**; the run's JSONL validates against the vendored
contracts.

## 1.6 — Specialist models · S13

**Research:** PDF pp.17–18 (change detection architectures and failure modes), p.17 (grounding), p.20–21
(model comparison). Notebooks `05_grounding`, `06_segmentation`, `07_change_detection`.

**Deliverable**
- `app/models/registry.py` and `manager.py` — the **VRAM-profiled `ModelManager`**: profile detection,
  lazy load, LRU eviction under a lock, and health state (`online` / `warming` / `degraded` / `offline`)
  plus `queueDepth` exposed exactly as the frontend's fleet strip expects.
- Change detection (ChangeFormer-class, LEVIR-CD-trained), segmentation (SegFormer-class),
  detection (DOTA/DIOR), grounding (Grounding DINO + SAM), SAR change (log-ratio / coherence).

**Gate** — change mask plus area statistics computed for a LEVIR-CD test pair, scored against ground truth.
Two models requested back-to-back on the 8 GB profile: the first evicts, the second loads, neither crashes,
and `warming` is observable in the status output.

## 1.7 — VLM and constrained answer generation · S14, S16

**Research:** PDF pp.15–16 (captioning and VQA), p.8 (why a VLM alone is insufficient).

**Deliverable** — RS-VLM serving (quantised to the VRAM profile), VQA and captioning **over the figures
rendered in 1.2.1** — the model reads the same image the operator is shown, which is why those renders are
deterministic and carry a recorded `renderSpec` — and the **constrained answer generator**: language produced
*from the structured results*, with the numbers injected rather than generated.

**The VLM cannot emit a figure that no specialist produced.** This is enforced by construction — it is
given the claim objects and asked to phrase them — and then tested for.

**Gate** — single-image question and answer in the CLI. A test that seeds a claim with a known number and
asserts the number in the answer text is exactly that number.

## 1.8 — Query understanding and routing

**Research:** PDF pp.24–25 (why deterministic routing rather than an autonomous agent) and p.37 (six routing
examples end to end).

**Deliverable** — intent classification over the nine intents the frontend already declares (`SCENE_VQA`,
`GROUND`, `INDEX_QUERY`, `DETECT`, `SEGMENT`, `CHANGE_DETECT`, `CHANGE_VQA`, `CROSS_MODAL`,
`EVIDENCE_RECALL`), extraction of objects, spatial region, temporal range and modality, then
**deterministic routing** to a pipeline graph.

Routing is deterministic by design (PDF p.24): a model chooses the *intent*, a table chooses the *pipeline*.
A wrong intent is recoverable and visible; a hallucinated pipeline is neither.

**Gate** — ≥95% intent accuracy on a labelled query set of at least 200 queries, held out. Matches the
PDF's Phase 4 gate.

## 1.9 — The agent, tool calling and the provider swap

**Research:** PDF pp.24–25. LangGraph `interrupt()` and LangChain `bind_tools` / `with_structured_output`.
Frontend `lib/command-bus/` and `lib/constants/commands.ts`.

**Deliverable**
- `app/lib/llm/chat_model.py` — `init_chat_model` called with the provider and model from `config.py`.
  Roughly forty lines. **Not a protocol, not an adapter set** — ADR-002 cancelled `LLMProvider`.
- `app/agents/` — the agent `StateGraph`, planner, deterministic router, tool dispatch, state. Analysis tools
  are backend functions bound with `bind_tools`; **interface tools are the frontend command registry**,
  mirrored into `app/constants/ui_commands.py` and emitted as `ui-command` events.
- The plan is returned **before execution** via `interrupt()`, so the operator can strike steps out (`/plan`,
  and `analysisPlanSchema` on the frontend). The run is paused at a checkpoint while it waits.

**Gate** — the full test suite passes against a second provider with only a `.env` change and no code edit.
This was previously "write a second adapter", which `init_chat_model` reduces to a configuration change; the
gate is kept because the *claim* still needs proving, only the work shrank.

## 1.10 — Pipeline graphs

**Deliverable** — `single_image_graph`, `temporal_graph`, `cross_modal_graph`, each a `StateGraph` composing
the nodes built in 1.2–1.9, each routing with `add_conditional_edges` over a plain lookup table (the
deterministic router of PDF p.24, expressed as a graph), and each emitting the full S1–S20 trace into the
LangGraph stream.

**Gate** — all three graphs run end to end from the CLI, resume correctly after a kill, and their journals
validate against the contracts.

## 1.11 — Cross-modal fusion

**Research:** PDF p.19 (fusion strategies, and when to fuse at all).

**Deliverable** — two *independent* per-sensor runs joined by **late fusion**, the agreement ledger
(`agreementRowSchema`), the modality advisory, and the refusal states.

Late rather than early fusion, because keeping each sensor's evidence separable is what makes the joint
answer auditable. **Fusion refuses** when co-registration is worse than sub-pixel, or when one sensor's
silence carries no information.

**Gate** — an optical/radar pair over the same ground produces a ledger with at least one row in each of
agreement and disagreement, each with a stated physical cause.

## 1.12 — Report generation

**Deliverable** — the sectioned report (`reportSectionKindSchema`: summary, inputs, findings, evidence,
models, confidence, limitations, conclusion), streamed section by section, exportable as JSON and GeoJSON.
PDF rendering may follow in Phase 2.

**Gate** — a generated report's every figure traces to a claim, and its every claim traces to a trace step.

## 1.13 — The voice loop

**Research:** `product-truth.md` §1. This is the product's identity.

**Deliverable**
- `faster-whisper` transcription, with voice-activity detection and a wake path.
- Utterance → agent → analysis tools **and** `ui-command` events → answer.
- **`speech` generation from the validated claim object**, not from the answer text.
- Piper/Kokoro synthesis, streamed.
- **Barge-in**: speaking over AERIS stops *that utterance's synthesis*. The run continues (`product-truth.md`
  §1.3). Standby suppresses speech without touching the run; only an explicit "stop this run" abandons it.
- **Narration and provisional answers**: spoken progress generated from trace steps, and a mid-run question
  answered from model knowledge, labelled provisional with empty `claimIds`, then superseded by the grounded
  utterance when the run completes.

**Gate** — *a full spoken investigation in the terminal.* The operator asks a question aloud; AERIS states
its plan aloud, runs a real analysis over real imagery, and speaks a real answer with a real number in it.
The operator speaks over it mid-answer, asks something unrelated, gets a provisional answer marked as such —
**and the original run finishes and reports back anyway.** `ui-command` events are printed where the frontend
will later dispatch them.

## 1.14 — Evaluation

**Research:** PDF p.39 (the evaluation framework).

**Deliverable** — a harness scoring: change detection on LEVIR-CD, VQA and captioning on a VRSBench subset,
grounding, routing accuracy, and system-level latency and VRAM under both profiles.

**Gate** — a single command produces the scorecard, and it is committed so regressions are visible.

---

# Phase 2 — Serving

Phase 2 adds adapters over the Phase 1 core. **It deletes nothing and moves no logic.**

| # | Sub-phase | Deliverable | Gate |
|---|---|---|---|
| 2.0 | FastAPI shell | `main.py`, error handler, request logging, CORS, `/health`, `/ready` | `aeris doctor` equivalent over HTTP |
| 2.1 | Read endpoints | imagery (cursor-paginated), missions, globe markers and tracks, model status, catalogue search | Frontend runs with `NEXT_PUBLIC_USE_MOCK_DATA=false` for read paths |
| 2.2 | Upload flow | `POST /imagery/upload-ticket` → direct-to-MinIO PUT → `POST /imagery/:id/confirm` | A multi-GB scene uploads without passing through the app server |
| 2.3 | Investigations + SSE | create/get/patch, attach scene, `/runs` as SSE over the same `graph.astream()` the CLI consumes, plus the two figure endpoints of `api-contract.md` §6 — the list and the image bytes, CORS on and immutably cacheable | The frontend's existing parsers consume a live run with no client change; a `figure-ready` event's `imageUrl` loads in a browser |
| 2.4 | WebSocket | Bidirectional: audio frames in, events out | Voice from the browser, end to end |
| 2.5 | Inngest binding | `app/inngest/functions/` — one function per graph invocation, carrying the retry and backoff policy. The graphs do not change; the checkpointer moves from SQLite to Postgres | The same run produces an identical journal invoked from the CLI and from Inngest, and a forced mid-run failure is retried and resumes from its checkpoint rather than from S1 |
| 2.6 | Tiles | TiTiler promoted from the 1.2 gate to a supported service; band selection and stretch via query params | Band math is server-side; the browser never does it |
| 2.7 | Voice + `ui-command` over the wire | `speech` and `ui-command` events on the live stream | Speaking to the browser flies the camera and raises a layer |
| 2.8 | Auth | JWT/OAuth2 via Supabase | |
| 2.9 | Integration and demo hardening | PDF Phase 10: offline bundle, pre-computed fallback scenes, rehearsed script, freeze | The full demo script passes three consecutive runs |

---

## Folder additions this plan requires

`folder-archtecture.md` was rewritten on 2026-08-30 and already carries all of them. Summarised:

```
backend/
├── app/
│   ├── cli/                 # Phase 1 adapter + renderers/. Sibling to routes/, never imported by it.
│   ├── schemas/events/      # the stream event models (no protocol)
│   ├── services/pipeline/   # state.py, checkpointer.py, stream.py, cancellation.py, nodes/, graphs/
│   ├── services/rendering/  # array -> finished image. figures, overlays, comparisons, legends + math/
│   ├── services/*/math/     # the numerical methods, sync and pure - one per computing subsystem
│   ├── lib/llm/             # init_chat_model from config. ~40 lines.
│   ├── inngest/functions/   # (Phase 2) replaces workers/. The only retry loop in the project.
│   ├── db/                  # SQLAlchemy models + async repositories
│   └── voice/               # transcription, synthesis, barge-in
└── bcontext/
    └── contracts/           # JSON Schema exported from the frontend's Zod. Generated, not authored.
```

## Explicitly deferred, and why

- **Continuous monitoring and alerting** — needs scheduling and acquisition automation that the SIH scope
  cannot supply (PDF p.42). The `missions` table exists; the scheduler does not.
- **Hyperspectral** — no dataset, no demo value at this tier.
- **Fine-tuning beyond change detection** — pretrained models first. Fine-tune only where a gate fails.
- **PDF rendering of reports** — JSON and GeoJSON in Phase 1; PDF in Phase 2 if it earns the time.
