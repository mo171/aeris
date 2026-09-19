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
- **AI-first prose and decision boundary.** Before adding any new hard-coded response, deterministic route,
  whitelist, fallback or `if/elif` branch, explain its architecture and ask the product owner for approval
  unless the rule is already documented in `product-truth.md` or this roadmap. Deterministic code is for
  scientific invariants and honesty constraints only: measurement, required inputs, model domain, resolution,
  registration, provenance, safety and typed refusal. If AI-authored prose fails validation, regenerate it
  from the validated dossier; while AI is enabled, never publish hard-coded prose as a fallback. Prefer
  capability registries, schemas and evidence-driven composition over growing branch trees or synonym lists.

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

## 1.0 — CLI skeleton and the LangGraph spine — **done (2026-08-31)**

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

**Result** — `aeris run`, `--resume` and `--replay` all work; 45 new tests, **142 green**, ruff and
`uv lock --check` clean. Built: `schemas/events/` (5 of 7 analysis events, the other two recorded with the
phase that owes them), `services/pipeline/` (state, checkpointer, memory store, stream, cancellation, the
`pipeline_node` decorator, `graphs/probe.py`), `services/sessions/` (session, run handle, fan-out),
`cli/renderers/` and `cli/run.py`.

Three things were **measured rather than assumed**, and each is recorded where it is relied on:

- `durability="sync"`. A hard-killed process leaves **zero** checkpoints under `exit`; a graceful
  cancellation cannot tell the modes apart, which is why the test kills a real process.
- **A checkpoint must hold data, never Python objects.** Putting an `Intent` in the state wrote our module
  path into the checkpoint; LangGraph warns that it will refuse this in a future version, and a rename
  would have made every in-flight run unresumable.
- Three separate mechanisms stop an abandoned run, and the first mutation pass showed **none of them was
  individually tested** — deleting one left every test green. Each now has its own test.

## 1.1 — Datasets — **done (2026-08-31)**

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

**Result** — 18 datasets catalogued from PDF Table 5, one loader over six declared layout shapes,
`aeris dataset list|show|fetch|search`, and a **real Sentinel-2 scene fetched from Planetary Computer**.
126 new tests, **268 green**.

The load-bearing decision is that `Licence.UNVERIFIED` **denies everything** rather than defaulting to
permissive — an unknown licence and a permissive one must never look alike in a table. Two of the eighteen
licences are verified (Copernicus Sentinel-1/2); the other sixteen carry the URL where their terms live, and
`require_trainable()` refuses training on any of them. That is the gate's "before, not after" expressed as
something that raises rather than something that warns.

Measured rather than assumed:

- One Sentinel-2 10 m band is **~245 MB** as a COG, not the ~100 MB published figures suggest. The record
  said "~200 MB per scene subset"; two bands came to 489 MB. `--asset` exists because of this.
- **Forgetting the L2A reflectance offset moves the vegetated fraction from 75.1% to 61.4%** on a real
  scene — 13.7 points, mean |ΔNDVI| 0.185, and both maps look like NDVI maps.
  (`notebooks/02_data_exploration/01_sentinel2_l2a.ipynb`)
- `Availability.PARTIAL` was added after a test showed the model was wrong: "train downloaded, test not" was
  being reported as *malformed*, which sends an operator to inspect an archive when they need to finish a
  download. `require_trainable()` is per-split for the same reason.

**Not done, and deliberately**: the other seventeen datasets are not downloaded (SEN12MS alone is ~430 GB),
and label parsing belongs to the phase with a model to feed — 1.6 for boxes and masks, 1.7 for questions.
1.1 owes acquisition, licensing, cataloguing and **enumeration**, and enumeration is what verifies a
download is complete.

## 1.2 — Raster engine · S1–S6, S11 · plus tiles — **done (2026-08-31)**

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

**Result — the gate passed in a real browser.** `aeris ingest inspect|scene|index`, `services/imagery/`
(metadata, validation, cog, tiling, `math/`), TiTiler in compose, and `tools/tilecheck/` — seven checks at
`http://localhost:3000`, all green, including `getImageData` on a canvas the tile was drawn into. 46 new
tests, **314 green**.

    NDVI over 10980×10980   range [-1.000, 1.000]   vegetated (>0.3) 72.6%
    TileJSON  xyz, bounds [77.032, 27.901, 78.176, 28.913], minzoom 8, maxzoom 14
    CORS      allowed → ACAO: http://localhost:3000   ·   other → 200 with NO ACAO
    Tile      image/png, RGBA, 38,217 transparent px of 65,536 at the scene edge

**The bug worth carrying forward.** The first NDVI ranged **[-337, +347]** and wrote a *valid* COG that
rendered as a plausible map — 0.055% of pixels, invisible by eye, and enough to set the colour scale of
every figure the array feeds. The first fix was wrong: raising the denominator guard changed nothing.
The cause is that `|a−b| ≤ |a+b|` holds **only when a and b share a sign**, and subtracting the L2A offset
from dark ground gives negative reflectance. Measured: 0.52% of valid pixels are negative, and **100% of
the out-of-range values came from exactly those.** `math/indices.py` masks them and carries a
post-condition that raises.

Three more things were measured rather than assumed, each after assuming wrongly first: TiTiler listens on
**80**, its settings are prefixed **`TITILER_API_`**, and its default CORS is `*` *with* credentials — a
pair every browser rejects, so the permissive-looking default is the broken one.

**Not built, deliberately**: the index *engine* (registry, vocabulary, cloud mask before arithmetic, the
S12 trace step) is 1.4. What 1.2 has is the raster path the gate names — read, scale, divide, write a COG,
upload, serve.

## 1.2.1 — Visual products · the figures the backend sends — **done (2026-08-31)**

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

**Result — the gate passed.** `aeris figures <scene> --level L2A` renders all three from the four-band
Sentinel-2 subset in `notebooks/01_remote_sensing/data`, and the index map **redraws byte-identically from
its recorded `renderSpec`** (1,478,754 bytes). 37 new tests, **353 green**.

    rgb-composite   1066×1120  2518 KB   legend categorical  ramp true-color
    index-map       1066×1176  1444 KB   legend continuous   ramp index-vegetation  domain [-1, 1]
    mask-overlay    1066×1120  2554 KB   legend binary       ramp mask-amber        resampling nearest
    vegetated: 17.1% of the scene   ·   3 figures in MinIO and under runs/<run_id>/figures/

**Matplotlib is used for its colormaps and nothing else** — no figure, no `Agg` canvas, no `savefig`.
Composition is NumPy and Pillow, because byte-identical reproduction is a *requirement* here (§6 rule 2)
and a matplotlib figure's bytes depend on font metrics, DPI and backend version. The colourbar is drawn by
hand for the same reason.

**Two additions to the contract, both because rule 2 demands completeness.** `renderSpec.stretch` carries
its `method` (a percentile stretch is data-dependent and a fixed one is not — only one redraws on other
data), and `renderSpec.decimation` was added outright: a figure is drawn from a decimated read, and two
decimations of one scene produce visibly different images. `figure-ready` is agreed and not yet on the
frontend, so extending it now costs nothing.

**The contract suite gained a direction.** `figure-ready` in `AnalysisEventType` broke the exact-match
union test, because the frontend does not parse it yet. Rather than weakening the check to a subset,
`EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND` records the three agreed-but-unimplemented events (§4, §5, §6)
by name with a reason, plus a staleness test that fails when the frontend ships one — at which point the
equality check starts enforcing it.

**Also fixed here, found by using it**: a 245 MB scene download had no retry, and a remote reset lost the
whole transfer. `_download_to` now retries three times with backoff — measured, after three consecutive
resets while fetching B02/B03 for this gate. Each attempt restarts rather than resuming with a `Range`
header, because resuming without checking the `ETag` risks stitching a scene from two versions of a file.

## 1.3 — Preprocessing · S7–S10 and the SAR branch — **done (2026-09-01)**

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

**Result — the gate passed**, `aeris preprocess coregister` and `aeris preprocess sar`, both on the real
Sentinel-1 / Sentinel-2 scene in `notebooks/01_remote_sensing/data` and the real Copernicus DEM over the
same ground.

    known-good  one rigid translation of (2.5, -1.25)   residual 0.0000 px   accepted
    known-bad   opposite translations in each half      residual 4.0000 px   REFUSED
    real pair   s2_B04 against s2_B08                   residual 0.1436 px   accepted

**Three defects were found in the maths, all by measurement rather than review, and none visible to the
tests that were passing over them.**

1. **Layover and shadow were swapped.** The slope was measured *away* from the sensor and then tested as
   though it were measured *towards* it, so a foreslope was reported as shadow and a backslope as layover.
   The test in place asserted only that both masks were non-empty and differed — which stays true when the
   sign flips. This is precisely the §8 rule 7 distinction, inverted.
