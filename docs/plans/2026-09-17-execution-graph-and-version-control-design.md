# AERIS Execution Graph, Dependency-Aware Invalidation, and Version Control Design

> **Status:** Proposed Architecture  
> **Date:** 2026-09-17  
> **Target Systems:** Backend (`services/pipeline/`, `db/models/`, `schemas/events/`), Frontend (`features/investigation/`)  
> **Code Intelligence Anchor:** GitNexus (24.8k symbols, 50k edges, 577 execution flows)

---

## 1. Executive Summary & Architectural Invariant

The AERIS workspace operates under a core thesis:
> *"AI is operating the analytical workspace for you, and you can inspect, control, reproduce, modify, and version everything it does."*

To realize this, execution and persistence must obey a strict architectural dependency chain:
```
Step metadata contract
        ↓
Parameter resolution
        ↓
Artifact / layer identity
        ↓
Dependency-aware invalidation & checkpoint reuse
        ↓
Threshold re-run (Vertical Slice)
        ↓
Version snapshot & comparison
        ↓
Branch / restore
```

### The Critical Architectural Separation: Checkpoints vs. Versions
* **Checkpoint (Runtime State):** Answers *"Can this execution reuse what it or an upstream run already computed?"*  
  Operates on the live LangGraph execution state, thread ID, and artifact store. Granular to individual DAG nodes.
* **Version (Persistent Investigation Snapshot):** Answers *"Can I reproduce, compare, branch, and restore this investigation state later?"*  
  An immutable, named snapshot referencing stable content-addressed artifact URIs, resolved parameters, and metrics.

---

## 2. Phase 1: Contract & Metadata Hardening

### 2.1 The Unified `AnalysisStep` Wire Shape
Both frontend and backend must strictly adhere to the `AnalysisStep` wire schema across SSE frames (`trace-step`), checkpoints, and version snapshots:

```typescript
// Shared Contract (Frontend: analysis.schema.ts / Backend: schemas/events/trace.py)
interface AnalysisStep {
  id: string;                                    // "step_xxx"
  stageCode: PipelineStage;                      // "S1", "S9", "S13", etc.
  operationId: string | null;                    // "change-detection", "ndvi", null for infra
  state: "running" | "completed" | "failed" | "skipped";
  inputs: Array<{ kind: "scene" | "region" | "layer" | "figure" | "step"; id: string }>;
  parameters: Record<string, ParameterValue>;   // Resolved values the step actually used
  outputs: Array<{ kind: "layer" | "figure" | "claim" | "artefact"; id: string }>;
  model: { id: string; version: string } | null;
  rationale: string | null;                      // Why this step / this model ran
  dependsOn: string[];                           // Direct upstream step IDs in the DAG
  durationMs: number | null;
  detail: string | null;                         // e.g., "reused from run_abc" or computed summary
  artefactLayerId: string | null;
  artefactUri: string | null;
}
```

### 2.2 Parameter Overrides Wire Contract
Re-run requests pass:
```typescript
interface AnalysisRunRequest {
  query: string;
  rerunFromStepId?: string | null;
  parameterOverrides?: Record<string, Record<string, ParameterValue>> | null;
  // e.g. { "step_change_detect": { "threshold": 0.45 } }
}
```

### 2.3 Stable Artifact Identity & Provenance
Every intermediate output has a deterministic, content-addressable or run-indexed path:
* Format: `runs/{run_id}/artefacts/{stage_code}_{name}`
* Key artifacts:
  * `S9`: `registration.json` (shift, residual pixels, tolerance, status)
  * `S13`: `change-probability.tif` (raw float32 model inference tensor)
  * `S13`: `change-mask.tif` (categorical uint8 mask sliced at threshold)
  * `S15`: `vector_features.json` / vector layer (GeoJSON polygons with numeric magnitude, areaHectares, confidence)
  * `S15`: `comparison_figure.png` (tri-panel visual)

---

## 3. Phase 2: Dependency-Aware Invalidation & Checkpoint Reuse

### 3.1 The Invalidation DAG
Rather than simplistic "re-run step $N$ and skip everything before $N$", invalidation walks the dependency closure:

```
[Validate Inputs (S1)]
        ↓
[Coregister Pair (S9)]
        ↓
[Change Inference (S13)] ── produces ──► [change-probability.tif]
        ↓                                           │ (reused!)
[Threshold Slicing (S13)] ◄─────────────────────────┘
        ↓ (threshold 0.35 → 0.45)
[Localise & Measure (S15)] ── produces ──► [mask, vectors, hectares]
        ↓
[Read Figure / VLM (S14)]
        ↓
[Synthesize Answer (S16)]
        ↓
[Estimate Confidence (S18)]
        ↓
[Log Provenance (S19)]
```

