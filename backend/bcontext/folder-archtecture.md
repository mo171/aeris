# Where every backend file goes, and the four rules the tree encodes.

**what** : The authoritative directory layout for `backend/`, annotated with what each folder owns. Also
states the four placement rules that the shape of the tree exists to enforce: `cli/` and `routes/` as
siblings, LangGraph as the only orchestrator, maths in its own module, and `async` everywhere but `math/`.
**where**: Read before creating any file. If a new file has no obvious home here, the folder is missing and
this document is edited in the same change — a file placed "temporarily" never moves.
**how**  : The tree is grouped by responsibility, not by technical kind, so a subsystem's service, its nodes
and its maths sit near each other. `architecture-context.md` says *what may depend on what*; this says
*where it lives*.

> Names marked `(Phase 2)` do not exist until Phase 2 and are listed so nothing is designed into a corner.

---

## The four rules this tree encodes

1. **`cli/` and `routes/` are sibling adapters over one core.** Neither imports the other. Anything both
   need lives in a service. Phase 1 ships `cli/` only; Phase 2 adds `routes/` and deletes nothing.
2. **LangGraph is the only orchestrator, Inngest is the only retry loop.** There is no `runner.py`, no
   `executor.py`, no `pipeline.py`, no `handlers/retry.py`. Graph, typed state, resume and streaming come
   from LangGraph; trigger, backoff and replay come from Inngest (ADR-002).
3. **Maths never lives in the file that uses it.** A subsystem that computes a number carries a sibling
   `math/` package. The service chooses *which* method; `math/` contains *the* method
   (`architecture-context.md` §12).
4. **Everything is `async def` except `math/`.** `math/` modules are pure and sync, and are reached with
   `asyncio.to_thread` (`architecture-context.md` §11).

---