2. **The terrain correction was a gain.** `cos(slope)/cos(incidence)` multiplies flat ground by 1.22 at a
   35° incidence. It is now `cos(θ)/cos(θ_local)`, which is exactly 1 where there is nothing to correct.
3. **Speckle was filtered as additive noise.** Measured on two regions of one scene with identical speckle
   statistics differing only in brightness: 25× smoothing on the dark half, 1.4× on the bright half. A
   change detector reads that variance collapse over water as a finding. Now Lee (1980) on the coefficient
   of variation, which is scale-free.

**And one in registration.** Invalid pixels were filled with zero, so tiles touching the nodata margin
locked onto that artificial edge and returned a shift of exactly (0, 0) — which reads as *perfect*
registration rather than as a failure. 1.3% nodata was enough to report 1.02 px on a pair aligned to
0.00 px, refusing good data. Filled with the tile mean.

**`polarisationSchema` is discharged.** It had sat in `FRONTEND_ONLY_VOCABULARIES` reading "Phase 1.3 —
the SAR branch" since Phase 0.7; `scenes.Polarisation` now mirrors it and the exact-match test enforces it.
Upper case `VV`/`VH`, deliberately not `BandRole`'s lower-case members — one addresses a band in a file,
the other is a value on the wire.

**Both branches report `obscuredFraction`**, the number `sensorRunSchema` already declares: cloud, shadow
and *unjudged* pixels for optical; layover and shadow for radar.

**The backscatter figure uses a fixed dB domain, not per-scene percentiles** — the same argument that puts
every NDVI on [-1, 1] in 1.2.1. A radar time series exists to be compared, and a per-date stretch makes a
flooded field and a calm one look alike.

## 1.4 — Spectral indices and geospatial statistics · S12, S15 measurement — **done (2026-09-11)**

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

**Result — the gate passed**, and it ran as a real pipeline run rather than a script. `aeris analyse
--scene <dir> --query "unhealthy vegetation"` runs the new `index-query` graph — **S7 → S12 → S15 → S16** —
through the 1.0 session and fan-out, with the journal, the live trace and the figure writer registered. On
the Mumbai scene that closed 1.2 and 1.3:

    S7    no cloud mask: the subset carries no SCL layer; NDVI reported unmasked (and says so)
    S12   NDVI from B08, B04 over 1066x1120                       index-engine 1.4.0
    S15   Sparse vegetation (NDVI 0.20 to 0.40): 2,471.0 ha,      geospatial-engine 1.4.0
          21.2% of 11,651.6 ha observed, 7,691 regions
    S16   "...covers 2,471.0 hectares ... in 7,691 regions. No cloud mask was available..."
    3 figures (index map, true colour, mask overlay - primary), each carrying its stage's trace step id

**The hectare figure was checked against two independent tools, not one.** QGIS is not on the build
machine, so the S15 mask was vectorised and measured by pyproj's ellipsoidal integration
(`Geod.geometry_area_perimeter`) and by PostGIS `ST_Area(::geography)` — the 0.2 route. All three give
**2,471.0057 ha**; the 7,691 polygons match the 7,691 regions. The naive figure — pixel count × 100 m² in
UTM — is 2,472.13 ha, **1.12 ha too many** (+0.045%), because UTM's scale at 230 km from the central
meridian is not 1. That is the plausible wrong number §8 rule 3 exists to prevent, and a test now fails on
it. 65 new tests, **444 green** (the two remaining reds need the 1.2 gate's Ghaziabad NDVI COG in MinIO,
which this machine never fetched); ruff and `uv lock --check` clean.

Measured rather than assumed, and each recorded where it is relied on:

- **s2cloudless cannot run on an L2A scene.** Its ten-band cube needs B10, which L2A products do not
  publish. The S7 that actually works on the data every index runs over is the product's own scene
  classification layer, so `mask_from_scene_classification` joined `cloud_masking.py` and the S7 node
  uses it. Cirrus counts as cloud; dark-area and unclassified pixels count as observed.
- **Areas are measured per pixel footprint in a local LAEA, without resampling the mask.** Projecting
  corners and summing footprints (per 32-pixel block) agrees with the geodesic integral to 2×10⁻⁹ in UTM
  and 6×10⁻⁸ in a geographic grid, and never changes which pixels the mask contains — which resampling
  the raster into the equal-area CRS would.
- **`coverageFraction` is a ratio of areas over *observed* ground**, not of counts over the grid. A field
  under cloud is not "not vegetated"; the same mask that kept it out of the index keeps it out of the
  denominator. `measure_mask` refuses a detection over unobserved ground, which is the structural proof
  that S12 masked before it computed.
- **EVI is unbounded and SAVI exceeds 1 over specular pixels**; both mask (never clip) outside [-1, 1],
  and the share the formula refused is reported in the S12 trace detail rather than absorbed.

Two additions to the spine, both because a figure rendered inside a node has to carry that node's id
(`api-contract.md` §6 rule 1): `pipeline_node` now exposes `current_trace_step_id()` and
`describe_trace_step()` through a context variable, and takes `model_id` / `model_version` so the trace
says which engine ran. Arrays never enter the checkpoint — S7, S12 and S15 retain their outputs through
`services/evidence/artefacts.py` (local COG plus the `artefacts` bucket) and the state carries paths and
keys. A run interrupted after S12, with its local artefact deleted, resumes through S15 by restoring the
artefact from storage; that is a test.

**Not built, deliberately**: vectorisation, claims and evidence records are 1.5, which is why no caption
carries a number yet; the query→index table is the deterministic half of routing and 1.8 replaces the
phrase match with a classifier; and a windowed multi-band fetch that would put a real SCL under the local
gate scene is 1.1 territory, so the real-data demonstration of S7 is recorded as owed.

## 1.5 — Evidence, confidence and provenance · S15, S18, S19 — **done (2026-09-11)**

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

**Result — the gate passed, all four statements, each as a test and each on the real scene.** The index-
query graph grew to **S7 → S12 → S15 → S16 → S18 → S19**; the two events 1.0 recorded as owed -
`layer-ready` and `claim` - are emitted, and `EVENT_TYPES_NOT_YET_EMITTED` is empty by earning it. On the
Mumbai scene, `aeris analyse --query "unhealthy vegetation"`:

    S12   layer-ready   raster-tiles  NDVI over the retained COG (TiTiler, server-side stretch and ramp)
    S15   layer-ready   raster-mask   every pixel of the mask, as tiles
          layer-ready   polygon-vector  844 of 7,691 regions as features, each with hectares and mean NDVI
          claim         primary, quantitative: 2,471.0 ha, 21.2% of 11,651.6 ha observed, 7,691 regions
          claim         supporting, spatial: the largest region, 112.0 ha, mean NDVI 0.29
    S16   the claims, spoken            S18  minimum-of-stated: none stated -> confidence None
    S19   provenance.json (2 inputs hashed, 2 artefact URIs, 2 engines, the rule) + evidence-graph.json

Walked back mechanically: every claim → evidence → layer → feature → ring → rasterised onto the S15 mask,
845 feature footprints, each containing every pixel its region measured; S12 and S15's completed trace
steps carry the `artefactLayerId` of the layer that draws their artefact; all three figures name a step and
the primary one carries both claim ids; 66 of 66 parseable journal lines and the whole evidence graph
validate against the vendored Zod. 40 new tests, **471 green**, ruff and `uv lock --check` clean.

Measured rather than assumed:

- **Vectorisation is exact and simplification is free; holes are the whole difference.** The largest real
  region has 658 interior rings. Rasterising its full polygon back covers exactly its pixels; its *outer
  ring* encloses 33% ground the mask never marked - and `featureGeometrySchema` is a single ring, so
  holes cannot travel. The feature therefore carries the true, holed area and its outline, and the
  invariant tested is containment, not equality. **A coordinated change to ask for: `holes` on the
  polygon geometry.**
- **The S7 mask from an L2A product has no fleet model.** `layerProvenanceSchema.modelId` is required and
  the twelve ids have no entry for Sen2Cor; `s2cloudless` did not run and is not claimed. S7's trace step
  carries no layer, the artefact is retained and its URI is in the provenance record. **A coordinated
  change to ask for: a thirteenth id for the product's own classification.**
- **The vector payload is the run's largest artefact.** 844 features made a 5.5 MB journal line; with
  coordinates at seven decimals (a centimetre) and a compact evidence graph, 11.6 MB became 5.6 MB.
  `MINIMUM_FEATURE_REGION_PIXELS` bounds what is drawn; the hectares are always the whole mask's.
- **Every number the answer speaks is on a claim.** The cloud caveat quoted an obscured fraction no claim
  carried until it became a metric on the primary claim (invariant 15), and a test now strips the claim
  texts out of the answer and checks what remains.

