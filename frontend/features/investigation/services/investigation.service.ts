// features/investigation/services/investigation.service.ts — the investigation record over the wire.
//
// what  : Creates an investigation, fetches one, lists them, and persists the operator camera bookmark.
// where : Called by use-investigation.ts and by the investigation.create command. Nothing else issues
//         these requests.
// how   : `createInvestigation` is on the critical path of the descent. Mission Command dispatches it,
//         starts the camera flying on the response, and routes immediately without waiting for the
//         flight — so this call has to be quick and small. Everything expensive belongs in the analysis
//         run that follows.
//
//         Every response is validated before it reaches a hook. Scene metadata is the evidence trail for
//         every downstream number, so a record missing its CRS or its ground sample distance must fail
//         loudly here rather than silently produce a wrong hectare figure six screens later.

import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";

import {
  investigationCreateResponseSchema,
  investigationListSchema,
  investigationSchema,
} from "../schemas/investigation.schema";
import type {
  CameraBookmark,
  Investigation,
  SceneRole,
  InvestigationCreateRequest,
  InvestigationCreateResponse,
  InvestigationSummary,
} from "../types/investigation.types";

export async function createInvestigation(
  request: InvestigationCreateRequest,
  signal?: AbortSignal,
): Promise<InvestigationCreateResponse> {
  const response = await apiClient.post(REST_API.investigations.create, request, { signal });

  return parseApiResponse(
    investigationCreateResponseSchema,
    response.data,
    "the investigation create endpoint",
  );
}

export async function fetchInvestigation(
  investigationId: string,
  signal?: AbortSignal,
): Promise<Investigation> {
  const response = await apiClient.get(REST_API.investigations.detail(investigationId), { signal });

  return parseApiResponse(investigationSchema, response.data, "the investigation endpoint");
}

export async function fetchInvestigations(signal?: AbortSignal): Promise<InvestigationSummary[]> {
  const response = await apiClient.get(REST_API.investigations.create, { signal });
  const list = parseApiResponse(
    investigationListSchema,
    response.data,
    "the investigation list endpoint",
  );

  return list.items;
}

/**
 * Binds an acquisition into one of the comparison roles.
 *
 * The server returns the updated investigation rather than an acknowledgement, so the caller can replace
 * its cached record in one step. Re-fetching after a role change would leave a window where the layer
 * stack and the comparator disagree about which scene is T1.
 */
export async function attachScene(
  investigationId: string,
  sceneId: string,
  role: SceneRole,
): Promise<Investigation> {
  const response = await apiClient.post(REST_API.investigations.attachScene(investigationId), {
    sceneId,
    role,
  });

  return parseApiResponse(investigationSchema, response.data, "the attach scene endpoint");
}

/**
 * Persists the camera pose so a shared URL reopens the exact view the operator left.
 * Called on an explicit save, never on camera movement: the camera changes every frame and writing that
 * to the backend would be thousands of requests per session.
 */
export async function saveCameraBookmark(
  investigationId: string,
  cameraBookmark: CameraBookmark,
): Promise<void> {
  await apiClient.post(REST_API.investigations.detail(investigationId), { cameraBookmark });
}
