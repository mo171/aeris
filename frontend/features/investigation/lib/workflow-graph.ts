import dagre from "dagre";
import type { WorkflowNodeKind } from "@/lib/constants/workflow";
import type { AnalysisTraceStep } from "@/features/investigation/types/analysis.types";
import type { EvidenceLayer } from "@/features/investigation/types/layer.types";
import type { Claim } from "@/features/investigation/types/evidence.types";
import type { InvestigationSceneSlot } from "@/features/investigation/types/investigation.types";

export interface WorkflowNode {
  id: string;
  kind: WorkflowNodeKind;
  /** The specific entity data for this node. Cast based on kind in the UI. */
  data: any;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  /** Indicates if this edge was generated from an upstream dependancy during a rerun */
  isReused?: boolean;
}

export interface WorkflowGraph {
  nodes: (WorkflowNode & { position: { x: number; y: number } })[];
  edges: WorkflowEdge[];
}

interface BuildWorkflowGraphParams {
  steps: AnalysisTraceStep[];
  layersById: Record<string, EvidenceLayer>;
  claimsById: Record<string, Claim>;
  sceneSlots: readonly InvestigationSceneSlot[];
}

/**
 * Constructs a DAG topology for the @xyflow/react canvas using dagre for rigid layout.
 * The graph flows left-to-right (LR).
 */
export function buildWorkflowGraph({
  steps,
  layersById,
  claimsById,
  sceneSlots,
}: BuildWorkflowGraphParams): WorkflowGraph {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", ranksep: 80, nodesep: 50 });
  g.setDefaultEdgeLabel(() => ({}));

  const nodes: WorkflowNode[] = [];
  const edges: WorkflowEdge[] = [];

  const addNode = (id: string, kind: WorkflowNodeKind, data: any, width: number = 220, height: number = 80) => {
    // Prevent duplicate nodes if referenced multiple times
    if (nodes.some((n) => n.id === id)) return;
    nodes.push({ id, kind, data });
    g.setNode(id, { width, height });
  };

  const addEdge = (source: string, target: string) => {
    const id = `edge-${source}-to-${target}`;
    if (edges.some((e) => e.id === id)) return;
    edges.push({ id, source, target });
    g.setEdge(source, target);
  };

  // 1. Add Scene Inputs
  sceneSlots.forEach((slot) => {
    addNode(slot.sceneId, "scene", slot);
  });

  // 2. Add Operation Steps and their connections
  steps.forEach((step) => {
    addNode(step.id, "operation", step);

    // Inputs -> Step
    step.inputs.forEach((input: any) => {
      // Ensure the input node exists if it's a scene or layer not explicitly in the inputs list
      if (input.kind === "scene") {
        const scene = sceneSlots.find((s) => s.sceneId === input.id);
        if (scene) addNode(scene.sceneId, "scene", scene);
      } else if (input.kind === "layer") {
        const layer = layersById[input.id];
        if (layer) addNode(layer.id, "layer", layer);
      }
      
      // We don't always add regions/figures here unless they are in a Map, 
      // but they are valid inputs. If they don't exist in dagre they might cause edge issues.
      // Assuming upstream nodes are added by their respective trace steps or maps.
      addEdge(input.id, step.id);
    });

    // Step -> Outputs
    step.outputs.forEach((output: any) => {
      if (output.kind === "layer") {
        const layer = layersById[output.id];
        if (layer) addNode(layer.id, "layer", layer);
      } else if (output.kind === "claim") {
        const claim = claimsById[output.id];
        if (claim) addNode(claim.id, "claim", claim);
      }
      addEdge(step.id, output.id);
    });

    // Step -> Step dependencies (ordering / sequence execution)
    // S12 dependsOn S10, for example. 
    step.dependsOn.forEach((upstreamId: string) => {
      addEdge(upstreamId, step.id);
    });
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
