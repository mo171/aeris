"use client";

import { useMemo } from "react";
import { WorkflowCanvas } from "@/components/sharedUI/workflowCanvas";
import { buildWorkflowGraph } from "../../lib/workflow-graph";
import { useInvestigationStore } from "../../store/investigation-store";
import type { AnalysisRun } from "../../types/analysis.types";
import type { InvestigationSceneSlot } from "../../types/investigation.types";

interface AnalysisCanvasProps {
  run: AnalysisRun | null;
  // In a real app we'd fetch these from the query cache using the investigationId.
  // For Phase B mock integration, we can assume the parent supplies them or we fetch them here.
  // For now, I will define them as props.
  layersById: Record<string, any>;
  claimsById: Record<string, any>;
  sceneSlots: readonly InvestigationSceneSlot[];
}

export function AnalysisCanvas({ run, layersById, claimsById, sceneSlots }: AnalysisCanvasProps) {
  const setSelectedNodeId = useInvestigationStore((state) => state.setSelectedNodeId);

  const graph = useMemo(() => {
    if (!run) return { nodes: [], edges: [] };
    return buildWorkflowGraph({
      steps: run.traceSteps,
      layersById,
      claimsById,
      sceneSlots,
    });
  }, [run, layersById, claimsById, sceneSlots]);

  if (!run) {
    return <div className="flex h-full items-center justify-center text-xs text-muted-foreground">No analysis trace available.</div>;
  }

  return (
    <WorkflowCanvas
      graph={graph}
      onNodeSelect={setSelectedNodeId}
      className="h-full w-full bg-slate-950/95"
    />
  );
}