When `threshold` changes from `0.35` to `0.45`:
1. **Invalidated Nodes:** `Threshold Slicing`, `localise_change` (S15), `read_figure` (S14), `generate_answer` (S16), `estimate_confidence` (S18), `log_provenance` (S19).
2. **Preserved / Reused Nodes:** `validate_inputs` (S1), `handle_clouds` (S7), `coregister_pair` (S9), and **Change Inference forward pass** (which generated `change-probability.tif`).
3. **Execution Semantics:**
   * Nodes prior to the invalidation boundary emit `TraceStep` with `state: "skipped"`, `durationMs: 0`, and `detail: "reused from run <prior_run_id>"`.
   * Reused artifacts and state keys are pulled directly from the prior run's checkpoint.
   * Only the invalidated sub-DAG executes.

---

## 4. Phase 3: The Threshold Vertical Slice

### 4.1 Backend Implementation Details
1. **`detect_change_node` (S13):**
   * Reads `state["parameter_overrides"]` for `threshold`. If absent, defaults to `CHANGE_PROBABILITY_THRESHOLD` (`0.35`).
   * If `state` already has `change_probability_path` and `change_probability_object_key` from a parent run and `threshold` is the only override:
     * Skips model inference (`detect_change()`).
     * Loads existing `probability` via `read_artefact()`.
     * Re-slices `mask = observed & (np.nan_to_num(probability, nan=0.0) >= threshold)`.
     * Writes new `change-mask.tif` for the new run.
     * Records `change_threshold = threshold`.
2. **`localise_change` (S15):**
   * Reads the newly sliced mask and measures it against the grid (`measure_mask_on_grid`).
   * Produces new vector polygon layers with updated `areaHectares` (e.g. `39.7 ha` $\to$ `41.2 ha`).
   * Emits new `LayerReadyEvent`.
   * Renders new comparison figure and emits `FigureReadyEvent`.
3. **`generate_answer` (S16):**
   * Synthesizes answer reflecting the re-measured claims and threshold.

### 4.2 Frontend Wire-Up
1. **`StepInspector.tsx`:**
   * Editing `threshold: 0.35` $\to$ `0.45` dispatches `COMMAND_IDS.investigation.rerunStep`.
2. **`use-analysis-run.ts`:**
   * Sends `rerunFromStepId` and `parameterOverrides` to backend.
   * On stream arrival:
     * Skipped steps render immediately as dimmed/reused nodes.
     * Invalidated nodes shimmer and execute live.
     * Answer panel, globe vector layers, and metrics update in real time.

---

## 5. Phase 4: Version Control Engine

Once execution semantics and artifact provenance are proven, Version Control integrates cleanly without duplicating heavy rasters:

### 5.1 Database Model (`backend/app/db/models/version.py`)
```python
class InvestigationVersion(Base, TimestampMixin):
    __tablename__ = "investigation_versions"

    id: Mapped[str] = identifier_column("ver_")
    investigation_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)  # "operator" | "agent"
    parent_version_id: Mapped[str | None] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        ForeignKey("investigation_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Full snapshot payload matching frontend versionSnapshotSchema:
    # { sceneSlots, timelinePair, steps: AnalysisStep[], resultSummary, layerIds, traceId }
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
```

### 5.2 Version Comparison (`diffVersions`)
* Compares `V1` and `V2` on:
  * Parameter diff: `step_change_detect.threshold`: `0.35` $\to$ `0.45`
  * Metric diff: `area`: `39.7 ha` $\to$ `41.2 ha`, `confidence`: `87%` $\to$ `92%`
  * Artifacts: `probability.tif` (reused, same hash/URI), `mask.tif` (new URI)
* Rendered seamlessly by [`VersionCompareSheet.tsx`](file:///c:/movin/projects/hackathon/sih/aeris/frontend/features/investigation/components/versions/VersionCompareSheet.tsx).

---

## 6. Verification & Blast Radius (GitNexus Impact)

* **`run_analysis` & `runner.py`:** Blast radius = HIGH (Direct callers: `cli/analyse.py`, `agents/tools/analysis_tools.py`). Changes must preserve backward compatibility when `parameter_overrides` is `None`.
* **`open_checkpointer`:** Blast radius = HIGH. Changes to checkpoint state schemas must maintain JSON-serializable dictionaries.
* **`pipeline_node` & `node.py`:** All stages wrap via `pipeline_node`. Adding step metadata (`operation_id`, `inputs`, `parameters`, `depends_on`) must provide graceful defaults so unaffected stages (S1–S8) require zero boilerplate churn.
