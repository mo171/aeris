"use client";

import { useMemo, useCallback } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  type Node as XYNode,
  type Edge as XYEdge,
  type NodeTypes,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { WorkflowGraph } from "@/features/investigation/lib/workflow-graph";
import { nodeTypes } from "./nodes";

interface WorkflowCanvasProps {
  graph: WorkflowGraph;
  onNodeSelect?: (nodeId: string | null) => void;
  className?: string;
}

export function WorkflowCanvas({ graph, onNodeSelect, className }: WorkflowCanvasProps) {
  // Convert our abstracted graph to xyflow types
  const initialNodes: XYNode[] = useMemo(() => {
    return graph.nodes.map((node) => ({
      id: node.id,
      type: node.kind,
      position: node.position,
      data: node.data,
    }));
  }, [graph.nodes]);

  const initialEdges: XYEdge[] = useMemo(() => {
    return graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      animated: edge.isReused === false,
      style: {
        stroke: "#6366f1", // indigo-500
        strokeWidth: 2,
        ...(edge.isReused ? { strokeDasharray: "4 4", opacity: 0.5 } : {}),
      },
    }));
  }, [graph.edges]);

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  const onSelectionChange = useCallback(
    ({ nodes }: OnSelectionChangeParams) => {
      if (!onNodeSelect) return;
      const selected = nodes.find((n) => n.selected);
      onNodeSelect(selected ? selected.id : null);
    },
    [onNodeSelect]
  );

  return (
    <div className={className}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes as unknown as NodeTypes} // cast required due to dynamic Node props
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onSelectionChange={onSelectionChange}
        fitView
        nodesDraggable={false} // Graph is rigidly defined by dagre
        nodesConnectable={false} // Operator cannot hand-wire dependencies
        elementsSelectable={true}
        minZoom={0.2}
        maxZoom={2}
      >
        <Background color="#334155" variant="dots" gap={24} size={2} className="opacity-40" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
