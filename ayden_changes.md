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
