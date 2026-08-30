// features/evidenceAudit/services/evidence-audit.service.ts — reading the claim corpus.
//
// what  : Fetches a filtered, cursor-paginated page of claims across every investigation.
// where : Called by use-evidence-audit.ts. Nothing else talks to this endpoint.
// how   : Filtering happens on the BACKEND, not here. The corpus grows with every run an operator ever
//         made, so fetching it whole to filter in the browser would work in review and fail in service —
//         the same reason the imagery catalogue is cursor-paginated rather than sorted client-side.

import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";

import { auditedClaimPageSchema } from "../schemas/evidence-audit.schema";
import type { AuditedClaimPage, EvidenceAuditQuery } from "../types/evidence-audit.types";

export const AUDIT_PAGE_SIZE = 25;

export async function fetchAuditedClaimPage(
  query: EvidenceAuditQuery,
  signal?: AbortSignal,
): Promise<AuditedClaimPage> {
  const response = await apiClient.get(REST_API.evidence.claims, {
    signal,
    params: {
      search: query.search || undefined,
      modelId: query.modelId ?? undefined,
      band: query.band && query.band !== "all" ? query.band : undefined,
      cursor: query.cursor ?? undefined,
      limit: query.limit ?? AUDIT_PAGE_SIZE,
    },
  });

  return parseApiResponse(auditedClaimPageSchema, response.data, "the claim corpus");
}
