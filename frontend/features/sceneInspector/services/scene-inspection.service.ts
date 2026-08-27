// features/sceneInspector/services/scene-inspection.service.ts — fetching one scene for the inspector.
//
// what  : Loads the acquisition, its quicklook and its context by scene id.
// where : Called by the scene inspector window only.
// how   : One request, keyed by scene id, because the inspector is a separate browser window with its own
//         JavaScript context. It cannot reach into the workspace's caches, and building it to depend on
//         a parent window would mean the URL stops working when opened on its own — which defeats the
//         point of a detachable window.

import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";

import { sceneInspectionSchema } from "../schemas/scene-inspection.schema";
import type { SceneInspection } from "../types/scene-inspection.types";

export async function fetchSceneInspection(
  sceneId: string,
  signal?: AbortSignal,
): Promise<SceneInspection> {
  const response = await apiClient.get(REST_API.imagery.detail(sceneId), { signal });

  return parseApiResponse(sceneInspectionSchema, response.data, "the scene detail endpoint");
}
