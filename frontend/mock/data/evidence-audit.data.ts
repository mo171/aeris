// mock/data/evidence-audit.data.ts — the claim corpus, assembled across every generated investigation.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : Flattens every generated investigation's claims into audit rows, applies the surface's filters,
//         and pages the result.
// where : Served by the evidence claims route.
// how   : Reads the SAME generated investigations the workspace reads, rather than generating a second
//         corpus. If these diverged, an operator could audit a claim that does not exist in the
//         investigation the row links to — which is the one failure an audit surface must not have.
//
//         Filtering happens here rather than in the browser because that is where the real backend will do
//         it, and Phase 1 exists to exercise the real request shape. The list is rebuilt per request: it
//         grows only as an operator creates investigations, and caching it would strand claims from runs
//         that completed after the first call.

import type { AuditedClaim } from "@/features/evidenceAudit/types/evidence-audit.types";
import type { ModelId } from "@/lib/constants/models";
import {
  isConfidenceInBand,
  type ConfidenceBandId,
} from "@/lib/constants/evidence-audit";

import { getMockAnalysisProducts, listMockInvestigations } from "./investigation.data";

interface AuditQuery {
  search: string | null;
  modelId: string | null;
  band: ConfidenceBandId | null;
  cursor: string | null;
  limit: number;
}

export function selectMockAuditedClaimPage(query: AuditQuery) {
  const matching = collectAuditedClaims().filter((claim) => matches(claim, query));

  const parsedCursor = query.cursor ? Number.parseInt(query.cursor, 10) : 0;
  const startIndex = Number.isFinite(parsedCursor) && parsedCursor > 0 ? parsedCursor : 0;
  const endIndex = Math.min(startIndex + query.limit, matching.length);

  return {
    items: matching.slice(startIndex, endIndex),
    nextCursor: endIndex < matching.length ? String(endIndex) : null,
    totalCount: matching.length,
  };
}

/**
 * Every claim from every investigation, newest investigation first.
 *
 * Ordered by the backend rather than the client, matching the rule the mission list already follows —
 * sorting on arrival would make rows jump between pages during a scroll.
 */
function collectAuditedClaims(): AuditedClaim[] {
  const rows: AuditedClaim[] = [];

  for (const investigation of listMockInvestigations()) {
    const products = getMockAnalysisProducts(investigation.id);
    if (!products) {
      continue;
    }

    const evidenceById = new Map(products.evidence.map((item) => [item.id, item]));

    for (const claim of products.claims) {
      const sourceSceneIds = new Set<string>();
      for (const evidenceId of claim.evidenceIds) {
        for (const sceneId of evidenceById.get(evidenceId)?.sourceSceneIds ?? []) {
          sourceSceneIds.add(sceneId);
        }
      }

      rows.push({
        claimId: claim.id,
        runId: claim.runId,
        text: claim.text,
        kind: claim.kind,
        confidence: claim.confidence,
        modelId: claim.modelId as ModelId,
        modelVersion: claim.modelVersion,
        traceStepId: claim.traceStepId,
        investigationId: investigation.id,
        investigationName: investigation.name,
        areaOfInterestName: investigation.areaOfInterestName,
        evidenceCount: claim.evidenceIds.length,
        sourceSceneIds: [...sourceSceneIds],
        producedAt: investigation.updatedAt,
      });
    }
  }

  return rows;
}

function matches(claim: AuditedClaim, query: AuditQuery): boolean {
  if (query.modelId && claim.modelId !== query.modelId) {
    return false;
  }

  if (query.band && !isConfidenceInBand(claim.confidence, query.band)) {
    return false;
  }

  if (query.search) {
    // The same haystack the surface's placeholder promises: wording, area and scene id.
    const haystack = [
      claim.text,
      claim.investigationName,
      claim.areaOfInterestName,
      ...claim.sourceSceneIds,
    ]
      .join(" ")
      .toLowerCase();

    if (!haystack.includes(query.search.toLowerCase())) {
      return false;
    }
  }

  return true;
}
