// features/missionCommand/services/model-registry.service.ts — health of the specialist model fleet.
//
// what  : Fetches the current status of every specialist model AERIS can route a question to.
// where : Called by use-model-status.ts, rendered by the ModelStatusStrip in the data panel.
// how   : A small, near-static payload. The caching policy that stops it being refetched constantly lives
//         in the hook, not here — services stay stateless and cache-unaware so they can be reused by any
//         caller with any caching requirement.

import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";

import { modelStatusCollectionSchema } from "../schemas/model.schema";
import type { ModelStatusCollection } from "../types/model.types";

export async function fetchModelStatus(signal?: AbortSignal): Promise<ModelStatusCollection> {
  const response = await apiClient.get(REST_API.models.status, { signal });

  return parseApiResponse(modelStatusCollectionSchema, response.data, "the model registry");
}