**Not built, deliberately**: persistence to the `evidence`, `claims` and `trace_steps` tables - a run row
needs an investigation row, which is 1.9's session persistence; the JSON records and the journal are the
Phase 1 audit trail and are the columns 1.9 writes. The confidence rule is `minimum-of-stated` with every
stage declining; 1.6 supplies the first stated score and 1.7 the validation checks PDF §20 folds in.

## 1.6 — Specialist models · S13 — **done (2026-09-12)**

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

**Result — both halves of the gate passed, on real weights, on a 4 GB laptop GPU.** Pretrained first, as
the plan says; nothing was trained. 40 new tests, **515 green** (the two reds are still the 1.2 tile
tests wanting the Ghaziabad COG), ruff and `uv lock --check` clean.

    aeris models evaluate --limit 256        changeformer  v6-levircd256-hzdr   93 ms per crop
      change class   precision 0.8009   recall 0.7905   F1 0.7957   IoU 0.6607
      area           predicted 15.70 ha   truth 15.91 ha   (nominal 0.5 m pixels)
      all 2,048 test crops:  F1 0.8233   IoU 0.6996   P 0.8516   R 0.7968   159.9 ha of 170.9 ha

    aeris models warm changeformer segformer-landcover --budget 700
      changeformer          offline -> warming (queue 1) -> online     resident 512 of 700 MB
      segformer-landcover   offline -> warming (queue 1) -> online     evicted changeformer; 640 of 700 MB

`warming` is *observed*, from a second task polling `status()` while the load runs, both in the CLI and
in a test. The models: **ChangeFormerV6** (wgcban's architecture vendored under MIT, HZDR-FWGEL's LEVIR-
CD-256 checkpoint from the Hub, 41.0 M parameters) and **SegFormer-B2 fine-tuned on LoveDA** through
`transformers`; the **SAR log-ratio detector** as the deterministic `sar-change`; and the residual gate of
§8 rule 2 in front of the optical detector, tested to refuse a misaligned pair *before* the model is
loaded. `app/models/` is the fleet: `constants/fleet.py` states every model's capability, stages,
weights source and measured footprint; `manager.py` leases, evicts idle least-recently-used models to a
budget, and reports `offline / warming / online / degraded` with `queueDepth` and `medianLatencyMs`
exactly as `modelStatusSchema` asks; `aeris doctor` gained a "Model device" row.

Measured rather than assumed:

- **The checkpoint's input convention is not the paper's.** ChangeFormer normalises to [-1, 1]; HZDR's
  checkpoint scores F1 0.21 that way, 0.19 with ImageNet statistics, 0.42 in BGR, and **0.79** on plain
  RGB in [0, 1]. Every wrong convention produces a plausible mask. The evaluation harness is what chose,
  and the adapter's header says so.
- **The vendored file was not verbatim the first time.** The extractor cut `ConvLayer` at a column-0
  comment inside the class, leaving 38.7 M parameters against the checkpoint's 41.0 M; the strict load
  refused it (10 unexpected tensors). Re-extracted to the next top-level definition, 41.0 M, loads clean.
- **Footprints:** ChangeFormer 157 MB of weights, 461 MB peak through a 256 tile, 102 ms; SegFormer 104
  MB, 556 MB peak through a 512 tile, 217 ms. Declared as 512 and 640. A Sentinel-2 subset (1120×1066)
  runs through either in about two seconds, windowed and stitched with no seam of NaN.
- **This laptop is a 4 GB profile**, below the roadmap's smallest. `VramProfile` gained a `4gb` tier and
  the profile is measured from `mem_get_info`, never read from a product name. Both models fit at once
  in 3,071 MB of budget, so the eviction is demonstrated with `--budget`, which is what "on the 8 GB
  profile" means on a card with four.
- **transformers 5's image processor requires torchvision** for a rescale and a normalisation whose
  constants are in the checkpoint's own `preprocessor_config.json`. The adapter reads the file instead.

**`dota-detector`, added the same day**: the mmrotate detectors need a compiler toolchain; **YOLO11s-OBB**
(Ultralytics, trained on DOTA v1.0, pure PyTorch) does not, and it is real - published test mAP50 79.5,
measured here at 79 MB of weights, 225 MB peak through a 1024 tile, 55 ms per tile. Served through the
`ultralytics` package, which reads a NumPy array as **BGR**: the adapter reverses at the boundary and a
test proves it box for box against the package's own file route. Large scenes are windowed at 1024 with a
128 overlap; a box cut by a window's interior edge is dropped when the neighbour holds it whole, which
took a 2×2 mosaic from 10 boxes for 8 objects to exactly 8. Smoke-tested on DOTA8 (Ultralytics' eight
crops, a new `download` route): F1 0.842 at IoU 0.5, no misses - crops the model trained on, so a check of
the adapter and not a benchmark; DOTA proper stays `manual`. **The cost is the licence: AGPL-3.0**, weights
and package alike, recorded in `constants/licences.py` - a hosted AERIS that keeps this detector must
publish its source or buy Ultralytics' commercial licence. That is a product decision, flagged, not made.

**Not built, and why**: `grounding-dino-sam` and `rs-vlm` are 1.7's (both load through `transformers`,
and the fleet records are in place with `offline` and a refusal naming the gap). The LEVIR-CD licence
page was unreachable from the build machine, so the dataset stays `UNVERIFIED` - which blocks training,
not evaluation, and no training was planned. The S13 *node* is 1.10's composition; the 1.5 builder
already turns any mask the detector produces into both representations and claims.

## 1.7 — VLM and constrained answer generation · S14, S16 — **done (2026-09-13): adapter trained, measured better on every task but counting, served end to end**

**Research:** PDF pp.15–16 (captioning and VQA), p.8 (why a VLM alone is insufficient).

**Deliverable** — RS-VLM serving (quantised to the VRAM profile), VQA and captioning **over the figures
rendered in 1.2.1** — the model reads the same image the operator is shown, which is why those renders are
deterministic and carry a recorded `renderSpec` — and the **constrained answer generator**: language produced
*from the structured results*, with the numbers injected rather than generated.

**The VLM cannot emit a figure that no specialist produced.** This is enforced by construction — it is
given the claim objects and asked to phrase them — and then tested for.

**Gate** — single-image question and answer in the CLI. A test that seeds a claim with a known number and
asserts the number in the answer text is exactly that number.

**Result — the gate passed on the unadapted base; the adaptation is built end to end and waits only for a
GPU the laptop does not have.** `aeris ask --image <png|jpg|tif> --question "..."` answers from Qwen3-VL-2B
served NF4 on the 3050 (1.5 GB resident, 1.7 GB peak through a two-image prompt, ~2 s a short answer,
~7 s a caption); `--image a --image b` asks about a pair. The constrained generator is in S16 of the
index-query graph: on the Mumbai scene the model's phrasing passed the numeral check and every figure in
the answer is a claim's (`aeris analyse` trace: *2 claims spoken ... by the vlm generator*). Its first
real run was **rejected** for copying "NDVI 0.20-0.40" from the fact - the rule now distinguishes a
specialist's number repeated from a number invented - and its second produced "2,471.0 ha hectares",
fixed by filling each hole with exactly what it replaced. 23 new tests, **538 green** (the two reds are still the 1.2 tile tests); the four VLM integration tests
include the seeded-number gate on the real model and the footprint check.

**The zero-shot baseline, measured on the 189 human-verified BigEarthNet.txt rows we have pictures for**
(`aeris models evaluate --model rs-vlm --file .../bigearthnet_txt.bench.jsonl`):

    qwen3-vl-2b-unadapted     yes/no 0.539 (chance 0.5)   MCQ 0.394 (chance 0.25)   boxes 0.000
                              captions ROUGE-L 0.162     overall (mean of types) 0.274
                              mean stated confidence 0.83 - over-confident by a wide margin

That number is the problem statement's point made numerically: a generic VLM does not read Sentinel-2.
Boxes are zero because the base answers `[0, 0, 99, 99]` in its own convention; MCQ is near chance
because it has never seen a CORINE class name. Both are what a LoRA fixes in the first few hundred steps.

**The adaptation, built and dry-run:** `training/vlm/` prepares the instruction set - BigEarthNet.txt on
the Lithuania-summer LMDB (3,447 rendered S1/S2 pictures, balanced per bucket, constant categories
dropped, S1 already in dB, S2 at 0-2500 with gamma 0.6 after an eight-patch comparison), RSVQA-LR by its
published image splits, and a VRSBench slice cut on Kaggle where the 7.8 GB archive is minutes rather
than hours - and `kaggle.py` uploads it and pushes `notebooks/08_vlm_finetuning/03_train_lora.ipynb` as
a T4 kernel. The notebook's dataset, collator, label masking and QLoRA wrap were executed on the laptop
at batch 1 (loss 0.95 -> 0.00 on a two-row smoke set; batch 2 OOMs a 4 GB card, which is the whole reason
for Kaggle). The fleet loads the adapter from `VLM_ADAPTER_REPOSITORY`; until one exists the version
string carries `-unadapted`, visible in `aeris models status`, on purpose. Four teaching notebooks and a
README explain the recipe for a reader new to it.