```
backend/
│
├── app/
│   ├── main.py                          # (Phase 2) FastAPI app factory. Empty in Phase 1.
│   ├── config.py                        # pydantic-settings. The only file that reads os.environ.
│   │
│   ├── cli/                             # PHASE 1 ADAPTER. Sibling to routes/, never imported by it.
│   │   ├── main.py                      # Typer app. The only place asyncio.run() is called.
│   │   ├── doctor.py                    # `aeris doctor` - the dependency table (Phase 0.6) DONE
│   │   ├── dataset.py                   # `aeris dataset list|fetch`
│   │   ├── ingest.py                    # `aeris ingest <path>`
│   │   ├── analyse.py                   # `aeris analyse --scene --query`
│   │   ├── run.py                       # `aeris run` - start | --resume | --replay  DONE (1.0). 1.10
│   │   │                                 #   points it at the three real graphs; the flags do not change.
│   │   ├── voice.py                     # `aeris voice` - the spoken loop
│   │   └── renderers/                   # Consumers of the LangGraph stream. Not a protocol - just consumers.
│   │       ├── trace_renderer.py        # draws the live S1-S20 trace in the terminal  DONE (1.0)
│   │       ├── figure_writer.py         # writes figure-ready images to runs/<run_id>/figures/ and prints the path
│   │       └── journal_writer.py        # appends runs/<run_id>.jsonl, replayable through the frontend's Zod  DONE (1.0)
│   │
│   ├── routes/                          # (Phase 2) Declaration only. No logic, no database, no model.
│   │   ├── investigation.py
│   │   ├── imagery.py
│   │   ├── missions.py
│   │   ├── analysis.py
│   │   ├── figures.py                   # GET /figures/{id} - the image bytes. CORS on, immutably cacheable.
│   │   ├── models.py
│   │   ├── reports.py
│   │   └── health.py
│   │
│   ├── controllers/                     # Validate, call one service, shape the response. Shared by cli/ and routes/.
│   │   ├── investigation_controller.py
│   │   ├── imagery_controller.py
│   │   ├── analysis_controller.py
│   │   ├── figure_controller.py
│   │   ├── mission_controller.py
│   │   └── report_controller.py
│   │
│   ├── schemas/                         # Pydantic. camelCase on the wire (api-contract.md §1).
│   │   ├── requests/
│   │   │   ├── investigation.py
│   │   │   ├── imagery.py
│   │   │   ├── analysis.py
│   │   │   └── mission.py
│   │   ├── responses/
│   │   │   ├── investigation.py
│   │   │   ├── evidence.py
│   │   │   ├── trace.py
│   │   │   ├── analysis.py
│   │   │   └── common.py
│   │   └── events/                      # The stream event union. Survived ADR-002; it IS the frontend contract.
│   │       ├── run.py                   # run-start, run-complete, run-error
│   │       ├── trace.py                 # trace-step
│   │       ├── layer.py                 # layer-ready
│   │       ├── claim.py                 # claim
│   │       ├── answer.py                # answer-token
│   │       ├── figure.py                # figure-ready  (NEW - api-contract.md §6) + legend + renderSpec
│   │       ├── speech.py                # speech        (NEW - api-contract.md §5)
│   │       └── ui_command.py            # ui-command    (NEW - api-contract.md §4)
│   │
│   ├── services/
│   │   │
│   │   ├── sessions/                    # The harness. A session = one thread id + its running tasks.
│   │   │   ├── session.py               # Opens/closes a session; owns the thread id and memory namespace
│   │   │   ├── run_handle.py            # Launching a run returns a handle IMMEDIATELY; astream() is
│   │   │   │                            #   consumed by a background task. Why: product-truth.md §1.3.1 -
│   │   │   │                            #   the conversation must continue while the run runs.
│   │   │   └── fanout.py                # One run's stream -> many consumers (trace, journal, speech)
│   │   │
│   │   ├── pipeline/                    # LangGraph only. Nothing here orchestrates by hand.
│   │   │   ├── state.py                 # The TypedDict state carried between nodes. DATA ONLY - never a
│   │   │   │                             #   Python object, or the checkpoint depends on our module layout
│   │   │   ├── node.py                   # @pipeline_node - mints the step id, emits the trace step twice,
│   │   │   │                             #   times it, checks abandonment in and out. NOT StepRunner:
│   │   │   │                             #   no retry, no executor, no protocol (ADR-002)
│   │   │   ├── checkpointer.py          # Selects SQLite (P1) / Postgres (P2) checkpointer from config
│   │   │   ├── stream.py                # Thin helpers that write event models via get_stream_writer()
│   │   │   ├── cancellation.py          # Node-boundary cancellation. EXPLICIT abandonment only, never
│   │   │   │                             #   barge-in (product-truth.md §1.3, corrected 2026-08-31)
│   │   │   ├── memory_store.py           # BaseStore for long-term memory, selected from config (§1.6)
│   │   │   │
│   │   │   ├── nodes/                   # One stage each. async def(state) -> state update. No retry, no maths.
│   │   │   │   ├── input_validation.py
│   │   │   │   ├── metadata_analysis.py
│   │   │   │   ├── query_interpretation.py
│   │   │   │   ├── task_classification.py
│   │   │   │   ├── modality_check.py
│   │   │   │   ├── temporal_check.py
│   │   │   │   ├── mission_planning.py
│   │   │   │   ├── model_routing.py
│   │   │   │   ├── inference.py
│   │   │   │   ├── evidence_generation.py
│   │   │   │   ├── confidence.py
│   │   │   │   ├── response_synthesis.py
│   │   │   │   └── trace_generation.py
│   │   │   │
│   │   │   └── graphs/                  # StateGraph composition + add_conditional_edges routing tables
│   │   │       ├── investigation_graph.py
│   │   │       ├── single_image_graph.py
│   │   │       ├── temporal_graph.py
│   │   │       └── cross_modal_graph.py
│   │   │
│   │   ├── imagery/                     # S1-S6, S11
│   │   │   ├── ingestion.py
│   │   │   ├── metadata.py
│   │   │   ├── validation.py
│   │   │   ├── cog.py                   # COG conversion into MinIO
│   │   │   ├── tiling.py
│   │   │   └── math/
│   │   │       ├── windowing.py         # tile grid + overlap arithmetic
│   │   │       ├── resampling.py        # the kernels; method choice by dtype stays in the service
│   │   │       └── quality_statistics.py# nodata fraction, histogram sanity, resolution report
│   │   │
│   │   ├── preprocessing/               # S7-S10 and the SAR branch
│   │   │   ├── cloud_masking.py
│   │   │   ├── reprojection.py
│   │   │   ├── coregistration.py        # runs it, reports the residual, REFUSES above tolerance
│   │   │   ├── sar_calibration.py       # order is fixed: calibrate -> speckle -> terrain
│   │   │   └── math/
│   │   │       ├── cloud_probability.py
│   │   │       ├── registration_residual.py  # phase correlation / tie points -> residual in pixels
│   │   │       ├── grid_alignment.py
│   │   │       ├── speckle_filters.py
│   │   │       └── terrain_flattening.py     # layover + shadow masks retained, not discarded
│   │   │
│   │   ├── spectral/                    # S12 - the reference example of rule 3
│   │   │   ├── indices.py               # async. Picks the index, maps bands per sensor, masks, returns a result.
│   │   │   └── math/
│   │   │       ├── index_formulae.py    # sync, pure. ndvi/evi/savi/ndwi/mndwi/ndbi/nbr over arrays.
│   │   │       └── thresholds.py        # sync, pure. Otsu, fixed cut-offs, histogram statistics.
│   │   │
│   │   ├── detection/                   # S13
│   │   │   ├── detector.py
│   │   │   ├── postprocess.py
│   │   │   └── math/
│   │   │       ├── box_operations.py    # iou, nms, box <-> polygon
│   │   │       └── geometry.py
│   │   │
│   │   ├── segmentation/                # S13
│   │   │   ├── segmenter.py
│   │   │   ├── postprocess.py
│   │   │   └── math/
│   │   │       ├── morphology.py        # opening/closing, small-object removal
│   │   │       └── vectorize.py         # raster mask -> polygons -> simplified geometry
│   │   │
│   │   ├── change_detection/            # S13
│   │   │   ├── detector.py
│   │   │   ├── comparison.py            # gated by the co-registration residual
│   │   │   ├── classification.py
│   │   │   └── math/
│   │   │       ├── differencing.py      # optical difference / ratio
│   │   │       ├── log_ratio.py         # SAR change
│   │   │       └── change_statistics.py # magnitude, class transitions
│   │   │
│   │   ├── optical_sar/                 # S13, S15 - late fusion only (PDF §9, p.19)
│   │   │   ├── per_sensor_runs.py       # two independent runs
│   │   │   ├── fusion.py                # joins at S15; REFUSES worse than sub-pixel registration
│   │   │   ├── agreement_ledger.py      # agreementRowSchema
│   │   │   └── math/
│   │   │       ├── alignment.py
│   │   │       └── fusion_rules.py      # the decision arithmetic, per sensor, kept separable
│   │   │
│   │   ├── vqa/                         # S14
│   │   │   ├── inference.py
│   │   │   └── prompts.py
│   │   │
│   │   ├── captioning/                  # S14
│   │   │   └── inference.py
│   │   │
│   │   ├── grounding/                   # S14
│   │   │   ├── inference.py
│   │   │   ├── postprocess.py
│   │   │   └── math/
│   │   │       └── box_operations.py
│   │   │
│   │   ├── evidence/                    # S15, S18, S19
│   │   │   ├── builder.py               # evidence + claim objects
│   │   │   ├── spatial.py
│   │   │   ├── confidence.py            # float | None. Never 0.0 by default.
│   │   │   ├── trace.py                 # trace steps + artefact URIs
│   │   │   └── math/
│   │   │       ├── area.py              # equal-area CRS reprojection, then hectares. Never from degrees.
│   │   │       ├── simplification.py
│   │   │       └── confidence_aggregation.py
│   │   │
│   │   ├── rendering/                   # Array -> finished image. product-truth.md §1.5, api-contract.md §6.
│   │   │   ├── figures.py               # async. Chooses the ramp/stretch, composes, writes to storage, emits figure-ready.
│   │   │   ├── overlays.py              # boxes, labels, masks over the true-colour scene
│   │   │   ├── comparisons.py           # T1 | T2 | change mask, side by side
│   │   │   ├── legends.py               # the machine-readable legend that ships with every figure
│   │   │   └── math/
│   │   │       ├── color_ramps.py       # sync, pure. Named ramp -> lookup table. Shared with the frontend's ramps.
│   │   │       ├── stretch.py           # sync, pure. Percentile / min-max / fixed. Recorded in renderSpec.
│   │   │       └── rasterize.py         # sync, pure. Scaled array + ramp + alpha -> RGBA. Nodata stays transparent.
│   │   │
│   │   └── reports/
│   │       ├── generator.py             # sectioned, streamed section by section
│   │       └── exporters.py             # JSON + GeoJSON (PDF in Phase 2 if it earns the time)
│   │
│   ├── agents/                          # Plans, routes, dispatches. Computes nothing.
│   │   ├── graph.py                     # the agent StateGraph, with interrupt() for plan approval
│   │   ├── state.py
│   │   ├── planner.py
│   │   ├── router.py                    # deterministic: intent -> table -> pipeline graph (PDF p.24)
│   │   ├── tools/
│   │   │   ├── analysis_tools.py        # backend functions bound with LangChain bind_tools
│   │   │   └── interface_tools.py       # mirrors the frontend command registry -> ui-command events
│   │   └── prompts/
│   │       ├── planner.py
│   │       ├── analyst.py
│   │       └── synthesis.py
│   │
│   ├── models/                          # ML model residency, not SQLAlchemy models.
│   │   ├── registry.py                  # the twelve model ids - vocabulary shared with the frontend
│   │   ├── loader.py
│   │   ├── manager.py                   # VRAM profile, lazy load, LRU eviction under an async lock
│   │   ├── vqa.py
│   │   ├── grounding.py
│   │   ├── segmentation.py
│   │   ├── detection.py
│   │   ├── change.py
│   │   └── fusion.py
│   │
│   ├── db/                              # SQLAlchemy persistence shape. Carries no business logic.
│   │   ├── models/
│   │   │   ├── scene.py
│   │   │   ├── investigation.py
│   │   │   ├── run.py
│   │   │   ├── evidence.py
│   │   │   ├── claim.py
│   │   │   ├── trace_step.py
│   │   │   └── mission.py
│   │   └── repositories/                # async queries. Services call these, never a Session directly.
│   │
│   ├── voice/
│   │   ├── transcription.py             # faster-whisper + voice-activity detection
│   │   ├── synthesis.py                 # Piper / Kokoro, streamed
│   │   ├── barge_in.py                  # cancels synthesis and the run behind it
│   │   └── loop.py                      # utterance -> agent -> answer -> speech
│   │
│   ├── inngest/                         # (Phase 2) Durable execution. Replaces the old workers/ folder.
│   │   ├── client.py
│   │   └── functions/                   # One function wraps one graph invocation. Retry policy lives here.
│   │       ├── ingest_scene.py          # the retry loop for ingestion (ADR-002)
│   │       ├── run_investigation.py
│   │       └── generate_report.py
│   │
│   ├── lib/                             # Infrastructure and cross-cutting. Imports nothing from services/.
│   │   ├── llm/                         # THE ONE CONTAINMENT RULE: LangChain/LangGraph construction only here.
│   │   │   ├── chat_model.py            # init_chat_model from config. ~40 lines. Not a wrapper.
│   │   │   └── embeddings.py
│   │   ├── responses.py
│   │   ├── exceptions.py
│   │   ├── error_handler.py
│   │   ├── logger.py
│   │   ├── database.py                  # async engine + AsyncSession (asyncpg)
│   │   ├── redis.py                     # model locks, short-lived cache
│   │   ├── storage.py                   # MinIO over the S3 API, presigned PUT/GET
│   │   ├── inngest.py                   # the Inngest client + health probe. The FUNCTIONS live in
│   │   │                                #   app/inngest/ (Phase 2.5) and import from here - same split
│   │   │                                #   as database.py vs app/db/models/.
│   │   ├── tiles.py                     # TiTiler URLs, TileJSON
│   │   ├── websocket.py                 # (Phase 2)
│   │   ├── telemetry.py
│   │   └── security.py                  # (Phase 2)
│   │
│   └── constants/                       # Fixed vocabularies. Imports nothing at all.
│       ├── stages.py                    # S1-S20 + the artefact-producing set. Shared with the frontend - never invented here.
│       ├── model_ids.py                 # the twelve ids + the capability vocabulary. Shared with the frontend.
│       ├── intents.py                   # the nine intents
│       ├── scenes.py                    # modality + scene role + temporal role. One module: "what is this scene, and what job does it do".
│       ├── statuses.py                  # run / investigation / message / mission lifecycle + model health
│       ├── evidence.py                  # claim kind, evidence kind, metric direction
│       ├── layers.py                    # layer kind + render mode. What the globe draws, and how.
│       ├── reports.py                   # the eight sections + the order they stream in
│       ├── figure_kinds.py              # rgb-composite | index-map | mask-overlay | detection-overlay | comparison | histogram | sar-backscatter, + legend kinds
│       ├── errors.py                    # the stable `code` a client branches on
│       ├── logs.py                      # JSON field names, format strings, third-party noise floor
│       ├── pagination.py                # default and maximum page size (named for what it bounds, not `limits.py`)
│       ├── color_ramps.py               # (Phase 1.2.1) named ramps + their domains. Shared vocabulary with the frontend's legends.
│       ├── ui_commands.py               # (deferred) mirrors frontend/lib/constants/commands.ts - written when `ui-command` is first emitted
│       └── tasks.py                     # (Phase 0.5) Inngest event names + the `aeris/<domain>.<action>` convention
│
├── notebooks/                           # A thinking surface. Nothing ships from here.
│   ├── 00_experiment/
│   ├── 01_remote_sensing/
│   ├── 02_data_exploration/
│   ├── 03_vlm/
│   ├── 04_vqa/
│   ├── 05_grounding/
│   ├── 06_segmentation/
│   ├── 07_change_detection/
│   ├── 08_optical_sar/
│   ├── 09_finetuning/
│   ├── 10_evaluation/
│   └── experiments/
│
├── training/
│   ├── datasets/
│   ├── configs/
│   ├── scripts/
│   ├── trainers/
│   └── checkpoints/
│
├── tests/
│   ├── unit/
│   │   └── math/                        # Mirrors every services/*/math/. Values checked by hand or QGIS.
│   ├── integration/
│   ├── pipeline/
│   ├── agents/
│   ├── contracts/                       # Fixtures validated against bcontext/contracts/
│   ├── fixtures/                        # Small. A 400 MB scene makes it an integration test.
│   └── evaluation/
│
├── scripts/
│   ├── download_models.py
│   └── setup_datasets.py
│                                        # NOTE: export_contracts.py was planned here and is NOT here.
│                                        #   The exporter has to *evaluate* Zod, which only Node can do -
│                                        #   a Python version would parse TypeScript or shell out to Node
│                                        #   anyway. It lives with the schemas it converts, at
│                                        #   frontend/scripts/export-contracts.mts, which is also where
│                                        #   api-contract.md §0 puts the authority. See Phase 0.7.
│
├── bcontext/
│   └── contracts/                       # schemas.json - 92 schemas, generated by
│                                        #   frontend/scripts/export-contracts.mts. Generated, not authored,
│                                        #   and committed so the backend suite needs no Node installed.
│
├── .env
├── .env.example
├── pyproject.toml                       # replaces requirements.txt in Phase 0.1
├── uv.lock
├── Dockerfile
└── docker-compose.yml
```

