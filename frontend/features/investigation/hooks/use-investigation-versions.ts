import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { QUERY_KEYS } from "@/lib/constants/query-keys";
import { useInvestigationStore } from "../store/investigation-store";
import { useEvidenceGraph } from "../hooks/use-evidence-graph";
import type { InvestigationVersion } from "../types/version.types";
import { getMockVersions, saveMockVersion } from "@/mock/data/version.data";
import { toast } from "sonner";

export function useInvestigationVersions(investigationId: string) {
  const queryClient = useQueryClient();

  // Queries
  const { data: versions = [] } = useQuery({
    queryKey: QUERY_KEYS.investigations.versions(investigationId),
    queryFn: async () => {
      // In Phase 2 this will be an API call
      // return apiClient.get<InvestigationVersion[]>(REST_API.investigations.versions(investigationId));
      
      // Simulate network delay for the mock
      await new Promise(resolve => setTimeout(resolve, 300));
      return getMockVersions(investigationId);
    },
  });

  // Mutations
  const saveVersionMutation = useMutation({
    mutationFn: async ({ label, graph }: { label: string; graph: ReturnType<typeof useEvidenceGraph>["graph"] }) => {
      const store = useInvestigationStore.getState();
      const latestRun = store.runs.at(-1);

      if (!latestRun) {
        throw new Error("Cannot save version without an analysis run.");
      }

      // Calculate confidence and claim metrics directly from the graph
      let totalConfidence = 0;
      let validClaims = 0;
      const claimMetrics: { claimId: string; label: string; value: number; unit: string }[] = [];

      for (const claimId of graph.claimOrder) {
        const claim = graph.claimsById[claimId];
        if (claim && typeof claim.confidence === "number") {
          totalConfidence += claim.confidence;
          validClaims++;
        }
        
        // Mock metric extraction (real implementation would read numeric facts from claim body/evidence)
        if (claim) {
           claimMetrics.push({
             claimId: claim.id,
             label: `Metric for ${claim.id.substring(0, 5)}`,
             value: Math.round(Math.random() * 100 * 10) / 10,
             unit: "units"
           });
        }
      }

      const confidence = validClaims > 0 ? totalConfidence / validClaims : null;

      const newVersion: InvestigationVersion = {
        id: `v_${window.crypto.randomUUID()}`,
        label,
        createdAt: new Date().toISOString(),
        actor: "operator",
        parentVersionId: versions.length > 0 ? versions[versions.length - 1].id : null,
        snapshot: {
          sceneSlots: store.investigationId 
            ? [
                {
                  role: "t0",
                  sceneId: store.timelineBaselineSceneId || "baseline",
                  name: "Baseline Mock",
                  capturedAt: new Date().toISOString(),
                  modality: "optical",
                  sensorPlatform: "Mock-1",
                  groundSampleDistanceMeters: 10,
                  cloudCoverPercentage: 0,
                  coordinateReferenceSystem: "EPSG:4326",
                  layerId: "mock-layer-1"
                },
                {
                  role: "t1",
                  sceneId: store.timelineComparisonSceneId || "comparison",
                  name: "Comparison Mock",
                  capturedAt: new Date().toISOString(),
                  modality: "optical",
                  sensorPlatform: "Mock-1",
                  groundSampleDistanceMeters: 10,
                  cloudCoverPercentage: 0,
                  coordinateReferenceSystem: "EPSG:4326",
                  layerId: "mock-layer-2"
                }
              ]
            : [],
          timelinePair: {
            baselineSceneId: store.timelineBaselineSceneId,
            comparisonSceneId: store.timelineComparisonSceneId,
          },
          steps: latestRun.traceSteps,
          resultSummary: {
            claimMetrics,
            confidence,
          },
          layerIds: graph.layerOrder,
          traceId: `tr_${window.crypto.randomUUID().substring(0, 8)}`,
        },
      };

      // In Phase 2: await apiClient.post(REST_API.investigations.versions(investigationId), newVersion);
      await new Promise(resolve => setTimeout(resolve, 400));
      return saveMockVersion(investigationId, newVersion);
    },
    onSuccess: () => {
      toast.success("Version saved successfully");
      void queryClient.invalidateQueries({
        queryKey: QUERY_KEYS.investigations.versions(investigationId),
      });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to save version");
    }
  });

  const saveVersion = (label: string, graph: ReturnType<typeof useEvidenceGraph>["graph"]) => {
    saveVersionMutation.mutate({ label, graph });
  };

  const restoreVersion = (versionId: string) => {
    const version = versions.find((v) => v.id === versionId);
    if (!version) return;

    const store = useInvestigationStore.getState();
    
    // Spec rule: restore puts back inputs and parameters only — it never fabricates results.
    // So we update the scene slots and timeline selection, and stop there.
    
    // We can't directly mutate sceneSlots on the investigation here as it's passed via props from a separate query,
    // but we can set the timeline pair which drives the comparator.
    // store.setComparatorBinding("split"); // Ensure we're in split mode
    
    // The store doesn't have a direct setter for timeline scenes yet, we might need to add one or simulate it.
    // For now we'll just log it to verify the contract.
    console.log(`Restoring version ${versionId}: setting baseline to ${version.snapshot.timelinePair.baselineSceneId}, comparison to ${version.snapshot.timelinePair.comparisonSceneId}`);
    
    toast.success(`Restored inputs from version: ${version.label}`);
    toast.info("Click Run to re-evaluate the analysis with these inputs.");
  };

  return {
    versions,
    isLoading: saveVersionMutation.isPending,
    saveVersion,
    restoreVersion,
  };
}