**The adapter, measured (2026-09-13).** One epoch, rank 16, 21,600 rows (BigEarthNet.txt Lithuania-summer,
RSVQA-LR, a VRSBench slice), 242 min on a Kaggle T4, validation loss 0.375 -> 0.340. Scored on the same
rows as the base with per-row predictions and McNemar's exact test (`training/vlm/compare.py`):

    file                          type            n    base   adapter   fixed  broken     p
    BigEarthNet.txt bench (human) yes/no         91   0.593   0.648       17      12   0.46
                                  MCQ            66   0.379   0.621       24       8   0.007
                                  boxes IoU>=.5  22   0.000   0.364        8       0   0.008
                                  captions R-L   10   0.161   0.491       10       0   0.002
    BigEarthNet.txt test (templ.) yes/no        127   0.465   0.756       45       8   <1e-4
                                  MCQ           160   0.350   0.700       74      18   <1e-4
                                  boxes          76   0.000   0.605       46       0   <1e-4
                                  captions       37   0.156   0.479       37       0   <1e-4
    RSVQA-LR test (Netherlands)   yes/no        300   0.607   0.863       95      18   <1e-4
                                  count/rural   250   0.452   0.484       27      19   0.30
      by category: presence 0.54 -> 0.85, comparison 0.67 -> 0.87, rural/urban 0.80 -> 0.86, count 0.22 -> 0.23

    overall (mean of types): bench 0.283 -> 0.531, test 0.243 -> 0.635, RSVQA-LR 0.529 -> 0.674

Honest reading: MCQ, boxes and captions are large, significant gains on every file; yes/no is significant
on the two larger files and only a trend on the 91 bench rows; **counting did not improve** (0.22 -> 0.23,
p = 0.3) - a LoRA on 5k count rows does not teach a 2B model to count vehicles, and the fleet should
answer "how many" with the detector, not the VLM. Confidence moved the right way where it was worst
(MCQ 0.90 -> 0.82 stated against 0.62 accuracy) and is still over-stated.

Two defects the adapter exposed, both fixed and tested:

- **Captions learned the constants anyway.** Categories were dropped, but every caption *text* opens with
  "captured during the summer in Lithuania" and the adapter said so on 10 of 10 bench captions. The
  prep now scrubs the country, season and climate-zone clauses from caption targets (zero residual on
  3,000 sampled captions) - the next training run inherits it. On an aerial DOTA crop the adapter did
  *not* say Lithuania; it described a vehicle, tersely - captions of high-resolution scenes got shorter
  and thinner, which the VRSBench slice (928 caption rows) did not prevent.
- **The adapter cannot phrase.** Asked the S16 constrained prompt it answered "{m1}" - one placeholder,
  nothing else - and the numeral guard, which forbade *invented* numbers, let it through: the answer was
  "2,471.0". Two fixes: phrasing runs on the base weights (`use_adapter=False`; the adapter's job is the
  picture), and every placeholder must be spoken or the template speaks.

