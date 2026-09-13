// lib/constants/workflow.ts — Analysis Canvas Node Types
//
// what  : The closed set of entity kinds that can appear on the DAG canvas.
// where : Used by features/investigation/lib/workflow-graph.ts to type nodes.
// how   : Matches the `kind` union on `nodeRefSchema` from analysis.schema.ts, but specifically
//         for frontend rendering in the @xyflow/react canvas.

export const WORKFLOW_NODE_KINDS = [
  "scene",
  "region",
  "operation", // Called 'step' on the wire, but rendered as the operation it performs
  "layer",
  "figure",
  "claim",
  "version",
] as const;

export type WorkflowNodeKind = (typeof WORKFLOW_NODE_KINDS)[number];
