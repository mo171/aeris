// mock/transport/routes.ts — maps mock HTTP requests to generated data.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : The route table the mock axios adapter dispatches through, one entry per real endpoint.
// where : Used only by mock/transport/mock-adapter.ts.
// how   : Paths mirror lib/constants/rest.api.ts exactly, including query-parameter names and the
//         cursor-page envelope, so services and hooks exercise the real request/response shape in Phase 1.
//         When the live backend arrives nothing upstream changes — this table is simply deleted.

import type { ImageryScene } from "@/features/missionCommand/types/imagery.types";
import type { ConfidenceBandId } from "@/lib/constants/evidence-audit";
import { REST_API } from "@/lib/constants/rest.api";

import { MOCK_ASSISTANT_SUGGESTIONS } from "../data/assistant.data";
import { getMockCrossModal } from "../data/cross-modal.data";
import { selectMockAuditedClaimPage } from "../data/evidence-audit.data";
import {
  attachMockScene,
  createMockInvestigation,
  getMockEvidenceGraph,
  getMockInvestigation,
  getMockPlan,
  getMockRegionSuggestions,
  getMockSceneInspection,
  listMockInvestigations,
  saveMockCameraBookmark,
  searchMockCatalogue,
} from "../data/investigation.data";
import { insertUploadedScene, selectImageryPage } from "../data/imagery.data";
import {
  createMockMission,
  getGlobeMarkers,
  getSatelliteTracks,
  selectMissionPage,
} from "../data/mission.data";
import { MOCK_MODEL_STATUSES } from "../data/model.data";

export interface MockRequestContext {
  pathname: string;
  query: Record<string, string | undefined>;
  body: unknown;
  pathParameters: string[];
}

export interface MockResponse {
  status: number;
  data: unknown;
}

export interface MockRoute {
  method: "GET" | "POST" | "PUT";
  match: (pathname: string) => string[] | null;
  handle: (context: MockRequestContext) => MockResponse;
}

const MOCK_STORAGE_PATH_PREFIX = "/mock-object-storage/";

function exactPath(path: string): (pathname: string) => string[] | null {
  return (pathname) => (pathname === path ? [] : null);
}

function patternPath(pattern: RegExp): (pathname: string) => string[] | null {
  return (pathname) => {
    const match = pattern.exec(pathname);
    return match ? match.slice(1) : null;
  };
}

