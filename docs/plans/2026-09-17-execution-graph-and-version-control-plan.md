# Execution Graph, Dependency Invalidation & Version Control Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement full trace step graph metadata, dependency-aware checkpoint invalidation, the threshold re-run vertical slice (0.35 → 0.45 without re-inferencing), and the immutable investigation version snapshot engine.

**Architecture:** Contract-first execution semantics: lock down `AnalysisStep` wire shapes across frontend and backend; decorate pipeline stages to emit graph dependencies and resolved parameters; enable smart checkpoint reuse that invalidates only downstream DAG nodes on parameter changes; and anchor version control on immutable snapshots of graph checkpoints.

**Tech Stack:** Python 3.12 (FastAPI, LangGraph, Pydantic, GeoAlchemy2/PostGIS, Rasterio), TypeScript (Next.js 15, React 19, @xyflow/react, TanStack Query, Zod, Tailwind CSS).

---

### Task 1: Contract Hardening — `AnalysisTraceStep` and Wire Models

**Files:**
- Modify: `backend/app/schemas/events/trace.py`
- Modify: `frontend/features/investigation/schemas/analysis.schema.ts`
- Test: `backend/tests/contracts/test_stream_events.py`

**Step 1: Write the failing contract test**
Add a test in `backend/tests/contracts/test_stream_events.py` asserting that `AnalysisTraceStep` serializes and validates with `operation_id`, `inputs`, `parameters`, `outputs`, `depends_on`, and `rationale`.

**Step 2: Run test to verify it fails**
Run: `pytest backend/tests/contracts/test_stream_events.py -k test_analysis_trace_step_full_shape -v`
Expected: FAIL due to missing fields or schema mismatch.

**Step 3: Update `AnalysisTraceStep` in `trace.py` and `analysis.schema.ts`**
Add fields:
- `operation_id: str | None = None`
- `inputs: list[TraceNodeRef] = field(default_factory=list)`
- `parameters: dict[str, Any] = field(default_factory=dict)`
- `outputs: list[TraceNodeRef] = field(default_factory=list)`
- `depends_on: list[str] = field(default_factory=list)`
- `rationale: str | None = None`

**Step 4: Run test to verify it passes**
Run: `pytest backend/tests/contracts/test_stream_events.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add backend/app/schemas/events/trace.py frontend/features/investigation/schemas/analysis.schema.ts backend/tests/contracts/test_stream_events.py
git commit -m "contract: harden AnalysisStep shape with inputs, parameters, and dependsOn"
```

---

### Task 2: Pipeline Stage Graph Metadata in `@pipeline_node`

**Files:**
- Modify: `backend/app/services/pipeline/node.py`
- Test: `backend/tests/unit/pipeline/test_pipeline_node.py`

**Step 1: Write the failing test**
Create/update `test_pipeline_node.py` to verify that `@pipeline_node` emits `operation_id`, `parameters`, `inputs`, `outputs`, and `depends_on` in `TraceStepEvent`.

**Step 2: Run test to verify it fails**
Run: `pytest backend/tests/unit/pipeline/test_pipeline_node.py -v`
Expected: FAIL.

**Step 3: Implement parameter and graph context in `node.py`**
- Extend `_StepContext` and `@pipeline_node` to accept `operation_id`, `inputs_fn` or `inputs`, and `depends_on`.
- In `_emit_step`, populate `operation_id`, `inputs`, `parameters` (from `state["resolved_parameters"]` or `state["parameter_overrides"]`), `depends_on`, and `rationale`.

**Step 4: Run test to verify it passes**
Run: `pytest backend/tests/unit/pipeline/test_pipeline_node.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add backend/app/services/pipeline/node.py backend/tests/unit/pipeline/test_pipeline_node.py
git commit -m "feat(pipeline): emit graph metadata and resolved parameters from pipeline_node"
```

---

### Task 3: Dependency-Aware Invalidation & Checkpoint Reuse Engine

**Files:**
- Modify: `backend/app/services/pipeline/checkpointer.py`
- Modify: `backend/app/services/pipeline/runner.py`
- Create: `backend/app/services/pipeline/invalidation.py`
- Test: `backend/tests/unit/pipeline/test_invalidation.py`

**Step 1: Write the failing invalidation test**
Write tests for `compute_invalidated_nodes(graph_name, changed_parameters)` in `test_invalidation.py`:
- Test 1: `changed_parameters = {"threshold": 0.45}` in temporal graph $\implies$ invalidates `["detect_change", "localise_change", "read_figure", "answer_question", "generate_answer", "estimate_confidence", "log_provenance"]`. Preserves `["validate_inputs", "handle_clouds", "coregister_pair"]` and inference probability tensor.
- Test 2: `changed_parameters = {"model": "different"}` $\implies$ invalidates from inference downwards.

**Step 2: Run test to verify it fails**
Run: `pytest backend/tests/unit/pipeline/test_invalidation.py -v`
Expected: FAIL.

