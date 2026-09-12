# Frontend Changes

## 1. Polygon Holes Support
- **File**: `frontend/features/investigation/schemas/layer.schema.ts`
- **Change**: Updated the `featureGeometrySchema` to include an optional `holes` property for the `polygon` type, defined as `z.array(z.array(geoPointSchema).min(3)).optional()`. This allows the rendering of polygons with interior rings.

## 2. Sen2Cor Scene Classification Layer (SCL) Model
Added a 13th Model ID representing Sentinel-2's native Scene Classification Layer (SCL). This ensures cloud masks are correctly attributable without falsely claiming `s2cloudless`.
- **Files Modified**: 
  - `frontend/lib/constants/models.ts`: Appended `"sen2cor-scl"` to `MODEL_IDS` and `MODEL_ORDER`. Added a `SPECIALIST_MODELS` entry detailing its capability as a preprocessing stage.
  - `frontend/mock/data/model.data.ts`: Mocked an online status for `"sen2cor-scl"` to support observability UI.
  - `backend/app/constants/model_ids.py`: Sync'd the `sen2cor-scl` string ID to the backend constants `StrEnum` to keep the fleet vocabularies consistent.

## 3. Contract Schemas Reconciled
- **Action**: Ran `pnpm run contracts:export` within the `frontend` directory.
- **Outcome**: Synced the recent frontend Zod schemas (ui-command, speech, figure-ready) with the backend contract map, automatically propagating updates to `backend/bcontext/contracts/schemas.json`.

## 4. Phase A Workspace Contract Updates
- **Action**: Modified multiple files to establish the new data models for the Workspace Canvas (Phase A of `implementation.md`).
- **Files Modified**:
  - `frontend/lib/constants/parameters.ts` [NEW]: Created schema definitions for `ParameterKind` and `ParameterValue` to drive dynamic UI form generation for analysis tools.
  - `frontend/lib/constants/analysis-operations.ts`: Enhanced `AnalysisOperation` with `parameters`, `defaultParameters`, `keywords`, and `group`. Added `"ANALYSIS"`, `"TEMPORAL"`, `"MULTIMODAL"`, and `"MEASURE"` operation groups.
  - `frontend/features/investigation/schemas/analysis.schema.ts`: Redefined `analysisStepSchema` to introduce DAG attributes (`inputs`, `outputs`, `dependsOn`, `parameters`).
  - `frontend/mock/streams/analysis-stream.ts` & `frontend/mock/data/investigation.data.ts`: Updated mock generators to construct and stream realistic DAG dependencies, providing inputs, outputs, and model parameters in the trace. Bumped `SESSION_STORAGE_VERSION`.

## 5. Phase B Analysis Canvas
- **Action**: Implemented the Analysis Canvas and Node Inspector (Phase B of `implementation.md`) using `@xyflow/react` and `dagre`.
- **Files Modified/Created**:
  - `frontend/package.json`: Installed `@xyflow/react`, `dagre`, and `@types/dagre`.
  - `frontend/lib/constants/workflow.ts` [NEW]: Created node kind enumerations (`scene`, `region`, `operation`, `layer`, `figure`, `claim`).
  - `frontend/components/sharedUI/workflowCanvas/` [NEW]: Created a reusable ReactFlow adapter featuring `WorkflowCanvas.tsx` and rigid custom nodes.
  - `frontend/features/investigation/lib/workflow-graph.ts` [NEW]: Added `buildWorkflowGraph()` function to compute the deterministic DAG layout with dagre.
  - `frontend/features/investigation/store/investigation-store.ts`: Introduced `traceView` ("rows" vs "canvas") and `selectedNodeId` state.
  - `frontend/features/investigation/components/tracePanel/AnalysisCanvas.tsx` [NEW]: Wired the workflow graph generator into the canvas adapter.
  - `frontend/features/investigation/components/tracePanel/ExecutionSpine.tsx`: Embedded the `AnalysisCanvas` allowing the operator to toggle between traditional rows and the new interactive canvas topology.
  - `frontend/features/investigation/components/inspector/StepInspector.tsx` [NEW]: Built the node inspector panel displaying runtime status, IO dependencies, and active parameters for selected pipeline steps. Embedded into `InvestigationScreen.tsx`.

## 6. Phase C — Edit Parameter → Re-run → Downstream Re-executes
- **Action**: Implemented Phase C of `implementation.md` — parameter editing in the `StepInspector` dispatches a new run from the selected step, with upstream steps reused and downstream steps re-executed.
- **Files Modified/Created**:
  - `frontend/lib/constants/commands.ts`: Added `rerunStep`, `toggleCanvas`, and `selectNode` to `COMMAND_IDS.investigation`.
  - `frontend/features/investigation/hooks/use-analysis-run.ts`: Defined `AskOptions` interface with `parameterOverrides` and `rerunFromStepId`; extended `ask()` to accept these; added `rerunStep(stepId, overrides)` convenience wrapper; wired both new fields into `streamAnalysisRun()` request payload.
  - `frontend/features/investigation/hooks/use-investigation-commands.ts`: Added `rerunStep` to `InvestigationCommandOptions`; registered `COMMAND_IDS.investigation.rerunStep` command with Zod params schema.
  - `frontend/features/investigation/components/InvestigationScreen.tsx`: Destructured `rerunStep` from `useAnalysisRun`; passed it into `useInvestigationCommands`.
  - `frontend/features/investigation/components/inspector/StepInspector.tsx`: Rebuilt with edit state (`isEditing`, `draftParams`); parameter inputs that coerce to the original value type; **Re-run from here** button (enabled when edits differ); **Cancel** to revert; runtime state rendered with visual distinctions (skipped = strikethrough, completed = teal, failed = destructive).
  - `frontend/components/sharedUI/workflowCanvas/nodes.tsx`: `OperationNode` now applies per-state CSS classes (`completed` → teal border, `running` → pulsing primary, `skipped` → muted + strikethrough, `failed` → destructive). All node types refined with improved typography and layout.
  - `frontend/mock/streams/analysis-stream.ts`: Re-run simulation — when `rerunFromStepId` is present, steps before the cut point emit as `state: "skipped"` with a detail string; steps at and after the cut point re-execute with `parameterOverrides` merged into their `parameters` field.

