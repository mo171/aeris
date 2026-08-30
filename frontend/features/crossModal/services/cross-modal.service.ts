// features/crossModal/services/cross-modal.service.ts — fetching the cross-modal verdict.
//
// what  : One call: GET the two sensor runs and their agreement for an investigation.
// where : Consumed by use-cross-modal.ts. Nothing else talks to the transport.
// how   : Parsed at the boundary, like every other service. The verdict is the most consequential object
//         this application renders — it is what an operator quotes — so a malformed one must fail here
//         rather than reach a component that will draw it anyway.

import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";

import { crossModalResultSchema } from "../schemas/cross-modal.schema";
import type { CrossModalResult } from "../types/cross-modal.types";

export async function fetchCrossModalResult(
  investigationId: string,
  signal?: AbortSignal,
): Promise<CrossModalResult> {
  const response = await apiClient.get(REST_API.investigations.crossModal(investigationId), {
    signal,
  });
  return parseApiResponse(
    crossModalResultSchema,
    response.data,
    "the cross-modal endpoint",
  );
}
