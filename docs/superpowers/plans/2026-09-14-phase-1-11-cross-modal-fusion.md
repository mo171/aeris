# Phase 1.11 Cross-Modal Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an auditable optical/SAR late-fusion graph with real evidence, refusals, persistence, and a retained real-data run.

**Architecture:** Two independent sensor branches produce masks and claims after a cross-sensor registration gate. A pure spatial policy constructs the agreement ledger, then the existing answer/confidence/provenance tail records a frontend-compatible result.

**Tech Stack:** Python 3.14, NumPy, SciPy, Rasterio, Pydantic v2, LangGraph, pytest, MinIO/PostGIS/Redis.

**Spec:** `docs/superpowers/specs/2026-09-14-phase-1-11-cross-modal-fusion-design.md`

**Execution record (2026-09-14):** Complete. The retained live run is
`backend/runs/run_01M2FS0F7KZW07CG8BA9S0HG7D`. Its Phase 1.11 contract, journal,
figures, evidence graph, provenance, and answer safety claim were validated from disk. The complete
repository suite ran with 670 passing tests; two unrelated legacy TiTiler tests could not find their
pre-existing Ghaziabad NDVI fixture in MinIO (`aeris-cog/.../ndvi.tif`) and therefore returned TiTiler's
"specified key does not exist" response. Phase 1.11 coverage, static checks, and `aeris doctor` are green.

## Global Constraints

- Fusion is late: neither sensor branch may consume the other branch's results.
- Cross-modal co-registration residual must be below `1.0` pixel.
- RTC SAR power is not calibrated a second time.
- Every ledger row is derived from spatial masks and has a physical reason.
- Confidence is nullable and fused confidence is the minimum contributing confidence.
- All checkpoint state is JSON-serializable wire data.
- Production code follows a witnessed red-green TDD cycle.

---

### Task 1: Wire contract and request routing

**Files:**
- Create: `backend/app/schemas/cross_modal.py`
- Modify: `backend/app/constants/pipeline.py`
- Modify: `backend/app/constants/routing.py`
- Modify: `backend/app/services/pipeline/graphs/__init__.py`
- Modify: `backend/app/agents/requests.py`
- Modify: `backend/app/services/pipeline/runner.py`
- Test: `backend/tests/contracts/test_cross_modal_contract.py`
- Test: `backend/tests/unit/test_router.py`

**Interfaces:**
- Produces `CrossModalResult`, `SensorRun`, `AgreementRow`, `ModalityAdvisory`, and `FusionVerdict`, all `CamelCaseModel` types.
- Registers `GraphName.CROSS_MODAL` and routes `Intent.CROSS_MODAL` to it.

- [x] Write contract and routing tests that fail because the models and graph registration do not exist.
- [x] Run the focused tests and confirm missing symbols/graph failures.
- [x] Add the Pydantic models and graph/routing vocabulary with exact frontend enums and bounds.
- [x] Run focused tests and confirm serialization validates against vendored schemas.

### Task 2: Pure optical, SAR, metadata, and fusion policy

**Files:**
- Create: `backend/app/services/optical_sar/__init__.py`
- Create: `backend/app/services/optical_sar/math/indices.py`
- Create: `backend/app/services/optical_sar/math/sar_masks.py`
- Create: `backend/app/services/optical_sar/math/fusion_rules.py`
- Create: `backend/app/services/optical_sar/metadata.py`
- Test: `backend/tests/unit/test_cross_modal_math.py`

**Interfaces:**
- Produces `optical_landcover_masks(green, nir, swir, observed) -> SensorMasks`.
- Produces `sar_landcover_masks(vv_power, vh_power, observed) -> SensorMasks`.
- Produces `build_agreement_rows(optical, radar, transform, crs) -> list[AgreementFinding]`.
- Produces `sentinel_metadata(scene_id) -> SceneMetadata` and `assess_pair(...) -> PairAssessment`.

- [x] Add hand-derived formula, threshold, quality, metadata, agreement, and refusal tests.
- [x] Run them and confirm imports fail for the absent package.
- [x] Implement only pure array/domain functions and immutable result dataclasses.
- [x] Run focused tests, refactor duplication, and keep them green.

### Task 3: Cross-modal input gate and independent sensor services

**Files:**
- Modify: `backend/app/services/pipeline/nodes/input_validation.py`
- Create: `backend/app/services/optical_sar/per_sensor_runs.py`
- Create: `backend/app/services/pipeline/nodes/cross_modal.py`
- Modify: `backend/app/services/pipeline/state.py`
- Test: `backend/tests/integration/test_cross_modal_pipeline.py`

