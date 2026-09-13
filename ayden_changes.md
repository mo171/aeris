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

## 7. Phase D — Version Snapshots + Compare
- **Action**: Implemented Phase D of `implementation.md` — operator-driven version snapshots with a pure client-side diff engine.
- **Files Modified/Created**:
  - `frontend/features/investigation/schemas/version.schema.ts` [NEW]: Created `investigationVersionSchema` and `versionSnapshotSchema` encapsulating `sceneSlots`, `timelinePair`, trace `steps` (the full graph with parameters), and `resultSummary`.
  - `frontend/features/investigation/types/version.types.ts` [NEW]: Extracted TypeScript types and defined diff types (`DiffSection`, `DiffRow`).
  - `frontend/features/investigation/lib/version-diff.ts` [NEW]: Implemented `diffVersions()`, a pure, side-effect-free engine that diffs two snapshots across Inputs, Workflow, Parameters, Models, Result Metrics, and Confidence. Excludes unchanged sections.
  - `frontend/mock/data/version.data.ts` [NEW]: Provided pre-seeded versions (Initial baseline, Relaxed threshold) to demonstrate the compare capabilities instantly.
  - `frontend/lib/constants/query-keys.ts`: Appended `investigations.versions()` query key factory.
  - `frontend/lib/constants/commands.ts`: Added `saveVersion`, `compareVersions`, `restoreVersion` to `COMMAND_IDS.investigation`.
  - `frontend/features/investigation/hooks/use-investigation-versions.ts` [NEW]: React Query hook for reading and mutating versions. The `saveVersion` mutation constructs a snapshot of the current workspace state (via `useInvestigationStore` and `useEvidenceGraph`) and mocks a REST save. `restoreVersion` logs the intent (in Phase D, restoring doesn't launch a run automatically).
  - `frontend/features/investigation/hooks/use-investigation-commands.ts`: Registered the three version commands and passed `versions`, `saveVersion`, `compareVersions`, `restoreVersion` dependencies through `InvestigationCommandOptions`.
  - `frontend/features/investigation/components/versions/` [NEW]: Created UI components: `SaveVersionDialog` (modal for naming saves), `VersionListPopover` (history dropdown with checkboxes for comparison), and `VersionCompareSheet` (renders the pure diff engine's output).
  - `frontend/features/investigation/components/header/InvestigationHeader.tsx`: Integrated `VersionListPopover` next to the trace ID as a compact `v{N}` badge.
  - `frontend/features/investigation/components/InvestigationScreen.tsx`: Wired up the version hook. Rendered `VersionCompareSheet` at the root and passed `versions` to the Header. Bound the compare modal's open state to the command callback.

## 8. Phase E — Project & Catalogue View
- **Project Entity**: Created `project.schema.ts` and `project.types.ts` defining `Project` with fields `name`, `areaOfInterest`, `status`, etc.
- **Service & Hook**: Created `project.service.ts` and `use-project.ts` to manage API integration and React Query hooks (`useProjects`, `useProject`). Added `/api/projects` endpoints to `rest.api.ts`.
- **Updated Schemas**: 
  - Added `projectId` to `investigationSchema` and `investigationCreateRequestSchema`. 
  - Added `projectId`, `templateVersionId`, `cadence`, and `alertRule` to `missionSchema`. 
  - Updated `globeMarkerSchema` with `projectId`.
- **UI and Navigation**: Replaced `/investigation` with `/projects` in `navigation.ts`. Added `ROUTES.PROJECTS` and `buildRoute.project` to `routes.ts`.
- **Project Index Screen (Shelf)**: Created `ProjectIndexScreen.tsx` listing all user projects.
- **Project Detail Screen**: Created `ProjectScreen.tsx` with tabs for Data (Catalogue view), Investigations, Reports, Versions, and Missions.
- **Investigation Breadcrumb**: Modified `InvestigationHeader.tsx` to include a breadcrumb indicating the parent Project (`Project › Investigation`).
- **Mission Command Left Panel**: Renamed `ActiveMissionsList` to `RecentProjectsList`. Created `AlertsStrip.tsx` to show only missions with an `alert` status. Integrated both into `DataContextPanel.tsx`.
- **Renamed Hooks & Commands**: Renamed `useSaveAsMission` to `use-monitor-this.ts` and updated to prompt for a cadence and reference the `templateVersionId`. Added the `projects.open` command to `COMMAND_IDS` in `commands.ts`.

## 9. Phase F - History & Evidence Tooling
- **Action**: Implemented Investigation History (Command Logging) from Phase F.
- **Files Modified/Created**:
  - rontend/lib/command-bus/types.ts: Added \ecordsHistory?: boolean\ flag to \CommandDefinition\.
  - rontend/lib/command-bus/registry.ts: Added a dispatch listener mechanism (\subscribeToDispatches\) to fire when commands complete.
  - rontend/features/investigation/hooks/use-investigation-commands.ts: Flagged analytical and temporal commands (e.g. \unOperation\, \sk\, \scrubTo\, \erunStep\, \saveVersion\) with \ecordsHistory: true\.
  - rontend/features/investigation/types/history.types.ts [NEW]: Created \InvestigationEvent\ interface for history logging.
  - rontend/features/investigation/hooks/use-investigation-history.ts [NEW]: Created a hook that subscribes to command dispatches, generates human-readable summaries, and stores them in session storage.
  - rontend/features/investigation/components/answerPanel/HistoryList.tsx [NEW]: Built UI component to render history events grouped by date.
  - rontend/features/investigation/components/answerPanel/AnswerPanel.tsx: Integrated \HistoryList\ to show the audit trail above previous runs.
  - rontend/features/investigation/components/InvestigationScreen.tsx: Wired up the history hook and passed it into the \AnswerPanel\.


## 10. Phase F - Layers Tab & Inputs Panel Overhaul
- **Action**: Refactored the Inputs panel to use a tabbed interface and added layer sorting.
- **Files Modified/Created**:
  - rontend/features/investigation/components/inputsPanel/LeftPanelTabs.tsx: Restructured to support three tabs (INPUTS, LAYERS, TOOLBOX).
  - rontend/features/investigation/components/inputsPanel/InputsPanel.tsx: Removed layer lists, leaving only scene inputs, acquisition history, and AOIs.
  - rontend/features/investigation/components/inputsPanel/LayersPanel.tsx [NEW]: Created to house Findings (Evidence), Masks, and Reference layers. Implemented @dnd-kit/core and @dnd-kit/sortable to allow drag-and-drop layer reordering. Added visual locks (?? for immutable model evidence, ? for editable regions) on hover.
  - rontend/features/investigation/store/investigation-store.ts: Added \layerOrder\ array and \setLayerOrder\ setter to maintain drag-and-drop state.
  - rontend/features/investigation/hooks/use-evidence-graph.ts: Updated to read \layerOrder\ from the store to ensure the scene stage respects the operator's sorting.


## 11. Phase F - Palette & Toolbox Regrouping and Evidence Tab
- **Action**: Refactored `CommandPalette` to include intent-level grouped operations and added an `EvidenceTab` to the right panel.
- **Files Modified/Created**:
  - `frontend/components/sharedUI/functionalComponent/appShell/CommandPalette.tsx`: Updated to render intent-level `ANALYSIS_OPERATIONS` alongside system commands.
  - `frontend/features/investigation/components/answerPanel/EvidenceTab.tsx` [NEW]: Built the provenance chain view per-claim (metrics, layer link, figure, model, trace step).
  - `frontend/features/investigation/components/answerPanel/RightPanelTabs.tsx` [NEW]: Extracted `AnswerPanel` to support three tabs (`ANALYSIS`, `EVIDENCE`, `CHAT`), embedding the `AnswerPanel` into Analysis and Chat modes, and the new `EvidenceTab` into Evidence mode.
  - `frontend/features/investigation/components/InvestigationScreen.tsx`: Replaced `AnswerPanel` with `RightPanelTabs`.

## 12. Final Audit Gap Fixes (Polish & Missing Implementation Details)
- **Action**: Addressed the 10 remaining gaps identified during the comprehensive audit of `implementation.md` to achieve 100% completion of the design document.
- **Files Modified/Created**:
  - `frontend/features/investigation/schemas/analysis.schema.ts`: Replaced `z.any()` fields in the `figure-ready` event with strictly typed `legend` and `renderSpec` schemas.
  - `frontend/lib/constants/commands.ts`: Added missing command IDs (`focusNode`, `moveToProject`, `missions.create`, `projects.create`).
  - `frontend/lib/constants/analysis-operations.ts`: Added the 10 missing analysis operations across the `ANALYSIS`, `TEMPORAL`, and `AI` groups (Change detection, Object detection, Land-cover segmentation, Burn severity, Trend analysis, Change explanation, Ask scene, Describe scene, Ground object, Ask region).
  - `frontend/features/investigation/hooks/use-investigation-commands.ts`: Registered the `focusNode` and `moveToProject` commands.
  - `frontend/lib/constants/basemaps.ts` [NEW]: Created the declarative basemap catalogue.
  - `frontend/features/investigation/components/inputsPanel/BasemapSwitcher.tsx` [NEW]: Created the basemap switcher UI.
  - `frontend/features/investigation/components/inputsPanel/LayersPanel.tsx`: Wired in the `BasemapSwitcher`.
  - `frontend/features/investigation/components/inputsPanel/LayerMetadataDrawer.tsx` [NEW]: Created the per-layer metadata drawer showing provenance and statistics.
  - `frontend/features/investigation/components/inputsPanel/RampOverrideSelect.tsx` [NEW]: Created the per-layer color ramp override selector.
  - `frontend/features/investigation/store/investigation-store.ts`: Added view state for the active basemap, ramp overrides, and layer annotations.
  - `frontend/features/investigation/schemas/investigation.schema.ts`: Added `events` (using the new `timelineEventAnnotationSchema`) and `layerNotes` to the investigation schema.

## 13. Phase G - Graph Layout & Visual Enhancements
- **Action**: Improved the layout, sizes, and colors of the React Flow nodes and edges in the Analysis and Version canvases.
- **Files Modified**:
  - `frontend/features/investigation/lib/workflow-graph.ts` & `frontend/features/investigation/lib/version-graph.ts`: Switched dagre layout from Left-to-Right (`LR`) to Top-to-Bottom (`TB`).
  - `frontend/components/sharedUI/workflowCanvas/nodes.tsx`: Compressed custom node sizes down to `220px-260px` to resolve DAG overlapping. Re-mapped Handles to `Position.Top` and `Position.Bottom`.
  - `frontend/components/sharedUI/workflowCanvas/WorkflowCanvas.tsx`: Injected edge styles (`stroke: "#6366f1"`) and styled the `Controls` panel to blend with the dark slate theme.

## 14. Phase G - Mock Data Pipeline Fixes
- **Action**: Repaired multiple `ReferenceError` crashes and disconnected DAG nodes in the mock trace generator.
- **Files Modified**:
  - `frontend/mock/data/investigation.data.ts`:
    - Re-mapped upstream `dependsOn` arrays from shorthand (e.g. `"S1"`) to fully qualified IDs to ensure React Flow resolves the edges.
    - Added `sceneSlots` inputs into step `S1` and updated `buildAnalysisProducts`/`buildTraceSteps` signatures to pipe `sceneSlots` into the generator, fixing floating scene nodes and a `ReferenceError`.
    - Corrected the `id` of the `ndvi` layer output in step `S12`.
    - Bumped `SESSION_STORAGE_VERSION` to `8` to clear stale, invalid mock cache on client reload.
