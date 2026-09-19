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
│   │   ├── dataset.py                   # `aeris dataset list|show|fetch|search`  DONE (1.1)
│   │   ├── ingest.py                    # `aeris ingest inspect|scene|index`  DONE (1.2)
│   │   ├── preprocess.py                # `aeris preprocess coregister|sar`  DONE (1.3)
│   │   ├── analyse.py                   # `aeris analyse --scene --query`  DONE (1.4). Runs the
│   │   │                                 #   routed graph through the same session as `run`.
│   │   ├── run.py                       # `aeris run` - start | --resume | --replay  DONE (1.0). 1.10
│   │   │                                 #   points it at the three real graphs; the flags do not change.
│   │   ├── models.py                    # `aeris models status|warm|evaluate`  DONE (1.6). The fleet strip,
│   │   │                                 #   the watchable eviction, the LEVIR-CD score.
│   │   ├── voice.py                     # `aeris voice` - the spoken loop
│   │   └── renderers/                   # Consumers of the LangGraph stream. Not a protocol - just consumers.
│   │       ├── trace_renderer.py        # draws the live S1-S20 trace in the terminal  DONE (1.0)
│   │       ├── figure_writer.py         # DONE (1.2.1). FETCHES each figure back out of storage - the same
│   │       │                            #   thing the frontend does with imageUrl - so a bad key fails here
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
│   │   ├── geo.py                       # GeoPoint, GeoBoundingBox - WGS 84 degrees, bounded  DONE (1.5)
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
│   │       ├── layer.py                 # layer-ready + EvidenceLayer/Feature/Item  DONE (1.5)
│   │       ├── claim.py                 # claim + Claim/ClaimMetric  DONE (1.5)
│   │       ├── answer.py                # answer-token
│   │       ├── figure.py                # figure-ready + legend + renderSpec  DONE (1.2.1)
│   │       ├── speech.py                # speech        (NEW - api-contract.md §5)
│   │       └── ui_command.py            # ui-command    (NEW - api-contract.md §4)
│   │
│   ├── prompts/                         # Centralized prompt registry. Every system prompt and template.
│   │   ├── agent.py                     # routing, planning, synthesis, interface-control
│   │   ├── voice.py                     # voice-turn classifier, grounded narration, progress, provisional
│   │   ├── investigations.py            # dynamic region suggestions
│   │   ├── harness.py                   # orchestration planner, scientific facts synthesis
│   │   ├── report.py                    # report editorial policy
│   │   └── vlm.py                       # system prompt, SAR note, VQA, caption, constrained answer
│   │
│   ├── services/
│   │   │
│   │   ├── datasets/                    # Phase 1.1. Acquisition, licensing, enumeration. DONE
│   │   │   ├── catalogue.py             # what is ON DISK + require_trainable() - the licence gate
│   │   │   ├── loader.py                # THE single loader. Reads DatasetLayout, no branch per dataset
│   │   │   └── acquisition.py           # STAC search/fetch, archive download, manual instructions
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
│   │   │   │   │                         #   A node reads its own step id with `current_trace_step_id()` and
│   │   │   │   │                         #   sets its completion line with `describe_trace_step()` (node.py).
│   │   │   │   ├── cloud_handling.py        # S7  DONE (1.4). SCL -> mask artefact, or "no mask" said aloud.
│   │   │   │   ├── feature_extraction.py    # S12 DONE (1.4). Mask the bands, then the formula; artefact + figure.
│   │   │   │   ├── evidence_localisation.py # S15 DONE (1.4, 1.5). Threshold, measure vs OBSERVED ground,
│   │   │   │   │                            #   then BOTH representations, evidence items, claims, overlay.
│   │   │   │   ├── answer_generation.py     # S16 DONE (1.5, 1.7). The constrained generator's phrasing (or
│   │   │   │   │                            #   the template), then the recorded caveats; trace says which.
│   │   │   │   ├── confidence_estimation.py # S18 DONE (1.5). minimum-of-stated; None when nothing stated.
│   │   │   │   ├── provenance_logging.py    # S19 DONE (1.5, 1.10). provenance.json + evidence-graph.json from
│   │   │   │   │                            #   state; parameters and artefacts are the branch's own.
│   │   │   │   ├── input_validation.py      # S1  DONE (1.10). What was handed in; refuses by name.
│   │   │   │   ├── object_detection.py      # S13+S15 DONE (1.10). dota-detector; boxes -> layer + count claims;
│   │   │   │   │                            #   the resolution gate applied to the output too.
│   │   │   │   ├── segmentation.py          # S13+S15 DONE (1.10). segformer-landcover; class map + confidence
│   │   │   │   │                            #   artefacts; the classes asked for as regions; the cover table.
│   │   │   │   ├── change_detection.py      # S9+S13+S15 DONE (1.10). The residual gate as its own step,
│   │   │   │   │                            #   changeformer, the change mask as regions, before|after|change.
│   │   │   │   └── vlm_reading.py           # S14 DONE (1.7, 1.10). Reads the primary figure; or IS the
│   │   │   │                                #   specialist for a perception question (a labelled claim).
│   │   │   ├── inputs.py                # Nodes get the inspected input and the masked frame back from state
│   │   │   ├── runner.py                # AnalysisRequest -> one graph run (CLI and agent share it)
│   │   │   │
│   │   │   └── graphs/                  # StateGraph composition + add_conditional_edges routing tables
│   │   │       ├── probe.py             # DONE (1.0). Two nodes, no imagery - "is the spine broken?"
│   │   │       ├── single_image.py      # DONE (1.10). S1 -> (S7) -> branch by intent (table) -> S15 -> S14
│   │   │       │                        #   -> S16 -> S18 -> S19. The 1.4 index-query graph is its S12 branch.
│   │   │       ├── temporal.py          # DONE (1.10). S1 -> (S7 x2) -> S9 gate -> S13 -> S15 -> S14 -> ...
│   │   │       └── cross_modal_graph.py # 1.11, with the radar branch it fuses
│   │   │
│   │   ├── imagery/                     # S1-S6, S11  DONE (1.2)
│   │   │   ├── metadata.py              # S1-S3. Driver, CRS, bands, processing level - all READ, never
│   │   │   │                            #   inferred from a filename
│   │   │   ├── validation.py            # S4-S5. Severity, not a boolean: WARNS is carried into the
│   │   │   │                            #   trace, REFUSES stops the run
│   │   │   ├── cog.py                   # S6. COG conversion into MinIO. Predictor follows dtype
│   │   │   ├── tiling.py                # S11. Overlapping windows + weighted stitching
│   │   │   └── math/                    # pure, sync, no I/O, no policy
│   │   │       ├── windowing.py         # tile grid + overlap arithmetic + blend weights
│   │   │       ├── indices.py           # normalised difference + reflectance scaling. Carries the
│   │   │       │                        #   post-condition that caught the NDVI-of-347 bug
│   │   │       ├── web_mercator.py      # DONE (1.5). Geographic bounds + the zoom range a raster layer needs.
│   │   │       └── quality_statistics.py# nodata fraction, histogram sanity, resolution report
│   │   │
│   │   │   NOTE: `ingestion.py` was planned here and is not needed - `metadata.py` reads and
│   │   │   `validation.py` decides, and a third module between them had nothing left to do.
│   │   │   `resampling.py` arrives with 1.3, which is the first phase that actually resamples.
│   │   │
│   │   ├── preprocessing/               # S7-S10 and the SAR branch.  DONE (1.3)
│   │   │   ├── cloud_masking.py         # s2cloudless -> threshold -> projected shadow. Reports
│   │   │   │                            #   obscuredFraction, counting UNJUDGED pixels as unread.
│   │   │   ├── reprojection.py          # S8/S10. Resampling follows the data type, never the dtype.
│   │   │   ├── coregistration.py        # runs it, reports the residual, REFUSES above tolerance
│   │   │   ├── elevation.py             # Copernicus DEM GLO-30, windowed, on the scene's own grid.
│   │   │   │                            #   Terrain correction without a DEM is not terrain correction.
│   │   │   ├── sar_calibration.py       # order is fixed: calibrate -> speckle -> terrain. Calibration
│   │   │   │                            #   is SKIPPABLE (`None`): an RTC product calibrated twice is
│   │   │   │                            #   the square of the truth and opens cleanly.
│   │   │   └── math/
│   │   │       ├── cloud_probability.py
│   │   │       ├── registration_residual.py  # phase correlation -> residual in pixels. Nodata is filled
│   │   │       │                             #   with the tile MEAN; zero-fill is an edge it locks onto.
│   │   │       ├── grid_alignment.py
│   │   │       ├── speckle_filters.py        # Lee (1980) on the coefficient of variation. Speckle is
│   │   │       │                             #   multiplicative, and that IS the formula.
│   │   │       └── terrain_flattening.py     # layover + shadow retained. The sign convention is the
│   │   │                                     #   whole file - it was inverted once and looked fine.
│   │   │
│   │   ├── spectral/                    # S12 - the reference example of rule 3.  DONE (1.4)
│   │   │   ├── indices.py               # async. Phrase -> index + range; bands by ROLE onto the finest grid
│   │   │   │                            #   (SWIR resampled before it meets a 10 m band); L1C and unknown
│   │   │   │                            #   levels refused; the mask applied to the INPUTS, then the formula.
│   │   │   └── math/
│   │   │       ├── index_formulae.py    # sync, pure. ndvi/evi/savi/ndwi/mndwi/ndbi/nbr. Imports the one
│   │   │       │                        #   normalised-difference kernel from imagery/math (written once).
│   │   │       └── thresholds.py        # sync, pure. Range masks (NaN never detected), Otsu, summary.
│   │   │
│   │   ├── detection/                   # S13
│   │   │   ├── detector.py
│   │   │   ├── postprocess.py
│   │   │   └── math/
│   │   │       ├── box_operations.py    # iou, nms, box <-> polygon
│   │   │       └── geometry.py
│   │   │
│   │   ├── segmentation/                # S13. 1.5 built the mask -> polygons kernel first.
│   │   │   ├── segmenter.py
│   │   │   ├── postprocess.py
│   │   │   └── math/
│   │   │       ├── morphology.py        # opening/closing, small-object removal
│   │   │       └── vectorize.py         # DONE (1.5). Eight-connected labels -> one polygon per region,
│   │   │                                #   holes kept; per-region means. The labelling every count uses.
│   │   │
│   │   ├── change_detection/            # S13  DONE (1.6)
│   │   │   ├── detector.py              # leases `changeformer`, thresholds its probability, states the
│   │   │   │                            #   model's own mean certainty as the confidence
│   │   │   ├── comparison.py            # the residual gate (§8 rule 2) IN FRONT of the detector; the
│   │   │   │                            #   S13 node calls this and never the detector directly
│   │   │   ├── sar_change.py            # `sar-change`: log-ratio on the 1.3 chain's output, increase and
│   │   │   │                            #   decrease kept apart, layover/shadow unobserved not unchanged
│   │   │   ├── classification.py
│   │   │   └── math/
│   │   │       ├── differencing.py      # optical difference / ratio
│   │   │       ├── log_ratio.py         # DONE (1.6). 10 log10(after/before), two-sided dB threshold.
│   │   │       └── change_statistics.py # DONE (1.6). Change-class P/R/F1/IoU as counts; no accuracy.
│   │   │
│   │   ├── detection/                   # S13/S15 oriented-object detection  DONE (1.6)
│   │   │   ├── detector.py              # leases `dota-detector`; mean box score as the stated confidence
│   │   │   ├── labels.py                # YOLO-OBB (normalised) and DOTA labelTxt readers -> OrientedBox
│   │   │   └── math/
│   │   │       └── oriented_boxes.py    # polygon IoU (shapely), class-aware rotated NMS, greedy matching,
│   │   │                                #   DetectionScore as counts
│   │   │
│   │   ├── evaluation/                  # Scores a model against a benchmark. 1.6 seeds, 1.14 completes.
│   │   │   ├── change_detection.py      # DONE (1.6). The detector over a paired-mask split through the
│   │   │   │                            #   single loader; counts summed before ratios; nominal hectares.
│   │   │   └── object_detection.py      # DONE (1.6). Box P/R/F1 at IoU 0.5 over an annotation split at the
│   │   │                                #   pipeline's own threshold; mAP is 1.14's.
│   │   │
│   │   ├── optical_sar/                 # S13, S15 - late fusion only (PDF §9, p.19)
│   │   │   ├── per_sensor_runs.py       # two independent runs
│   │   │   ├── fusion.py                # joins at S15; REFUSES worse than sub-pixel registration
│   │   │   ├── agreement_ledger.py      # agreementRowSchema
│   │   │   └── math/
│   │   │       ├── alignment.py
│   │   │       └── fusion_rules.py      # the decision arithmetic, per sensor, kept separable
│   │   │
│   │   ├── vlm/                         # S14  DONE (1.7) - one package for VQA and captioning: one lease, one
│   │   │   ├── reading.py               #   `Reading` (text, prompt, model version, model-stated confidence)
│   │   │   └── math/
│   │   │       └── rendering.py         # the fixed S2 true-colour and S1 false-colour stretches; training
│   │   │                                #   and serving import the same functions
│   │   ├── query/                       # DONE (1.8). Query understanding: what is being asked, of what.
│   │   │   ├── classifier.py            # cues narrow to a family, kNN over the bank votes within it
│   │   │   ├── decomposer.py            # filler off, clauses split at connectives, pronouns flagged
│   │   │   ├── entities.py              # objects -> detector classes, region, temporal, sensor, wants
│   │   │   ├── bank.py                  # the labelled bank + held-out + fresh files, embedded once, cached
│   │   │   ├── intent_bank.jsonl        # 215 learned from; intent_holdout.jsonl 235 and intent_fresh.jsonl 45 scored
│   │   │   ├── intent_compound.jsonl    # 15 compound requests developed against; intent_compound_fresh.jsonl 35 scored
│   │   │   └── math/nearest.py          # weighted kNN vote, confidence and margin
│   │   │
│   │   ├── answer/                      # S16  DONE (1.7)
│   │   │   └── constrained.py           # claims -> facts with {m1} holes -> VLM prose -> numeral check ->
│   │   │                                #   holes filled from the claims. A hallucinated digit rejects the
│   │   │                                #   whole phrasing for the template.
│   │   │
│   │   ├── grounding/                   # S14
│   │   │   ├── inference.py
│   │   │   ├── postprocess.py
│   │   │   └── math/
│   │   │       └── box_operations.py
│   │   │
│   │   ├── evidence/                    # S15, S18, S19.  DONE (1.4, 1.5)
│   │   │   ├── artefacts.py             # DONE (1.4). A stage's array -> COG on disk + `artefacts` bucket;
│   │   │   │                            #   the state carries the path and key, never the array.
│   │   │   ├── spatial.py               # DONE (1.4). The geospatial-engine: hectares, coverage of OBSERVED
│   │   │   │                            #   ground, region count and density. Refuses a detection over
│   │   │   │                            #   unobserved pixels - the structural proof S12 masked first.
│   │   │   ├── builder.py               # DONE (1.5). A mask -> raster-mask layer AND polygon layer, the
│   │   │   │                            #   evidence items, the claims. Mints the whole chain in one place
│   │   │   │                            #   so a claim cannot exist without pixels behind it.
│   │   │   ├── trace.py                 # DONE (1.5). ProvenanceRecord + EvidenceGraph and their writers.
│   │   │   │                            #   Input hashes, parameters, artefact URIs, versions, the rule.
│   │   │   └── math/
│   │   │       ├── area.py              # DONE (1.4, 1.5). Pixel FOOTPRINTS projected into a local LAEA and
│   │   │       │                        #   summed; the mask is never resampled. `polygon_area` measures a
│   │   │       │                        #   region's outline in the same projection - one number.
│   │   │       ├── simplification.py    # DONE (1.5). Douglas-Peucker in metres, topology kept; then the
│   │   │       │                        #   outer ring in degrees. Holes cannot travel on the wire.
│   │   │       └── confidence_aggregation.py  # DONE (1.5). minimum-of-stated. None is absent, not 0.
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
│   │       ├── generator.py             # evidence dossier -> guarded canonical reader narrative
│   │       ├── markdown.py              # complete chat projection of that narrative
│   │       ├── voice.py                 # short speakable projection; no synthesis yet
│   │       ├── geojson.py               # geometry export without prose or recomputation
│   │       ├── exporters.py             # writes one local bundle after successful Phase 1 runs
│   │       └── pdf/                     # print-only concern: theme, components, page composition
│   │
│   ├── agents/                          # Plans, routes, dispatches. Computes nothing.  DONE (1.9)
│   │   ├── graph.py                     # understand -> plan -> approve (interrupt()) -> execute -> synthesise
│   │   ├── run.py                       # `converse()`: compile with the checkpointer, pause, resume with the operator's choice
│   │   ├── state.py                     # AgentState: data only; results accumulate per thread (the evidence store)
│   │   ├── planner.py                   # steps by the table, prose by the model, checked (count, numerals)
│   │   ├── arbiter.py                   # the model's one vote: uncertain margins, within the family, never over a rule
│   │   ├── router.py                    # DONE (1.8). `route_plan`: a request -> ordered steps (pronouns bound,
│   │   │                                #   same asks merged); `route`: deterministic intent -> table -> tool + graph (PDF p.24),
│   │   │                                #   then validation: two images for a pair, both sensors for cross-
│   │   │                                #   modal, an index the engine has, a class the detector knows and a
│   │   │                                #   pixel that can hold it. Refuses with the numbers.
│   │   └── tools/
│   │       ├── analysis_tools.py        # index query (the real graph via pipeline/runner.py), count, VQA, recall;
│   │       │                            #   @tool schemas, deterministic dispatch by the routing table
│   │       └── interface_tools.py       # spotlight_claim / focus_evidence / toggle_layer, bound with bind_tools;
│   │                                    #   every id checked against the run. Prompts: app/prompts/agent.py
│   │
│   ├── models/                          # ML model residency, not SQLAlchemy models.  DONE (1.6)
│   │   ├── registry.py                  # `LOADERS`: which of the twelve ids this process can build, bound
│   │   │                                #   to the fleet facts in constants/fleet.py
│   │   ├── loader.py                    # the device, MEASURED (`mem_get_info`); Hub downloads and
│   │   │                                #   SHA-256-pinned release assets into data/models; memory release;
│   │   │                                #   the `aeris doctor` row. torch is imported inside functions.
│   │   ├── manager.py                   # `lease()`: lazy load under the 0.3 Redis lock, LRU eviction of
│   │   │                                #   IDLE models to a declared budget, offline/warming/online/
│   │   │                                #   degraded, queueDepth, medianLatencyMs -> modelStatusSchema
│   │   ├── change.py                    # ChangeFormerV6 adapter: [0, 1] RGB (measured), 256 windows, stitched
│   │   ├── segmentation.py              # SegFormer-B2 LoveDA adapter via transformers, 512 windows
│   │   ├── detection.py                 # YOLO11s-OBB (DOTA v1.0) adapter via ultralytics, AGPL-3.0; RGB->BGR
│   │   │                                #   at the boundary, 1024 windows, seam-cut boxes dropped, rotated NMS
│   │   ├── vendor/
│   │   │   └── changeformer_v6.py       # wgcban's architecture, verbatim, MIT, licence in the header
│   │   ├── encoder.py                   # DONE (1.8). bge-small sentence encoder, CPU, CLS-pooled; a cached
│   │   │                                #   singleton, not a fleet member (no device budget, no claim)
│   │   ├── vlm.py                       # DONE (1.7). Qwen3-VL at `settings.vlm_size`, NF4 on CUDA, PEFT LoRA
│   │   │                                #   from `settings.vlm_adapter_repository`; version says `-unadapted`
│   │   │                                #   when none is attached. `vlm_record()` is what the manager admits by.
│   │   ├── grounding.py
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
│   │   ├── llm/                         # DONE (1.9)
│   │   │   ├── chat_model.py            # init_chat_model from LLM_PROVIDER/LLM_MODEL; `none` is a path; doctor probe
│   │   │   └── tracing.py               # LangSmith on from config - the one place os.environ is written
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
│   │   ├── tiles.py                     # DONE (1.5). TiTiler TileJSON, viewer and XYZ template URLs.
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
│       ├── fleet.py                     # (Phase 1.6) what each of the twelve ids IS here: capability, stages,
│       │                                #   weights source, measured VRAM footprint, tile size; the
│       │                                #   VRAM profile tiers (4 GB is a tier); engine vs learned.
│       ├── change.py                    # (Phase 1.6) the change threshold and the SAR log-ratio dB threshold
│       ├── detection.py                 # (Phase 1.6) DOTA's fifteen classes in checkpoint order, thresholds, tiling
│       ├── routing.py                   # (Phase 1.8) intent -> graph table, object synonyms -> DOTA classes,
│       │                                #   object lengths for the resolution gate, the cue regexes, the encoder
│       ├── vlm.py                       # (Phase 1.7) the Qwen3-VL variants and footprints, the image size, the
│       │                                #   token budgets, the numeral rule, the BigEarthNet.txt categories (not)
│       │                                #   trained. The prompt strings are app/prompts/vlm.py.
│       ├── spectral.py                  # (Phase 1.4) the seven indices, their band roles, coefficients,
│       │                                #   interpretation bands and the phrase -> target table. Transcribed
│       │                                #   from the frontend's overlays/spectral-indices.ts (PDF §3.3).
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
│   ├── 08_vlm_finetuning/               # DONE (1.7). Teaching notebooks: data analysis, zero-shot baseline,
│   │                                    #   the Kaggle LoRA run, base-vs-adapter. README explains the recipe.
│   ├── 09_finetuning/
│   ├── 10_evaluation/
│   └── experiments/
│
├── training/                            # Imports app/ constants; nothing under app/ imports from here.
│   ├── vlm/                             # DONE (1.7)
│   │   ├── prepare_bigearthnet_txt.py   # BigEarthNet.txt x Lithuania-summer LMDB -> rendered PNGs + jsonl,
│   │   │                                #   balanced per bucket, constant categories dropped, licence-gated
│   │   ├── prepare_rsvqa_lr.py          # RSVQA-LR by its published image splits, capped per type
│   │   ├── merge_instruction_sets.py    # -> train.jsonl / validation.jsonl + manifest
│   │   └── kaggle.py                    # upload-data | push | status | output through the kaggle CLI
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
| A formula, a transform, a statistic, a threshold | `services/<subsystem>/math/` — sync, pure, no project imports beyond `constants/` and a sibling `math/` |
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
| A stage's intermediate output (a mask, an index array) | `services/evidence/artefacts.py` writes it; the state carries its path and key. Never the array itself |
| A model's weights, footprint or version | `constants/fleet.py`. A service leases the model from `app/models/manager.py` and never loads it |
| A third-party model architecture | `app/models/vendor/`, verbatim, with its licence; an adapter beside it wraps it |
| A URL, credential, path, threshold default or timeout | `.env` → `config.py` |

## Folders that were deliberately removed

| Removed | Because |
|---|---|
| `services/pipeline/pipeline.py`, `context.py`, `executor.py` | A hand-rolled executor and context object. LangGraph's compiled graph and typed state replace all three (ADR-002) |
| `services/pipeline/runner.py` | Was the `StepRunner` protocol. Deleted — retry belongs to Inngest, resume to the checkpointer |
| `lib/events.py` | Was the `EventSink` protocol. The event *models* survive in `schemas/events/`; the transport is the LangGraph stream |
| `workers/` with `jobs/` and `handlers/{success,failure,retry}.py` | Celery-shaped, and `handlers/retry.py` is a hand-written retry loop, which invariant 5 forbids. Replaced by `app/inngest/functions/` |
| `spectral/ndvi.py`, `ndwi.py`, `nbr.py` | One file per index put the maths beside the application logic. They are now functions in `spectral/math/index_formulae.py`, and `indices.py` chooses between them |