function parsePositiveInteger(value: string | undefined, fallback: number): number {
  const parsed = value ? Number.parseInt(value, 10) : Number.NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export const MOCK_ROUTES: readonly MockRoute[] = [
  {
    method: "GET",
    match: exactPath(REST_API.imagery.list),
    handle: ({ query }) => ({
      status: 200,
      data: selectImageryPage({
        cursor: query.cursor ?? null,
        limit: parsePositiveInteger(query.limit, 25),
        search: query.search ?? null,
      }),
    }),
  },
  {
    method: "POST",
    match: exactPath(REST_API.imagery.createUploadTicket),
    handle: ({ body }) => {
      const request = body as { fileName?: string } | undefined;
      const sceneId = `scn_upl_${Date.now().toString(36)}`;

      return {
        status: 201,
        data: {
          sceneId,
          uploadUrl: `https://mock-object-storage.aeris.invalid${MOCK_STORAGE_PATH_PREFIX}${sceneId}`,
          expiresAt: new Date(Date.now() + 15 * 60_000).toISOString(),
          requiredHeaders: { "x-aeris-mock-upload": request?.fileName ?? "scene" },
        },
      };
    },
  },
  {
    method: "PUT",
    match: patternPath(new RegExp(`^${MOCK_STORAGE_PATH_PREFIX}(.+)$`)),
    handle: () => ({ status: 200, data: null }),
  },
  {
    method: "POST",
    match: patternPath(/^\/api\/v1\/imagery\/([^/]+)\/confirm$/),
    handle: ({ pathParameters }) => {
      const sceneId = pathParameters[0];
      insertUploadedScene(buildUploadedScene(sceneId));
      return { status: 202, data: null };
    },
  },
  {
    method: "GET",
    match: exactPath(REST_API.missions.list),
    handle: ({ query }) => ({
      status: 200,
      data: selectMissionPage(query.cursor ?? null, parsePositiveInteger(query.limit, 20)),
    }),
  },
  {
    method: "POST",
    match: exactPath(REST_API.missions.create),
    handle: ({ body }) => ({
      status: 201,
      data: createMockMission(body as Parameters<typeof createMockMission>[0]),
    }),
  },
  {
    method: "GET",
    match: exactPath(REST_API.evidence.claims),
    handle: ({ query }) => ({
      status: 200,
      data: selectMockAuditedClaimPage({
        search: query.search ?? null,
        modelId: query.modelId ?? null,
        band: (query.band as ConfidenceBandId | undefined) ?? null,
        cursor: query.cursor ?? null,
        limit: parsePositiveInteger(query.limit, 25),
      }),
    }),
  },
  {
    method: "GET",
    match: exactPath(REST_API.globe.markers),
    handle: () => ({
      status: 200,
      data: { markers: getGlobeMarkers(), generatedAt: new Date().toISOString() },
    }),
  },
  {
    method: "GET",
    match: exactPath(REST_API.globe.satelliteTracks),
    handle: () => ({
      status: 200,
      data: { tracks: getSatelliteTracks(), generatedAt: new Date().toISOString() },
    }),
  },
  {
    method: "GET",
    match: exactPath(REST_API.models.status),
    handle: () => ({
      status: 200,
      data: { models: MOCK_MODEL_STATUSES, checkedAt: new Date().toISOString() },
    }),
  },
  {
    method: "GET",
    match: exactPath(REST_API.assistant.suggestions),
    handle: () => ({ status: 200, data: { suggestions: MOCK_ASSISTANT_SUGGESTIONS } }),
  },

  // ── Investigations ─────────────────────────────────────────────────────────────────────────────
  {
    method: "POST",
    match: exactPath(REST_API.investigations.create),
    handle: ({ body }) => {
      const request = body as {
        sceneIds?: string[];
        seedQuery?: string | null;
        missionId?: string | null;
      };
      const investigation = createMockInvestigation(
        request?.sceneIds ?? [],
        request?.seedQuery ?? null,
        request?.missionId ?? null,
      );

      return {
        status: 201,
        data: {
          investigationId: investigation.id,
          areaOfInterestName: investigation.areaOfInterestName,
          areaOfInterest: investigation.areaOfInterest,
          cameraTarget: {
            latitude: investigation.centroid.latitude,
            longitude: investigation.centroid.longitude,
            altitudeMeters: 9_000,
          },
        },
      };
    },
  },
  {
    method: "GET",
    match: exactPath(REST_API.investigations.create),
    handle: () => ({ status: 200, data: { items: listMockInvestigations() } }),
  },
  {
    method: "GET",
    match: patternPath(/^\/api\/v1\/investigations\/([^/]+)\/evidence$/),
    handle: ({ pathParameters }) => {
      const graph = getMockEvidenceGraph(pathParameters[0]);
      return graph
        ? { status: 200, data: graph }
        : { status: 404, data: { message: "Investigation not found" } };
    },
  },
  {
    method: "GET",
    match: patternPath(/^\/api\/v1\/investigations\/([^/]+)\/cross-modal$/),
    handle: ({ pathParameters }) => {
      const result = getMockCrossModal(pathParameters[0]);
      return result
        ? { status: 200, data: result }
        : { status: 404, data: { message: "Investigation not found" } };
    },
  },
  {
    method: "GET",
    match: patternPath(/^\/api\/v1\/investigations\/([^/]+)\/plan$/),
    handle: ({ pathParameters }) => {
      const plan = getMockPlan(pathParameters[0]);
      return plan
        ? { status: 200, data: plan }
        : { status: 404, data: { message: "Investigation not found" } };
    },
  },
  {
    method: "GET",
    match: patternPath(/^\/api\/v1\/investigations\/([^/]+)$/),
    handle: ({ pathParameters }) => {
      const investigation = getMockInvestigation(pathParameters[0]);
      return investigation
        ? { status: 200, data: investigation }
        : { status: 404, data: { message: "Investigation not found" } };
    },
  },
  {
    // The camera bookmark. Persisted for real so a reload genuinely reopens the saved framing — a mock
    // that acknowledged the save without storing it would make the feature look broken on refresh.
    method: "POST",
    match: patternPath(/^\/api\/v1\/investigations\/([^/]+)$/),
    handle: ({ pathParameters, body }) => {
      const request = body as { cameraBookmark?: unknown };
      return request?.cameraBookmark
        ? { status: 204, data: saveMockCameraBookmark(pathParameters[0], request.cameraBookmark) }
        : { status: 204, data: null };
    },
  },
  {
    method: "POST",
    match: patternPath(/^\/api\/v1\/investigations\/([^/]+)\/scenes$/),
    handle: ({ pathParameters, body }) => {
      const request = body as { sceneId?: string; role?: "t0" | "t1" | "sar" };
      const updated =
        request?.sceneId && request?.role
          ? attachMockScene(pathParameters[0], request.sceneId, request.role)
          : null;

      return updated
        ? { status: 200, data: updated }
        : { status: 404, data: { message: "Investigation or scene not found" } };
    },
  },
  {
    method: "GET",
    match: patternPath(/^\/api\/v1\/imagery\/([^/]+)$/),
    handle: ({ pathParameters }) => {
      const inspection = getMockSceneInspection(pathParameters[0]);
      return inspection
        ? { status: 200, data: inspection }
        : { status: 404, data: { message: "Scene not found" } };
    },
  },
  {
    method: "POST",
    match: exactPath(REST_API.catalogue.search),
    handle: ({ body }) => {
      const query = body as Parameters<typeof searchMockCatalogue>[0] | undefined;
      const result = query?.areaOfInterest ? searchMockCatalogue(query) : null;

      return result
        ? { status: 200, data: result }
        : { status: 404, data: { message: "No archive coverage for this area" } };
    },
  },
  {
    method: "GET",
    match: exactPath(REST_API.regions.suggestions),
    handle: ({ query }) => ({
      status: 200,
      data: { suggestions: getMockRegionSuggestions(query.investigationId ?? "") },
    }),
  },
];

/** Builds the scene record the backend would create once an upload finishes preprocessing. */
function buildUploadedScene(sceneId: string): ImageryScene {
  const now = new Date().toISOString();

  return {
    id: sceneId,
    name: `Operator upload · ${now.slice(0, 10)}`,
    capturedAt: now,
    ingestedAt: now,
    modality: "optical",
    sensorPlatform: "Operator upload",
    bandCount: 4,
    groundSampleDistanceMeters: 3,
    cloudCoverPercentage: 0,
    coordinateReferenceSystem: "EPSG:4326",
    boundingBox: { west: 72.7, south: 18.9, east: 73.0, north: 19.2 },
    centroid: { latitude: 19.05, longitude: 72.85 },
    fileSizeBytes: 268_435_456,
    processingState: "processing",
    temporalRole: "single",
    thumbnailUrl: null,
  };
}