---

## Placement questions, answered

| You are writing… | It goes in |
|---|---|
| A formula, a transform, a statistic, a threshold | `services/<subsystem>/math/` — sync, pure, no project imports beyond `constants/` |
| The choice of *which* formula to apply | The async service file above that `math/` folder |
| One stage of S1–S20 | `services/pipeline/nodes/` — `async def`, no maths, no retry, no database |
| The order stages run in, or a branch between them | `services/pipeline/graphs/` — a `StateGraph`, not an `if` chain in a service |
| Retry, backoff, or "run this again" | `app/inngest/functions/` and nowhere else |
| A resume point or run state | Nowhere. It is the LangGraph checkpointer, configured in `services/pipeline/checkpointer.py` |
| A chat-model or embeddings construction | `lib/llm/` only. Everywhere else imports from there |
| An emitted event | A model in `schemas/events/`, written through `services/pipeline/stream.py` |
| A colour ramp, a stretch, or an array → RGBA conversion | `services/rendering/math/` — sync and pure, like every other `math/` |
| A figure's title, caption, legend or composition | `services/rendering/` — the async layer that *chooses* the ramp and stretch and records them in `renderSpec` |
| A named colour ramp or a figure kind | `constants/color_ramps.py` / `constants/figure_kinds.py`. Shared vocabulary with the frontend's legends — never invented in a service |
| Drawing a tile for the globe | Nowhere here. Tiles are TiTiler's, via `lib/tiles.py`. Tiles are not figures (`api-contract.md` §8) |
| Something both the CLI and a future route need | A service. Never in `cli/`, never in `routes/` |
| A hardcoded list of anything | `constants/` |
| A URL, credential, path, threshold default or timeout | `.env` → `config.py` |

## Folders that were deliberately removed

| Removed | Because |
|---|---|
| `services/pipeline/pipeline.py`, `context.py`, `executor.py` | A hand-rolled executor and context object. LangGraph's compiled graph and typed state replace all three (ADR-002) |
| `services/pipeline/runner.py` | Was the `StepRunner` protocol. Deleted — retry belongs to Inngest, resume to the checkpointer |
| `lib/events.py` | Was the `EventSink` protocol. The event *models* survive in `schemas/events/`; the transport is the LangGraph stream |
| `workers/` with `jobs/` and `handlers/{success,failure,retry}.py` | Celery-shaped, and `handlers/retry.py` is a hand-written retry loop, which invariant 5 forbids. Replaced by `app/inngest/functions/` |
| `spectral/ndvi.py`, `ndwi.py`, `nbr.py` | One file per index put the maths beside the application logic. They are now functions in `spectral/math/index_formulae.py`, and `indices.py` chooses between them |