**Interfaces:**
- Produces `validate_cross_modal_inputs(state)`, `analyse_optical(state)`, and `analyse_radar(state)` node updates with modality-prefixed state keys.
- Consumes existing spectral readers, cloud masking, SAR preprocessing, artefact storage, evidence builders, and renderers.

- [x] Add a failing synthetic-GeoTIFF test proving input order is normalized and same-modality pairs refuse.
- [x] Extend S1 validation only for `CROSS_MODAL`; preserve temporal same-modality rules.
- [x] Add failing tests proving optical and radar branches independently retain masks, confidence, quality, layers, evidence, claims, and figures.
- [x] Implement branch services and nodes without cross-reading state.
- [x] Run focused integration tests against real MinIO artefact storage.

### Task 4: Ledger, graph fan-in, answer, and persistence

**Files:**
- Create: `backend/app/services/optical_sar/agreement_ledger.py`
- Create: `backend/app/services/optical_sar/fusion.py`
- Create: `backend/app/services/pipeline/graphs/cross_modal.py`
- Modify: `backend/app/services/pipeline/nodes/provenance_logging.py`
- Modify: `backend/app/services/pipeline/nodes/answer_generation.py`
- Modify: `backend/app/services/pipeline/nodes/confidence_estimation.py`
- Test: `backend/tests/integration/test_cross_modal_pipeline.py`

**Interfaces:**
- Produces `build_cross_modal_graph()` and a checkpointed `cross_modal_result` wire dictionary.
- Persists `cross-modal-result.json` and includes it in provenance artefacts.

- [x] Add a failing graph test for parallel branch execution and ledger fan-in.
- [x] Add failing admissible/conflict/refusal tests for verdict behavior.
- [x] Implement S9 gate, fan-out/fan-in graph, ledger/result builder, and constrained answer path.
- [x] Run graph tests and inspect journal event ordering and checkpoint values.

### Task 5: CLI and contract-complete E2E fixture

**Files:**
- Modify: `backend/app/cli/analyse.py`
- Modify: `backend/app/agents/graph.py`
- Test: `backend/tests/integration/test_cross_modal_pipeline.py`
- Test: `backend/tests/contracts/test_run_journal.py`

**Interfaces:**
- `aeris analyse --scene OPTICAL --before SAR --before-sar "Use optical and SAR images together to identify built-up and water-covered regions"` runs `cross-modal` without manual graph selection.

- [x] Add failing CLI/request construction tests for both input orders.
- [x] Implement role-safe request construction and useful missing-input errors.
- [x] Run the synthetic run through journal, figure writer, checkpoint, MinIO, evidence graph, and provenance assertions.

### Task 6: Real Sentinel validation and documentation

**Files:**
- Modify: `backend/bcontext/roadmap.md`
- Modify: `backend/bcontext/memory.md`
- Output: `backend/runs/<run-id>/cross-modal-result.json`

**Interfaces:**
- Uses `aeris dataset search/fetch` for a close Mumbai Sentinel-1/Sentinel-2 clipped pair including `B02,B03,B04,B08,B11,SCL` and `vv,vh`.

- [x] Verify `aeris doctor` passes all nine checks before the real run.
- [x] Search and acquire the closest scientifically usable pair over the fixed Mumbai AOI.
- [x] Materialize SAR on the optical grid and retain the affine-grid alignment record (the runtime verifies it; it does not claim image-content registration).
- [x] Run the representative cross-modal question end to end.
- [x] Validate the result contract, evidence references, artefact existence, journal terminal event, and one corroborated plus one non-corroborated row.
- [x] Visually inspect every retained figure and reject misleading output.
- [x] Record measured results and the deferred Phase 1.10 debt in roadmap/memory.

### Task 7: Full verification

**Files:**
- Modify only files required by witnessed failures.

- [x] Run `uv run pytest tests/unit tests/contracts tests/integration -q` and record the exact result: 670 passed, 2 legacy TiTiler fixture failures as noted above.
- [x] Run `uv run ruff check app tests` and fix any errors through regression tests where behavior changes.
- [x] Run `uv run aeris doctor` and confirm 9/9 checks.
- [x] Re-run the retained real E2E command and validate its journal/result from disk.
- [x] Review `git diff HEAD --check`, `git status --short`, and the Phase 1.11 spec line by line before declaring completion.
