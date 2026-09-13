import dagre from "dagre";
import type { WorkflowNode, WorkflowEdge, WorkflowGraph } from "./workflow-graph";
import type { InvestigationVersion } from "../types/version.types";

interface BuildVersionGraphParams {
  versions: InvestigationVersion[];
}

/**
 * Constructs a DAG topology for the @xyflow/react canvas using dagre for rigid layout.
 * Visualizes the version history as a Git-like branch graph.
 * The graph flows top-to-bottom or left-to-right.
 */
export function buildVersionGraph({ versions }: BuildVersionGraphParams): WorkflowGraph {
  const g = new dagre.graphlib.Graph();
  // Using TB for consistency with the analysis trace.
  g.setGraph({ rankdir: "TB", ranksep: 100, nodesep: 60 });
  g.setDefaultEdgeLabel(() => ({}));

  const nodes: WorkflowNode[] = [];
  const edges: WorkflowEdge[] = [];

  const addNode = (id: string, data: any, width: number = 320, height: number = 100) => {
    if (nodes.some((n) => n.id === id)) return;
    nodes.push({ id, kind: "version", data });
    g.setNode(id, { width, height });
  };

  const addEdge = (source: string, target: string) => {
    const id = `edge-${source}-to-${target}`;
    if (edges.some((e) => e.id === id)) return;
    edges.push({ id, source, target });
    g.setEdge(source, target);
  };

  // Add all versions as nodes
  versions.forEach((version) => {
    addNode(version.id, version);
  });

  // Add edges based on parentVersionId
  versions.forEach((version) => {
    if (version.parentVersionId) {
      // In a git graph, time flows outward from the parent to the child
      addEdge(version.parentVersionId, version.id);
    }
  });

  // Run dagre layout
  dagre.layout(g);

  // Apply positions
  const positionedNodes = nodes.map((node) => {
    const dagreNode = g.node(node.id);
    return {
      ...node,
      position: {
        // Shift by half width/height because dagre positions by center, xyflow by top-left
        x: dagreNode.x - dagreNode.width / 2,
        y: dagreNode.y - dagreNode.height / 2,
      },
    };
  });

  return {
    nodes: positionedNodes,
    edges,
  };
}
