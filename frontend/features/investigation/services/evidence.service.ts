// features/investigation/services/evidence.service.ts — the claim and evidence graph over the wire.
//
// what  : Fetches the evidence graph for an investigation and normalises it into the indexed shape the
//         UI reads.
// where : Called by use-evidence-graph.ts only.
// how   : The wire format is flat parallel arrays; the UI needs lookups. Normalising once here, on
//         arrival, is what makes the evidence spotlight cheap: hovering a claim resolves its supporting
//         features through two map reads instead of scanning the graph, and the spotlight fires on every
//         pointer move across the answer panel.
//
//         Layer order is preserved exactly as sent. Draw order is a backend decision — it knows which
//         product belongs on top of which — and re-sorting it here would silently change what an operator
//         sees on the scene.

import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";

import { evidenceGraphSchema } from "../schemas/evidence.schema";
import type { EvidenceGraph, NormalisedEvidenceGraph } from "../types/evidence.types";

export async function fetchEvidenceGraph(
  investigationId: string,
  signal?: AbortSignal,
): Promise<NormalisedEvidenceGraph> {
  const response = await apiClient.get(REST_API.investigations.evidence(investigationId), {
    signal,
  });
  const graph = parseApiResponse(
    evidenceGraphSchema,
    response.data,
    "the evidence graph endpoint",
  );

  return normaliseEvidenceGraph(graph);
}

export function normaliseEvidenceGraph(graph: EvidenceGraph): NormalisedEvidenceGraph {
  const claimsById: NormalisedEvidenceGraph["claimsById"] = {};
  const evidenceById: NormalisedEvidenceGraph["evidenceById"] = {};
  const layersById: NormalisedEvidenceGraph["layersById"] = {};

  for (const claim of graph.claims) {
    claimsById[claim.id] = claim;
  }
  for (const item of graph.evidence) {
    evidenceById[item.id] = item;
  }
  for (const layer of graph.layers) {
    layersById[layer.id] = layer;
  }

  return {
    claimsById,
    // The primary claim leads; the rest keep the order the backend reasoned in.
    claimOrder: [...graph.claims]
      .sort((left, right) => Number(right.isPrimary) - Number(left.isPrimary))
      .map((claim) => claim.id),
    evidenceById,
    layersById,
    layerOrder: graph.layers.map((layer) => layer.id),
  };
}

/** Resolves the stage features one claim is supported by, for the spotlight. */
export function resolveClaimFeatureIds(
  graph: NormalisedEvidenceGraph,
  claimId: string,
): string[] {
  const claim = graph.claimsById[claimId];
  if (!claim) {
    return [];
  }

  return claim.evidenceIds.flatMap((evidenceId) => graph.evidenceById[evidenceId]?.featureIds ?? []);
}
