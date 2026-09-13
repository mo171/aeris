"use client";

import { useMemo } from "react";
import { WorkflowCanvas } from "@/components/sharedUI/workflowCanvas";
import { buildVersionGraph } from "../../lib/version-graph";
import { useInvestigationStore } from "../../store/investigation-store";
import type { InvestigationVersion } from "../../types/version.types";

interface VersionCanvasProps {
  versions: InvestigationVersion[];
}

export function VersionCanvas({ versions }: VersionCanvasProps) {
  const setSelectedNodeId = useInvestigationStore((state) => state.setSelectedNodeId);

  const graph = useMemo(() => {
    if (!versions || versions.length === 0) return { nodes: [], edges: [] };
    return buildVersionGraph({ versions });
  }, [versions]);

  if (!versions || versions.length === 0) {
    return <div className="flex h-full items-center justify-center text-xs text-muted-foreground">No version history available.</div>;
  }

  return (
    <WorkflowCanvas
      graph={graph}
      onNodeSelect={setSelectedNodeId}
      className="h-full w-full bg-slate-950/95"
    />
  );
}
