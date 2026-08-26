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
  missions: {
    list: `${API_VERSION_PREFIX}/missions`,
    detail: (missionId: string) => `${API_VERSION_PREFIX}/missions/${missionId}`,
  },
  globe: {
    markers: `${API_VERSION_PREFIX}/globe/markers`,
    satelliteTracks: `${API_VERSION_PREFIX}/globe/satellite-tracks`,
  },
  models: {
    status: `${API_VERSION_PREFIX}/models/status`,
  },
  assistant: {
    suggestions: `${API_VERSION_PREFIX}/assistant/suggestions`,
    history: `${API_VERSION_PREFIX}/assistant/history`,
    /** Server-sent event endpoint carrying answer tokens and execution-trace steps. */
    stream: `${API_VERSION_PREFIX}/assistant/stream`,
  },
} as const;
