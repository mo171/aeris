# Frontend Requirements (Missing in Backend)

The frontend requires the following functionality from the backend, which is currently missing or not fully implemented as we transition to Phase 2:

## 1. HTTP API and SSE Streaming (Phase 2 Serving)
The backend is currently a CLI application (Phase 1). The frontend requires the actual REST API routes and SSE endpoints to be implemented:
- `GET /api/v1/imagery`, `GET /api/v1/imagery/{sceneId}`, `POST /api/v1/catalogue/search`
- `POST /api/v1/investigations`, `GET/PATCH /api/v1/investigations/{id}`
- **SSE Stream**: `POST /api/v1/investigations/{id}/runs` and `POST /api/v1/assistant/stream`
- `GET /api/v1/investigations/{id}/evidence`, `/plan`, `/report`
- `GET /api/v1/globe/markers`, `/globe/satellite-tracks`

## 2. Event Streaming Details
- **`layer-ready`**: Must be its own SSE event, separate from `trace-step`. The viewer needs to draw a layer the moment it exists.
- **`figure-ready`**: Endpoints needed for fetching figure metadata (`GET /api/v1/investigations/{id}/figures`) and the actual image bytes (`GET /api/v1/figures/{figureId}`).
- **Artefact URIs**: Every trace step needs to carry its artefact URI where the stage produced one.
- **Evidence properties**: Every evidence polygon must carry `areaHectares`, `magnitude`, `confidence`, `modelId`, `modelVersion`, `traceStepId`.

## 3. Cross-Modal Analysis Parameters
- `GET /api/v1/investigations/:id/cross-modal` needs to accept `baseline` and `comparison` scene IDs as query parameters, rather than being keyed only on the investigation ID. This is required so moving the timeline recomputes the advisory.

## 4. Analysis Step & Trace Overrides
- **Plan steps and `trace-step`**: Need the full `AnalysisStep` shape: `operationId`, `parameters`, `inputs[]`, `outputs[]`, `model`, `rationale`, and `dependsOn[]`.
- `POST /investigations/:id/runs`: Must accept `parameterOverrides` and `rerunFromStepId`. Upstream steps must come back as `state: "skipped"` with `detail` naming the run they were reused from.

## 5. Investigation History & Versioning
- `GET/POST /api/v1/investigations/:id/versions`
- `GET/POST /api/v1/investigations/:id/history` (append-only `{ at, actor, commandId, params, summary }`)
- Project-based endpoints (`/projects`, etc.) and `projectId` required on investigations and missions.
