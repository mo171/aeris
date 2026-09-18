# Backend Haves (Missing in Frontend)

The backend has implemented several features and capabilities that it expects the frontend to handle, but the frontend currently lacks the required implementation:

## 1. UI Command Dispatch (`ui-command`)
- The backend emits `ui-command` events (e.g., `investigation.focusEvidence`, `setSplitPosition`) to let the agent drive the interface.
- **Frontend Requirement**: The frontend must parse these events from the stream and dispatch them through its existing command bus (`lib/command-bus`), ensuring proper schema validation before execution.

## 2. Speech Streaming (`speech`)
- The backend generates spoken lines separated from the written claim text, emitted as `speech` events.
- **Frontend Requirement**: The frontend must handle playback of these audio events. It must support barge-in (cancels the utterance synthesis without stopping the run) and properly distinguish between `grounded`, `provisional`, `progress`, and `refusal` kinds.

## 3. Rendered Figures (`figure-ready`)
- The backend renders deterministic, self-contained figures (e.g., index maps with legends, SAR backscatter, change comparison) and emits `figure-ready` events.
- **Frontend Requirement**: The frontend needs surfaces to display these. Specifically, detached pop-out windows (e.g., `/scene/[sceneId]`) and a dedicated route under `app/(reference)/` to host the figures without booting a WebGL globe. It must also handle the `isPrimary` property (one figure per run marked to show unprompted).

## 4. Geometry Schema Upgrades
- **Polygon Holes**: The backend mask vectorization preserves holes in regions. The frontend's `featureGeometrySchema` currently only supports a single ring, causing regions with holes to render incorrectly as their outline alone.
- **Frontend Requirement**: Update the Zod schema and Cesium rendering to support polygons with holes.

## 5. Scene Classification Model ID
- **13th Model ID**: The backend uses the product's own scene classification (e.g., SenCor2 for Sentinel-2 L2A) for the S7 cloud mask. 
- **Frontend Requirement**: `layerProvenanceSchema.modelId` and `lib/constants/models.ts` need to be updated to include a 13th model ID for native product scene classification (e.g., `s2cloudless`).