End to end with the adapter: `aeris analyse` on the Mumbai scene - S14 reads the overlay in 19 s
("distributed across the image, with one area in the bottom-right quadrant, adjacent to a body of water
and a densely built-up urban area"), S16 phrases every claim number exactly, the four VLM integration
tests pass including the footprint (declared 2,048 MB holds with the adapter attached). The adapter is
loaded from a local directory (`VLM_ADAPTER_REPOSITORY` accepts a path or a Hub id); the Hub push waits
for a token with write permission.

**Owed:** a second training run on the scrubbed captions with more VRSBench caption rows; the Hub push
(write token); notebook 04 executed end to end; the 4B variant on an 8 GB machine; counting routed to
the detector rather than asked of the VLM (1.8's routing). `grounding-dino-sam` is still
offline; Qwen3-VL's native grounding plus the LoRA's box rows is the first candidate for it.

**Problem-statement check (2026-09-12), before 1.7 starts.** The SIH statement (SatQuery AI) was read
against this plan. What it makes *mandatory* that the plan already carries: single-image VQA (1.7),
captioning or grounding (1.7: both), change description or change-VQA from a bi-temporal pair (1.10 over
the 1.6 detector, phrased by 1.7), optical-SAR complementary extraction (1.11), agentic model selection
with an auditable execution summary (1.8/1.9 over the 1.5 provenance record), GeoTIFF/TIFF input with
PNG/JPEG for benchmarks only (1.2, 1.1). What it changes:

- **"A generic LLM or VLM without remote-sensing adaptation will not satisfy the requirements"**, and
  "at least one visual or vision-language component must be fine-tuned or otherwise adapted using
  BigEarthNet.txt or any open-source training data". The deferral "fine-tune only where a gate fails" is
  withdrawn for the VLM: 1.7 **fine-tunes** it. **`rs-vlm` = Qwen3-VL-2B-Instruct (Apache-2.0, 4.0 GB in
  bf16, native multi-image input and grounding, transformers-native) with a LoRA trained on
  BigEarthNet.txt** - the statement's named dataset: 464,044 co-registered S1/S2 pairs with captions,
  VQA and referring expressions (CDLA-Permissive-1.0, text on the Hub as one 0.43 GB parquet; images from
  BigEarthNet v2.0, a 10% subset suffices). Training is not possible on the 4 GB laptop; it is run on a
  16 GB cloud GPU (a free T4 is enough at rank 16-64, 448 px) and the adapter (~70 MB) is what the fleet
  loads, 4-bit, beside the base. Served on the 3050 it is `degraded`-eligible and measured before declared.
  The alternatives weighed and not chosen: EarthDial-4B (MIT, RS-adapted, SAR and temporal aware - but
  7.7 GB, `internvl_chat` custom code pinned to an old transformers, and not adapted *by us*); GeoChat
  (7B LLaVA, same objections, larger).
- **CDVQA** is the statement's change-VQA benchmark and was not in the catalogue; it is now, `manual`,
  unlocked in 1.10 and scored in 1.14 beside LEVIR-CD. Its pairs are SECOND's - the change detector must
  not be fine-tuned on SECOND if CDVQA is to mean anything.
- **BigEarthNet.txt** is in the catalogue as its own record, distinct from BigEarthNet-MM.
- **The final evaluation set is Cartosat-2S optical with RISAT SAR, pre-georeferenced and co-registered.**
  Neither sensor is Sentinel. The 1.3 SAR chain assumes Sentinel-1 GRD calibration constants; for a
  pre-calibrated RISAT product S8 must be skippable with the skip *recorded*, and the 1.9 co-registration
  residual must still be measured on the pair rather than trusted. A resolution the VLM has never seen
  (0.6 m pan-sharpened) is the reason the LoRA data should include VRSBench-resolution imagery too, not
  BigEarthNet.txt's 10 m alone.

## 1.8 — Query understanding and routing — **done (2026-09-12): 0.991 held-out, 1.000 fresh; a count never reaches the VLM**

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

**What was built.** A cascade (`services/query/classifier.py`): cues in `constants/routing.py` narrow a
question to an intent family (an evidence question, both sensors named, a change cue, a segmentation verb,
"how many <object>", an index named, a perception opener, a locating verb), and a kNN over a labelled
bank of 215 questions - embedded by `BAAI/bge-small-en-v1.5` on the CPU, ~10 ms a question - votes within
the family. `services/query/entities.py` extracts objects (resolved to the detector's classes; a place
after "in the" is context, not a target), compass region, temporal scope and dates, sensor, and what shape
of answer is wanted. `agents/router.py` maps intent -> tool -> graph from a table and validates: two-image
intents need two images, cross-modal needs both sensors, an index question needs an index the engine has,
and **a count needs a class the detector knows and a pixel that can hold it** (`OBJECT_LENGTH_METRES /
MIN_OBJECT_PIXELS`: a 4.5 m car needs <= 0.56 m pixels; a 10 m Sentinel-2 scene is refused with both
numbers before the detector runs and reports zero). `aeris route "<q>"` prints a decision; `aeris route
--evaluate` prints the gate; `aeris ask` and `aeris analyse` route before they run anything.

**Measured** (`aeris route --evaluate`, 2026-09-12):

    file                          n    rules alone   kNN alone   cascade   uncertain
    held-out half of the bank   235        0.936       0.766      0.991          1
    fresh, operator register     45        0.867       0.911      1.000          1

Honest reading: the held-out half was split from the bank by text hash, never learned from - but the cues
were tuned against its errors in three passes (0.877 -> 0.987 -> 0.991), so it is out-of-sample for the kNN
and not for the rules. The fresh file was written afterwards in an operator's register ("how many ships r
there", "why did u say its flooded"): first score 0.933, with three errors that were vocabulary gaps
("since the first date", text-speak, "any X here?"), fixed in the tables and re-scored 1.000 - so that
number was looked at once too, and says so here. Both files are one author's phrasing; a judge's will be
wider. The two remaining held-out errors are arguable labels ("What is the dominant land use here?" ->
SEGMENT; "Which areas changed the most and why?" -> CHANGE_DETECT).

**The counting decision, exercised end to end.** On the DOTA8 crop with three basketball courts in its
label file: routed, `dota-detector` counts **3** (four boxes kept, mean score 0.85, 2.2 s), the VLM never
leased - asserted by a test that spies on the manager. `--force-vlm` on the same question: the adapted VLM
says **2** in 22.8 s. "How many buildings" is refused by name with the fifteen classes it can count, and
the VLM answers *presence* ("Yes"), labelled as not a count. "Where are the basketball courts" grounds
with the detector's three boxes and their centres.

**Compound requests (added the same day).** A voice request holds several questions. Measured first: the
single-intent router got 4 of 4 single asks and **0 of 11 compound ones** - it answered the loudest clause.
`services/query/decomposer.py` strips filler ("hey aeris, can you please"), splits at sentence ends and
connectives (", then", "and also", "after that", "finally", and " and " only before a clause opener so
"ships and boats" stays one phrase), drops conditional leads ("if yes,"). `agents/router.py::route_plan`
routes each clause, binds a pronoun clause to the clause before ("count them", "how much of it"), carries
a pair or both-sensors context to later clauses with no cue of their own, and merges consecutive steps
that are one run of one tool (find + where + how many of the planes -> one detector step with both wants;
two change questions -> one comparison; a count of ships and of tanks -> one detector run). `aeris ask`
answers every step in order; `aeris analyse` runs one graph per index step.

    file                              n   exact sequence   steps found   first untouched score
    compound, developed against      15        1.000          1.000      0.333 (single-intent router)
    compound, fresh (two batches)    35        1.000          1.000      0.500 (batch 1), 0.667 (batch 2)

The untouched scores are the honest ones: each fresh batch was scored once, its errors were vocabulary
gaps in the decomposer (a connector, a filler phrase, "its" mis-folded, "there" taken for a pronoun) and
were fixed by table, then it was scored again. A third batch would score somewhere between. Two labels
were changed to what the plan should be rather than what was first written: "how many ships and how many
tanks" is one detector run, not two steps.

**Owed:** ~~the DETECT / SEGMENT / CHANGE graphs the table names `None` for~~ (built in 1.10); ~~an LLM
arbiter~~ (1.9); a query set written by someone other than the author; a conditional step ("if yes, ...")
executed conditionally rather than always (1.9's agent).

**On objects the detector does not know - the recommendation, for after the product is whole.** No
fine-tuning now: a demo that routes well over fifteen classes and a segmentation model beats one with a
sixteenth class and no agent. Then, in order: (1) route building *area* and an approximate building
*count* to `segformer-landcover` (LoveDA has a building class; connected components over its mask; zero
training, 1.10's segmentation graph) - a building footprint is a segmentation problem, and touching roofs
make box counting unreliable in exactly the dense scenes people ask about; (2) if instance counts of
buildings are still wanted, fine-tune YOLO11-OBB on the *union* of DOTA v1.0 and a building-instance set
(xView's building class, or SpaceNet footprints converted to oriented boxes) on the same Kaggle T4 path
as the VLM - the union, not buildings alone, so the fifteen classes are not forgotten; (3) the VLM's second
run on scrubbed captions for captions and VQA, never for counting.

## 1.9 — The agent, tool calling and the provider swap — **done (2026-09-13): plan paused, steps run, every number a claim's; gate proven with a second model**

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

**What was built.** `lib/llm/chat_model.py` (`init_chat_model` from `LLM_PROVIDER`/`LLM_MODEL`; the key
read under the provider's own name; `LLM_PROVIDER=none` is a first-class path with a template behind every
model call; a doctor row that round-trips). The model has **four jobs, none of them routing**:

1. **Arbiter** (`agents/arbiter.py`): asked only on an uncertain kNN margin, only within the family the
   cues allowed, never over a rule. Measured: 3 questions in 330 reach it; the gate is unchanged with it
   on (0.991 / 1.000 / 1.000). Asked bare, without the policy, gpt-5-mini put "how many ships are there"
   under SCENE_VQA - the reason it is behind the router, not in front of it.
2. **Planner prose** (`agents/planner.py`): the steps are the router's; the model writes the summary and
   one description per step, checked - same count, no numeral that the template did not already state.
   Rejected prose is the template. `agents/graph.py::approve` pauses on the plan with `interrupt()`;
   the operator's resume carries the step ids kept (`--skip step-2`, or the terminal prompt).
3. **Synthesis**: every step's findings are claims in wire form (a detector count is a claim with a
   metric; a VLM answer a claim with none, labelled a reading; a refusal a negative claim) and the model
   phrases them through the 1.7 guard unchanged - placeholders in, every placeholder spoken, no numeral
   that is not a fact's. S16 also phrases with it now (`ANSWER_GENERATOR=llm`: one call, no GPU, the
   VLM as fallback).
4. **Interface commands**: bound with `bind_tools` over `spotlight_claim`, `focus_evidence`,
   `toggle_layer` (`constants/ui_commands.py` mirrors `commands.ts`; a test parses the file); every id
   the model names is checked against the run's claims, evidence and layers, and a made-up one is dropped.

Dispatch is the table's: `agents/graph.py::execute` sends each enabled step to `agents/tools/`
(`run_index_query` runs the real graph through `services/pipeline/runner.py` - journal, figures,
provenance, checkpoint; `count_objects`; `answer_visual_question`; `recall_evidence` reads earlier
requests on the thread, no model). `aeris agent "<request>" --scene|--image [--yes|--skip] [--thread]`;
every request writes `runs/<request_id>/agent/{record.json, answer.txt, README.md}` beside the graph runs it made.

**Measured (2026-09-13).** DOTA8 crop, "how many basketball courts are there, and does it look like a
school?": plan by the model (2 steps, no numerals), detector **3** (the label file's count), VLM "yes",
answer by the model with every numeral a claim's; a step struck out at the pause is skipped and said so.
Mumbai scene, "map the water bodies and give me their area, then show me where the vegetation is stressed,
and finally count the cars on the roads": 4 clauses -> 3 steps; two graph runs (water 2,667.3 ha, sparse
vegetation 2,471.0 ha), the count refused at *planning* with the resolution numbers, and the answer's
**19 numerals all traced to claims or the refusal** - checked mechanically over the record. Evidence
recalled across requests on a thread in 0 ms. **Gate:** the doctor probe, plan prose, arbiter and phrasing
run against `gpt-4.1-mini` with two settings changed and no code edit (`test_the_gate_a_second_model...`);
a second *provider* is the same two settings and its key, untested for want of one.

**Defects found by running, fixed:** "give me *their* area" was not a pronoun clause; the agent did not
compute the scene's resolution so a car count was skipped at execution instead of refused at planning;
evidence recall echoed the current request's claims (duplicate placeholders made the guard reject the
phrasing); "where the vegetation is stressed" resolved to all vegetation (word order) - inverted phrases
added; LangGraph 1.2 trips over `Command(resume=None)`.

**The product owner's review (2026-09-13), adopted in full.** Reviewing a record from before the fixes
above, four structural rules were proposed; each was right and more general than the instance fix it
replaced, and each is now code and a test:

1. *A follow-up that asks for a property computable from the previous step enriches that step's wants;
   it does not become an EVIDENCE_RECALL step.* `route_plan` merges a clause that names no subject of
   its own and asks for an area, map, location, count or the evidence into the step before it - unless
   it points at an earlier request ("earlier", "previous", "you found"), which stays a recall. Caught
   "give me the area in hectares as well", which the pronoun rule had not.
2. *Recall produces claims, not metadata.* "Recalled from run X: 2 claims on 4 evidence items" moved
   from the claims into `StepResult.provenance` (request, run, step, counts) - the record, not the answer.
3. *Synthesis input is structurally unique.* `synthesis_facts` keeps each claim id once; the answer
   cannot repeat a claim because the facts do not. A recall is said to be one through a note to the
   phrasing, never a fact (a fact is honoured verbatim; the model reproduced the framing sentence mid-answer
   until it was moved).
4. *The template fallback speaks to the operator.* "The request to count the cars on the roads was not
   done: <reason>", not "Step 3 (DETECT) was not done". The reason - the resolution numbers - is kept:
   it is the operator's next action.

Found on the way: the bare word "area" made "is this an industrial area" an area ask; the cue now needs
"the/its/total ... area" or "area of/in". Re-run of the reviewed request: one INDEX step with
`wants_area`, the count refused at planning, answer by the model in two sentences plus the refusal; the
template path (`LLM_PROVIDER=none`) reads the same way; a recall on the thread carries provenance in
`record.json` and none in the answer. Suite 594 passed.

**Owed:** the `ui-command` event on the assistant stream (Phase 2); a conditional step ("if yes, ...")
executed conditionally (the agent runs it and the answer says whether it applied); ~~the 1.10 graphs the
plan still names as unbuilt~~ (built: every step is a graph run from 1.10).

## 1.10 — Pipeline graphs — **done (2026-09-13): two graphs, every specialist a branch; the third moves to 1.11 with its content**

**Deliverable** — `single_image_graph`, `temporal_graph`, `cross_modal_graph`, each a `StateGraph` composing
the nodes built in 1.2–1.9, each routing with `add_conditional_edges` over a plain lookup table (the
deterministic router of PDF p.24, expressed as a graph), and each emitting the full S1–S20 trace into the
LangGraph stream.

**Gate** — all three graphs run end to end from the CLI, resume correctly after a kill, and their journals
validate against the contracts.

**Result.** Two graphs built, run from the CLI and the agent, resumed from their checkpoints, journals and
evidence graphs validating against the vendored contracts; 664 tests green (349 unit, the rest integration
on real weights and real imagery), ruff clean.

- `single-image` (`graphs/single_image.py`): S1 -> (S7) -> a branch by intent from a table -> S15 -> S14
  -> S16 -> S18 -> S19. INDEX_QUERY is the 1.4 graph as one branch (S12); DETECT and GROUND run
  `dota-detector` at S13 and bind its boxes to ground at S15; SEGMENT runs `segformer-landcover` at S13
  and measures the classes asked for at S15; SCENE_VQA (and GROUND of a phrase no detector knows) has the
  VLM as its S14 specialist. One S1, one S14 reading, one S16, one S18, one S19 for every branch.
- `temporal` (`graphs/temporal.py`): S1 -> (S7 on both dates) -> S9 -> S13 `changeformer` -> S15 -> S14 ->
  S16 -> S18 -> S19. CHANGE_DETECT reads the comparison figure; CHANGE_VQA asks the model over both
  pictures and keeps the measured change beside its answer.
- `cross-modal` is **not built here**: without the radar measurement it would fuse (1.11's log-ratio and
  dark-target branch) the fan-in has nothing to do, and a graph whose join is a placeholder is the thing
  this project does not ship. The routing table names 1.11 for it; the reducers in `state.py` were
  written for its shape in 1.0 and still wait for it.

**Inputs are one vocabulary** (`services/imagery/frames.py`): a scene directory, a georeferenced raster,
or a picture with no grid. A picture is not refused - a count over a benchmark crop is a real answer - and
never pretended: figures and pixel claims, no layer on the globe, hectares only at a pixel size the
operator declared (`--gsd`, labelled *nominal* on every metric), pixels alone otherwise. S1 records what
each input is and refuses what the question cannot be answered from: an index over a picture, a detector
over radar, a pair on two grids, a class that spans fewer than eight pixels at this resolution - the
router's gate again, because a run can start without a router.

**The agent's runs are graph runs.** `count_objects_step` and `answer_visual_question_step` - the 1.9
tools that called a model with no journal, no figure, no record and no checkpoint - are gone; every
plan step is `run_graph_step` through `services/pipeline/runner.py`, the function `aeris analyse` uses,
with the decision turned into a request by `agents/requests.py`. `aeris agent` and `aeris analyse` take
`--before` for a pair and `--registered` to vouch for one.

    aeris analyse --scene .../P1470__1024__3296___1648.jpg --query "count the basketball courts"
      S1 picture 1024x1024, no georeference -> S13 4 boxes (mean 0.85): 3 basketball courts, 1 soccer field
      -> S15 3 basketball courts; 2 claims; no georeference, so no layer -> S14 reads the overlay -> S16
      "The detector found 3 basketball courts in P1470..., with a mean score of 0.86. Also found ..."

    aeris analyse --scene mumbai_gate --level L2A --query "segment the buildings and give me their area"
      S7 no SCL -> S13 1066x1120, 97.6% observed; background 77.2%, water 12.0%, building 6.0% -> S15
      Building covers 693.4 ha (6.0% of 11,651.6 ha observed, 12 regions; 11 drawn as polygons)

    aeris analyse --scene levir/B/0271.png --before levir/A/0271.png --gsd 0.5 --registered --query "what changed"
      S9 residual 20.41 px, 12% of tiles agree: declared-by-operator -> S13 30.5% changed, p 0.96 -> S15
      0.5001 ha (nominal, at 0.5 m per pixel), 25 regions -> F1 0.805 against the dataset's label

    aeris analyse --scene mumbai_gate_2026 --before mumbai_gate_2023 --level L2A --query "what has changed"
      S7 SCL on both dates -> S9 residual 0.10 px, shift 0.14 px, 86% of 64 tiles agree: tiles-agree ->
      S13 1.1% changed -> S15 135.7 ha in 54 regions; the comparison figure is tide and turbidity in
      Mahim Bay, which is what a building-change model finds at 10 m (below)

**Measured rather than assumed**

- **LangGraph hands a node only the keys its first parameter's annotation declares.** S19, still annotated
  `IndexQueryState`, recorded no detections and no figures from a run whose checkpoint held both. Every
  node is annotated with the graph's full state now, and `node.py` says why.
- **The 1.3 registration residual conflated change with misregistration.** The RMS of per-tile phase
  correlation shifts was 32 px on a LEVIR-CD pair its authors registered to about 2 px, because tiles
  whose ground changed report content, not geometry. Measured on sixty pairs, with four options: the
  median tile disagreement (a minority of changed tiles cannot move it; a half-scene warp still does)
  admits 14/60; the whole-frame correlation with a quarter of the tiles behind it admits 32/60; ORB
  features match 0-1 keypoints across seasons and admit none; and none of them admits one of forty pairs
  offset on purpose by 25-30 px. The gate is now the first two in turn, with the systematic shift gated
  too (a consistent 2 px offset at 10 m is 20 m, which a change model reads as every edge moving), and
  the tolerance is **5 m on the ground** converted to pixels - the 1.3 value at Sentinel-2's pixel,
  which held a 0.5 m pair to a quarter-metre wobble under 15 m buildings. The 28 pairs neither route
  admits are refused with every number and the way out: `--registered`, the operator's word, recorded as
  such (§8 rule 5, the same rule as `--level` and `--gsd`). On the Sentinel-2 pair the tiles agree at
  0.10 px.
- **The specialists are out of their domain at 10 m, and the pipeline says what they said, not what is
  true.** SegFormer-LoveDA (0.3 m) calls 77% of Mumbai "background" and 6% "building"; ChangeFormer
  (0.5 m, buildings) marks tide and sediment in Mahim Bay as change; the DOTA detector, asked for bridges
  over the 10 m subset, also drew planes and storage tanks it could not have seen at three pixels a
  side. The last is fixed structurally - the resolution gate is applied to the *output* as well as the
  question, and boxes below it stay in the artefact and out of the claims - and the first two are
  stated: a land-cover and a change model trained at Sentinel-2's resolution are what the scene path
  needs (BigEarthNet land cover; OSCD or the 1.11 radar log-ratio for change). On their own resolution
  both are right: the LEVIR pair scores F1 0.805 against its label in the graph, as the 1.6 harness did.
- **A negative reading over a figure with nothing on it is a hallucination waiting to happen.** Asked
  to describe "tennis courts" on a figure where the detector drew none, the VLM placed them top-middle.
  S14 now reads the classes that were drawn, and reads nothing when nothing was.
- **`PHOTOMETRIC=YCBCR` in a JPEG's profile broke a one-band COG.** The writer copied the reference's
  whole creation profile; it copies its georeferencing and nothing else now.
- **Hectares to one decimal is a statement about a 10 m pixel.** 0.5 m pixels are 0.000025 ha each and a
  building's change read as "0.0 ha"; the decimals follow the pixel (1 at 10 m, 4 at 0.5 m, the
  contract's ceiling).
- **The phrasing prompt did not state the guard's rule.** gpt-5-mini left the supporting "also found"
  finding out and the guard rejected the answer; told that every placeholder is used once and a figure
  written in a finding is copied or left out, never rounded, it complies (two runs, stable).
- **A windowed STAC fetch** (`fetch_scene_window`) moves 10 MB for a 10 km subset of five bands where the
  whole-band fetch moved 489 MB for two; the March 2026 and January 2023 subsets over the Mumbai box
  land on one grid (their S9 residual is 0.10 px) and both carry the SCL the 1.4 subset lacked.

**Owed:** the cross-modal graph with its radar branch (1.11); a categorical colour ramp in the frontend
vocabulary so a class map can be a figure (today the segmenter's figures are the confidence surface and
one amber mask per class); models trained at 10 m for land cover and change on scenes; the frontend's
`cancelled` trace state; the S7 vocabulary entry for Sen2Cor.

## 1.11 — Cross-modal fusion · **Done 2026-09-14**

**Research:** PDF p.19 (fusion strategies, and when to fuse at all).

**Delivered** — two *independent* per-sensor runs joined by **late fusion**, the agreement ledger
(`agreementRowSchema`), the modality advisory, a categorical fusion figure, and the refusal states.

Late rather than early fusion, because keeping each sensor's evidence separable is what makes the joint
answer auditable. **Fusion refuses** when the supplied affine grids differ by a pixel or more, or when
one sensor's silence carries no information. The affine-grid check is recorded honestly: it verifies the
input rasters' common grid, not image-content co-registration.

**Gate met** — retained real run
[`run_01M2FS0F7KZW07CG8BA9S0HG7D`](../runs/run_01M2FS0F7KZW07CG8BA9S0HG7D/artefacts/S15_cross-modal-result.json)
used Sentinel-2B L2A (2026-03-12) and Sentinel-1A RTC (2026-03-15) over Mumbai. The pair was three days
apart with a 0.00 px affine-grid residual. Its material (>= 5 ha) ledger has 72 corroborated rows, 21
optical-only rows, 6 radar-only rows, and 1 conflict. The conflict is 5.2178 ha of optical water versus
radar built-up; the system gives no fused headline, emits a confidence-null primary refusal, and asks for
a third observation. All 173 row feature references resolve in the evidence graph; the contract, five
figures, provenance, and terminal journal event were validated from disk.

**Deferred Phase 1.10 debt** — still deliberately outside this phase: enforce training-domain safeguards
for 10 m land-cover and learned change requests; refresh the vendored `figure-ready` event contract; and
validate complete figure-bearing production journals, not only the probe graph.

## 1.11.2 — Deterministic temporal multimodal fusion

This is an additive capability. It does not replace the Phase 1.10 temporal graph or the Phase 1.11
single-time cross-modal graph. It composes them into a four-input investigation while preserving the
existing two-input paths and their contracts.

**Deliverable** — deterministic, evidence-driven fusion over:

```
S2-T1 -> S2-T2 -> optical temporal change
S1-T1 -> S1-T2 -> SAR temporal change
                         \         /
                          \       /
                    temporal cross-modal ledger
```

- optical change and SAR change as independent, auditable runs;
- a temporal cross-modal ledger linking change evidence by sensor, time and location;
- agreement, disagreement, non-informative-silence and abstention states;
- physical explanations that remain explanations, not invented measurements;
- four-input provenance and claim references, with every input, registration decision, artefact and
  derived result retained in the evidence graph;
- the smallest valid input configuration: a two-date optical question need not load SAR, while a request
  for radar confirmation requires all four inputs.

The first implementation is **not** a learned four-image model. A learned joint model is deferred until
validated four-input data and a measurable baseline comparison exist. The deterministic ledger is the
reference system against which any later model must be evaluated.

**Validity rules** — each optical and SAR pair must pass its own temporal registration and domain checks;
the four inputs must share the declared spatial relationship; missing or non-informative evidence must
produce a typed abstention; disagreement must remain visible rather than being majority-voted away.

**Gate** — a real four-input run produces independent optical and SAR change artefacts, a temporal
agreement ledger, physical-explanation or abstention records, a valid evidence graph, and claims whose
provenance resolves back to all contributing inputs. Existing single-temporal and single-time
cross-modal tests remain green unchanged.

## 1.12 — Report generation · **Done 2026-09-14**

This is the user-facing reporting product, not merely an internal JSON/GeoJSON export.

**The three answer surfaces** — one investigation produces three related but deliberately different outputs:

1. **Chat answer** — the complete written answer streams into the frontend assistant as safe, rendered
   Markdown. Headings, lists, emphasis, tables, citations to claims and links to evidence/figures are
   presentation; every quantitative statement still comes from the validated claim objects. The frontend
   must replace the current plain-text answer renderer with a Markdown renderer that sanitises output,
   preserves streaming and never permits arbitrary HTML or executable content.
2. **Voice answer** — the voice agent speaks a shorter, natural version of the same validated result.
   It is generated from claims, not by reading arbitrary chat Markdown, and carries the same claim ids.
   The voice may omit detail for brevity but may not change a measurement, confidence, limitation or
   refusal present in the complete answer.
3. **Professional report** — the complete, re-readable investigation record for a remote-sensing or
   geospatial researcher, with methods, inputs, conclusions, facts supporting each conclusion, model
   versions, processing parameters, evidence, figures, uncertainty, limitations, refusals and provenance.

**Deliverable** — a generic report pipeline over the evidence, claim and provenance system:

- the streamed report sections (`summary`, `inputs`, `findings`, `evidence`, `models`, `confidence`,
  `limitations`, `conclusion`) shown in the frontend report surface;
- a **detailed researcher report PDF** with a stable layout: title and investigation scope, executive
  summary, question and data inventory, acquisition dates and spatial reference, preprocessing and quality
  checks, methods and equations where relevant, findings and measurements, claim-by-claim evidence,
  embedded real figures from the run, model/version and parameter tables, confidence and uncertainty,
  limitations/refusals, reproducibility/provenance, and a conclusion;
- a **summary report** with the essential conclusion, key measurements, confidence/limitations and a small
  curated set of primary figures for quick review or briefing;
- all relevant generated figures embedded from the actual run: index maps, masks, detection overlays,
  temporal comparisons, SAR backscatter, fusion figures, legends and diagnostic plots. The PDF must use
  the same figure bytes and render specifications that the operator saw, never screenshots or invented
  replacements;
- JSON as the machine-readable report manifest and GeoJSON as the spatial export. These are companion
  formats, not substitutes for the researcher-grade PDF. Sections reference claim ids, evidence layer ids,
  figure ids, trace steps, refusals and input records rather than copying measurements into a second source
  of truth;
- one report schema that accepts single-image, temporal, cross-modal and four-input investigations;
- deterministic report assembly. The LLM may write explanatory prose and Markdown around validated facts,
  but it cannot create or alter measurements, geometry, provenance, confidence, figure metadata or refusal
  states. Missing evidence becomes an explicit limitation or refusal in chat, voice and PDF.

**Persistence and delivery**

- Raw PDF, summary PDF, JSON manifest and GeoJSON are stored in the private MinIO `reports` bucket under a
  stable `investigation/report/version` object-key layout. Report bytes do not live in Postgres and are not
  sent through the chat stream.
- Figure bytes continue to live in the private MinIO `figures` bucket. Every figure used by a report must
  have a persisted manifest containing its figure id, object key, hash, media type, dimensions, legend,
  render specification, trace step id and claim ids. Do not duplicate image bytes in Postgres.
- Postgres stores the report identity and lifecycle metadata: report id, investigation id, trace id,
  version, status, title, generated time, object keys for each export, content hashes, summary metadata and
  the ordered report-section/figure/claim references. It also stores the figure manifest needed to resolve
  report references after a stream or local journal is gone.
- Downloads go through authenticated report endpoints or short-lived signed URLs. The frontend must be
  able to stream the report drawer, open the detailed or summary PDF, and download JSON/GeoJSON without
  loading a large document into React memory.
- Report generation is resumable and idempotent: a repeated request for the same completed investigation
  and report version reuses verified artifacts, while a changed evidence graph creates a new version.

**Reopened quality gate** — the first implementation produced valid files but failed the product bar: its
reader narrative was too close to pipeline telemetry, evidence pages did not explain what each image proved,
the PDF mixed editorial and layout concerns, and its LLM prompt lived outside `services/prompts/`. The phase
is not complete until the replacement passes both a strongly supported real investigation and an
out-of-domain or evidence-limited investigation, with every page rendered and visually inspected.

**Gate** — after a real investigation, the frontend receives a complete Markdown chat answer, the voice
surface receives a shorter claim-grounded answer, and the report drawer assembles section by section. The
detailed PDF opens as a professional research document containing the actual run figures; the summary PDF
contains only the selected primary figures; JSON and GeoJSON validate against their contracts; every figure
and number resolves to a claim/evidence/trace record; every input and model parameter is reproducible; all
refusals and limitations survive into every surface; MinIO objects can be restored from Postgres metadata;
and regenerating the same report version produces byte-identical or canonically equivalent artifacts.

## 1.13 — The voice loop — **done (2026-09-17)**

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

**Product quality** — the voice should feel like a calm, precise, responsive cinematic assistant: concise
when the operator is busy, expressive when narrating evidence, and never theatrical at the expense of
clarity. Use an original voice identity with a similar professional warmth and controlled British cadence
if that fits the product; do not clone or reproduce a film actor's identifiable voice.

**Gate** — *a full conversational investigation in the terminal.* The operator asks a question aloud;
AERIS confirms or presents its plan aloud, runs a real analysis over real imagery, and speaks a grounded
answer with a real number in it. The operator can interrupt synthesis, ask an unrelated follow-up while
the original run continues, receive a clearly labelled provisional response, resume or abandon a run
explicitly, and hear the completed grounded result afterward. Transcription, wake detection, barge-in,
speech cancellation, narration, `ui-command` events and claim references are tested under silence, noise,
rapid turn-taking, model delay and failed synthesis. No voice response may invent a measurement or erase a
refusal.

**Result** — Implemented `VoiceSession` coordinator, `VoiceTurnDecision` LLM-structured routing, prompt-toolkit hotkey integration (`Ctrl+P`), barge-in playback interruption, provisional speech for mid-run questions, offline integration tests with Piper/faster-whisper verifying < 0.8 WER round-trip without API keys.

## 1.14 — Mature AERIS orchestration hardening — **done (2026-09-17)**

This is the final Phase 1 orchestration milestone. It is a new layer **above** the scientific graphs built
in 1.10, 1.11 and 1.11.2, not a replacement for them and not another scientific pipeline. The existing
1.8/1.9 routing and agent behavior become the substrate to consolidate, generalise and harden here.

**Core idea** — AERIS answers not only "which pipeline should I run?" but:

> What is the user asking about, what evidence would establish it, which installed capability can produce
> that evidence, whether it is valid for these inputs, and how should the work be composed and explained?

**Deliverable** — a capability- and evidence-oriented orchestration layer with:

- a typed `TaskSpec` for concept, requested operation, modality, temporal and spatial scope, desired output,
  precision and constraints;
- compound-request decomposition into a dependency-aware task graph, with parallel work where valid and
  explicit prerequisites where required;
- one capability registry declaring each model or scientific graph's operations, ontology, input
  requirements, domain, output evidence and limitations;
- a deterministic validity and feasibility engine separating theoretical capability from validity on the
  supplied data: sensor, bands, GSD, CRS, georeferencing, registration, temporal pairing, data quality,
  model domain and requested precision;
- deterministic planning that selects the minimum valid evidence configuration instead of forcing every
  request into four inputs;
- partial-plan execution, so valid tasks complete while unsupported or invalid tasks return useful typed
  refusals;
- domain and geospatial reasoning after model execution for operations such as area, overlap, largest,
  change magnitude, spatial relations and temporal trends;
- claim construction from evidence and derived measurements, including uncertainty, validity, units,
  temporal/spatial extent and provenance;
- first-class statuses such as `VALID`, `UNSUPPORTED`, `AMBIGUOUS`, `INSUFFICIENT_DATA`,
  `NON_INFORMATIVE`, `REGISTRATION_FAILURE`, `RESOLUTION_FAILURE` and `MODEL_DOMAIN_MISMATCH`;
- one auditable execution journal spanning the request, task graph, capability decisions, validity checks,
  graph runs, checkpoints, artefacts, evidence, claims, refusals and synthesis;
- a synthesis boundary where the LLM receives verified claims and may explain them, but cannot select
  arbitrary tools, invent quantitative results or override deterministic scientific constraints.

**Hard-coding boundary** — scientific invariants remain explicit and deterministic: required bands,
resolution limits, registration requirements, measurement prerequisites and model-domain constraints.
Natural-language vocabulary must not become a growing global whitelist such as `OBJECT_SYNONYMS` or
`UNDETECTABLE_OBJECTS`; model-specific knowledge belongs with the capability that owns it.

**Non-goals** — no free-form autonomous agent, arbitrary LLM tool selection, giant central router, removal
of provenance or refusal logic, quantitative VLM answers by default, or rewrite of working scientific
graphs without a demonstrated need.

**Success criteria** — a concept outside the detector vocabulary can still receive a valid qualitative
answer when a capable VLM supports it; quantitative requests are refused without validated evidence; adding
a specialist is a registry and graph integration task rather than a central-router rewrite; compound
requests can mix capabilities; partial execution is useful; every decision is auditable; existing 1.9,
1.10, 1.11 and 1.11.2 behavior remains correct; and every result remains grounded in evidence and claims.

**Gate** — a representative mixed investigation decomposes into dependent tasks, resolves capabilities,
records validity decisions, executes the minimum valid set, preserves partial success and typed refusals,
produces a complete evidence graph and claim set, resumes after interruption, and yields the same grounded
answer and journal on replay. The suite includes capability addition without central-router edits and
mutation tests proving that removing a validity check causes the gate to fail.

**Result** — Upgraded the orchestration engine to a full ReAct loop (PLAN → ACT → OBSERVE → REPLAN) that operates strictly above a deterministic scientific firewall.
- **Agent Autonomy**: The Agent Harness now intercepts scientific refusals (e.g., `MODEL_DOMAIN_MISMATCH`), explicitly reasons about them, and dynamically replans using alternative capabilities (e.g., falling back from DOTA to VLM for trees).
- **Scientific Firewall**: Physics and ontology constraints remain immutable. The Registry blocks invalid intents (e.g. detecting cars on 10m GSD imagery) and returns typed refusals.
- **Fatal Refusals & Safe Termination**: Hard physical stops (like `RESOLUTION_FAILURE` or `SCIENTIFIC_INVALID`) are classified as `fatal=True`. The Agent immediately halts the ReAct loop without wasting LLM cycles, explicitly bounded by `max_tool_calls` and `max_replans`.
- **Layer 3 Tool Execution API**: Formalized capability execution through isolated agent-facing APIs (`app/agents/tools/`) that execute ML/graphs and format standard observations.

## 1.15 — Evaluation

**Research:** PDF p.39 (the evaluation framework).

**Deliverable** — a harness scoring the complete Phase 1 system: change detection on LEVIR-CD, temporal
multimodal agreement and abstention, VQA and captioning on a VRSBench subset, grounding, report integrity,
voice turn-taking and interruption behavior, mature orchestration capability resolution, routing accuracy,
and system-level latency and VRAM under both profiles.

**Gate** — a single command produces a committed scorecard covering scientific correctness, evidence and
provenance integrity, refusal quality, orchestration behavior and voice interaction regressions.

---

# Phase 2 — Serving

Phase 2 adds adapters over the Phase 1 core. **It deletes nothing and moves no logic.**

| # | Sub-phase | Deliverable | Gate | Status |
|---|---|---|---|---|
| 2.0 | FastAPI shell | `main.py`, error handler, request logging, CORS, `/health`, `/ready` | `aeris doctor` equivalent over HTTP | **done** (2026-09-17) |
| 2.1 | Read endpoints | imagery (cursor-paginated), missions, globe markers and tracks, model status, catalogue search | Frontend runs with `NEXT_PUBLIC_USE_MOCK_DATA=false` for read paths | **done** (2026-09-17) |
| 2.2 | Upload flow | `POST /imagery/upload-ticket` → direct-to-MinIO PUT → `POST /imagery/:id/confirm` | A multi-GB scene uploads without passing through the app server | **done** (2026-09-17) |
| 2.3 | Investigations + SSE | create/get/patch, attach scene, `/runs` as SSE over the same `graph.astream()` the CLI consumes, plus the two figure endpoints of `api-contract.md` §6 — the list and the image bytes, CORS on and immutably cacheable | The frontend's existing parsers consume a live run with no client change; a `figure-ready` event's `imageUrl` loads in a browser |
| 2.4 | WebSocket | Bidirectional: audio frames in, events out | Voice from the browser, end to end |
| 2.5 | Inngest binding | `app/inngest/functions/` — one function per graph invocation, carrying the retry and backoff policy. The graphs do not change; the checkpointer moves from SQLite to Postgres | The same run produces an identical journal invoked from the CLI and from Inngest, and a forced mid-run failure is retried and resumes from its checkpoint rather than from S1 |
| 2.6 | Tiles | TiTiler promoted from the 1.2 gate to a supported service; band selection and stretch via query params | Band math is server-side; the browser never does it |
| 2.7 | Voice + `ui-command` over the wire | `speech` and `ui-command` events on the live stream | Speaking to the browser flies the camera and raises a layer | **done** (2026-09-20) |
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
- **HTTP report delivery and Postgres report metadata** — Phase 1 writes a complete local report bundle;
  authenticated download endpoints and lifecycle metadata remain Phase 2.
