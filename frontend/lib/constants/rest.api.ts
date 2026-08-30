// lib/constants/rest.api.ts — THE endpoint registry. Every backend URL in the application lives here.
//
// what  : Maps each backend capability to its path. Collection paths are constants; resource paths are
//         builder functions so an id is never string-concatenated at a call site.
// where : Imported only by feature service files (features/&ast;/services/&ast;.service.ts). Components and hooks
//         must never see a URL.
// how   : Paths are relative; lib/axios/axios-client.ts supplies the base URL from env. When the backend
//         renames an endpoint this file is the single edit.

const API_VERSION_PREFIX = "/api/v1";

export const REST_API = {
  imagery: {
    list: `${API_VERSION_PREFIX}/imagery`,
    detail: (sceneId: string) => `${API_VERSION_PREFIX}/imagery/${sceneId}`,
    /** Signed-URL handshake — files upload straight to cloud storage, never through the backend. */
    createUploadTicket: `${API_VERSION_PREFIX}/imagery/upload-ticket`,
    confirmUpload: (sceneId: string) => `${API_VERSION_PREFIX}/imagery/${sceneId}/confirm`,
  },
  catalogue: {
    /**
     * The temporal archive query: an area, a window and a quality ceiling in, the acquisitions that
     * exist plus the pair the catalogue would choose out. POST because the body carries geometry.
     */
    search: `${API_VERSION_PREFIX}/catalogue/search`,
  },
  missions: {
    list: `${API_VERSION_PREFIX}/missions`,
    detail: (missionId: string) => `${API_VERSION_PREFIX}/missions/${missionId}`,
    /** Promotes a completed investigation into a saved, re-runnable mission over the same area. */
    create: `${API_VERSION_PREFIX}/missions`,
  },
  globe: {
    markers: `${API_VERSION_PREFIX}/globe/markers`,
    satelliteTracks: `${API_VERSION_PREFIX}/globe/satellite-tracks`,
  },
  models: {
    status: `${API_VERSION_PREFIX}/models/status`,
  },
  investigations: {
    create: `${API_VERSION_PREFIX}/investigations`,
    detail: (investigationId: string) => `${API_VERSION_PREFIX}/investigations/${investigationId}`,
    attachScene: (investigationId: string) =>
      `${API_VERSION_PREFIX}/investigations/${investigationId}/scenes`,
    /** Server-sent events: trace steps, ready layers, claims and answer tokens for one analysis run. */
    runs: (investigationId: string) => `${API_VERSION_PREFIX}/investigations/${investigationId}/runs`,
    evidence: (investigationId: string) =>
      `${API_VERSION_PREFIX}/investigations/${investigationId}/evidence`,
    /** The autonomous plan, returned before execution so the operator can edit it. */
    plan: (investigationId: string) => `${API_VERSION_PREFIX}/investigations/${investigationId}/plan`,
    report: (investigationId: string) =>
      `${API_VERSION_PREFIX}/investigations/${investigationId}/report`,
    /**
     * The cross-modal verdict: two independent per-sensor runs and their agreement.
     *
     * A separate endpoint from `runs` rather than a mode of it, because the shape is genuinely different
     * — two analyses and a comparison, not one analysis. Folding it into the run stream would force every
     * temporal consumer to handle a dual-provenance claim it will never receive.
     */
    crossModal: (investigationId: string) =>
      `${API_VERSION_PREFIX}/investigations/${investigationId}/cross-modal`,
  },
  evidence: {
    /**
     * The claim corpus across every investigation.
     *
     * Separate from investigations.evidence, which returns one investigation's graph. This one answers
     * questions that span them — every claim a model version produced, everything resting on a scene later
     * found faulty — which is exactly what a single investigation's graph cannot express.
     */
    claims: `${API_VERSION_PREFIX}/evidence/claims`,
  },
  regions: {
    suggestions: `${API_VERSION_PREFIX}/regions/suggestions`,
  },
  assistant: {
    suggestions: `${API_VERSION_PREFIX}/assistant/suggestions`,
    history: `${API_VERSION_PREFIX}/assistant/history`,
    /** Server-sent event endpoint carrying answer tokens and execution-trace steps. */
    stream: `${API_VERSION_PREFIX}/assistant/stream`,
  },
} as const;