**Step 3: Implement DAG invalidation logic in `invalidation.py`**
Define stage dependency trees and compute the downstream transitive closure of invalidated nodes. In `runner.py`:
- When `rerun_from_step_id` or `parameter_overrides` is provided, restore state for non-invalidated nodes.
- Emit `TraceStep` with `state: "skipped"`, `detail: f"reused from run {prior_run_id}"` for skipped nodes.

**Step 4: Run test to verify it passes**
Run: `pytest backend/tests/unit/pipeline/test_invalidation.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add backend/app/services/pipeline/invalidation.py backend/app/services/pipeline/runner.py backend/app/services/pipeline/checkpointer.py backend/tests/unit/pipeline/test_invalidation.py
git commit -m "feat(pipeline): implement dependency-aware DAG invalidation and checkpoint reuse"
```

---

### Task 4: The Threshold Vertical Slice in `detect_change_node` & `localise_change`

**Files:**
- Modify: `backend/app/services/pipeline/nodes/change_detection.py`
- Test: `backend/tests/integration/test_threshold_rerun.py`

**Step 1: Write the failing integration test**
In `test_threshold_rerun.py`:
- Run baseline temporal change detection at threshold `0.35`. Record run outcome `O1` (area $A_1$, mask URI $M_1$, probability URI $P_1$).
- Trigger re-run with `parameter_overrides = {"threshold": 0.45}`.
- Assert:
  1. Inference was skipped (`detect_change` model lease was not called).
  2. `probability_path` was reused ($P_2 == P_1$).
  3. New mask was cut ($M_2 \neq M_1$).
  4. Area $A_2$ reflects the stricter threshold ($A_2 < A_1$).
  5. S1, S7, S9 were reported as `skipped`.

**Step 2: Run test to verify it fails**
Run: `pytest backend/tests/integration/test_threshold_rerun.py -v`
Expected: FAIL.

**Step 3: Implement threshold override handling and mask re-slicing in `change_detection.py`**
- In `detect_change_node`: check `state.get("parameter_overrides")` for `threshold`. If probability is in state/disk from a parent run, bypass model inference and re-slice mask.
- In `localise_change`: measure new mask, produce new layer/figure/claims, emit `LayerReadyEvent` with updated `areaHectares`.

**Step 4: Run test to verify it passes**
Run: `pytest backend/tests/integration/test_threshold_rerun.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add backend/app/services/pipeline/nodes/change_detection.py backend/tests/integration/test_threshold_rerun.py
git commit -m "feat(change-detection): implement parameter-driven threshold re-slicing and layer re-emission"
```

---

### Task 5: Frontend Step Inspector & Re-run Wire-Up

**Files:**
- Modify: `frontend/features/investigation/hooks/use-analysis-run.ts`
- Modify: `frontend/features/investigation/components/inspector/StepInspector.tsx`
- Modify: `frontend/features/investigation/components/tracePanel/AnalysisCanvas.tsx`
- Test: `frontend/lib/streaming/ui-command-bridge.test.ts`

**Step 1: Write/update frontend test**
Assert that `rerunStep` dispatches the expected request payload and handles `state: "skipped"` steps properly in the canvas state.

**Step 2: Run test to verify**
Run: `pnpm test` in `frontend/`.

**Step 3: Wire frontend UI**
- Ensure `StepInspector.tsx` passes the changed threshold to `rerunStep`.
- Update `AnalysisCanvas.tsx` and `TraceStepNode.tsx` to display skipped/reused nodes with distinct muted visual styling and tooltips.

**Step 4: Build and test frontend**
Run: `pnpm run build` in `frontend/`.
Expected: 0 errors.

**Step 5: Commit**
```bash
git add frontend/features/investigation/
git commit -m "feat(frontend): connect step inspector threshold re-run to live stream"
```

---

### Task 6: Investigation Version Snapshot Engine & Storage

**Files:**
- Modify: `backend/app/db/models/history.py` (or create `version.py`)
- Create: `backend/app/services/versions/manager.py`
- Create: `backend/app/schemas/versions.py`
- Test: `backend/tests/unit/test_version_service.py`

**Step 1: Write the failing unit test**
Test saving an investigation version snapshot, listing versions, and retrieving a version with its snapshot.

**Step 2: Run test to verify it fails**
Run: `pytest backend/tests/unit/test_version_service.py -v`
Expected: FAIL.

**Step 3: Implement `InvestigationVersion` model and `VersionManager`**
- Snapshot schema matches `versionSnapshotSchema` from frontend.
- Provide `save_version(investigation_id, label, actor, snapshot, parent_version_id)`.
- Provide `get_version`, `list_versions`.

**Step 4: Run test to verify it passes**
Run: `pytest backend/tests/unit/test_version_service.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add backend/app/db/models/ backend/app/services/versions/ backend/tests/unit/test_version_service.py
git commit -m "feat(versions): implement investigation version snapshot manager"
```
