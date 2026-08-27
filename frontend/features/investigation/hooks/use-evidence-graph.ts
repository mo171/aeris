// features/investigation/hooks/use-evidence-graph.ts — the claim and evidence graph for the open investigation.
//
// what  : Reads the normalised evidence graph from the query cache and exposes the layer list the stage
//         renders, with the operator overrides already applied.
// where : Consumed by the layer stack, the answer panel and the scene stage binding.
// how   : The graph is server state and stays in the query cache; the analysis stream mutates that cache
//         incrementally as layers and claims arrive rather than triggering a refetch, which is the rule
//         for realtime data in this codebase.
//
//         Overrides are applied here, at read time, rather than written back into the cached descriptors.
//         Keeping the backend truth and the operator preference separate means a refetch never silently
//         re-shows a layer someone hid, and clearing overrides restores exactly what the backend intended.
//
//         Solo is resolved last so it wins over per-layer visibility, which is what an operator expects
//         from a solo control.

"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { QUERY_KEYS } from "@/lib/constants/query-keys";

import { fetchEvidenceGraph, resolveClaimFeatureIds } from "../services/evidence.service";
import { useInvestigationStore } from "../store/investigation-store";
import type { Claim, NormalisedEvidenceGraph } from "../types/evidence.types";
import type { EvidenceLayer } from "../types/layer.types";

const EMPTY_GRAPH: NormalisedEvidenceGraph = {
  claimsById: {},
  claimOrder: [],
  evidenceById: {},
  layersById: {},
  layerOrder: [],
};

interface UseEvidenceGraphResult {
  graph: NormalisedEvidenceGraph;
  /** Layers in draw order, with visibility, opacity and solo already resolved. */
  layers: EvidenceLayer[];
  claims: Claim[];
  primaryClaim: Claim | null;
  isLoading: boolean;
  /** The stage features supporting a claim, for the spotlight. */
  featureIdsForClaim: (claimId: string) => string[];
}

export function useEvidenceGraph(investigationId: string): UseEvidenceGraphResult {
  const visibilityOverrides = useInvestigationStore((state) => state.layerVisibilityOverrides);
  const opacityOverrides = useInvestigationStore((state) => state.layerOpacityOverrides);
  const soloLayerId = useInvestigationStore((state) => state.soloLayerId);

  const { data, isLoading } = useQuery({
    queryKey: QUERY_KEYS.investigations.evidence(investigationId),
    queryFn: ({ signal }) => fetchEvidenceGraph(investigationId, signal),
  });

  const graph = data ?? EMPTY_GRAPH;

  const layers = useMemo(
    () =>
      graph.layerOrder.map((layerId) => {
        const layer = graph.layersById[layerId];
        const isVisible = visibilityOverrides[layerId] ?? layer.isVisible;

        return {
          ...layer,
          isVisible: soloLayerId === null ? isVisible : soloLayerId === layerId,
          opacity: opacityOverrides[layerId] ?? layer.opacity,
        };
      }),
    [graph, opacityOverrides, soloLayerId, visibilityOverrides],
  );

  const claims = useMemo(
    () => graph.claimOrder.map((claimId) => graph.claimsById[claimId]),
    [graph],
  );

  return {
    graph,
    layers,
    claims,
    primaryClaim: claims.find((claim) => claim.isPrimary) ?? claims[0] ?? null,
    isLoading,
    featureIdsForClaim: (claimId: string) => resolveClaimFeatureIds(graph, claimId),
  };
}
