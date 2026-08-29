// features/investigation/services/catalogue.service.ts — asking the archive what exists over an area.
//
// what  : Issues the temporal catalogue query and validates the acquisitions, coverage holes and
//         recommended pair that come back.
// where : Called only by use-catalogue-search.ts.
// how   : A POST rather than a GET despite being a read. The query carries a bounding box, a modality
//         list and a window — a structured body, not a handful of scalars — and putting geometry in a
//         query string means encoding decisions, length limits and an unreadable URL in every log.
//
//         The response is validated before it reaches a hook for the same reason every other response is:
//         an acquisition missing its tile template or its ground sample distance would scrub to a blank
//         scene or quote a wrong area, and both failures are far cheaper to diagnose here than there.

import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";

import { catalogueSearchResponseSchema } from "../schemas/catalogue.schema";
import type { CatalogueSearchResponse, TemporalQuery } from "../types/catalogue.types";

export async function searchCatalogue(
  query: TemporalQuery,
  signal?: AbortSignal,
): Promise<CatalogueSearchResponse> {
  const response = await apiClient.post(REST_API.catalogue.search, query, { signal });

  return parseApiResponse(
    catalogueSearchResponseSchema,
    response.data,
    "the catalogue search endpoint",
  );
}
