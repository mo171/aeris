import { Handle, Position } from "@xyflow/react";
import type { WorkflowNode } from "@/features/investigation/lib/workflow-graph";
import { cn } from "@/lib/utils";

interface BaseNodeProps {
  data: WorkflowNode["data"];
  selected?: boolean;
}

export function SceneNode({ data, selected }: BaseNodeProps) {
  return (
    <div
      className={cn(
        "px-4 py-2 shadow-sm rounded-md border bg-background text-left",
        selected && "border-primary ring-1 ring-primary",
      )}
    >
      <Handle type="source" position={Position.Right} className="!bg-muted-foreground" />
      <div className="font-semibold text-xs text-muted-foreground uppercase tracking-wider">Scene</div>
      <div className="text-[10px] text-foreground font-mono truncate max-w-[160px]">{data.sceneId ?? data.id}</div>
    </div>
  );
}

const operationStateStyle: Record<string, string> = {
  completed: "border-aeris-teal/60 bg-aeris-teal/5",
  running:   "border-primary animate-pulse bg-primary/5",
  skipped:   "border-muted bg-muted/20 opacity-50",
  failed:    "border-destructive/60 bg-destructive/5",
  pending:   "border-border bg-background",
};

export function OperationNode({ data, selected }: BaseNodeProps) {
  const state: string = data.state ?? "pending";
  const stateClass = operationStateStyle[state] ?? operationStateStyle.pending;

  return (
    <div
      className={cn(
        "px-4 py-2 shadow-sm rounded-md border text-left",
        stateClass,
        selected && "ring-2 ring-primary",
      )}
    >
      <Handle type="target" position={Position.Left} className="!bg-muted-foreground" />
      <Handle type="source" position={Position.Right} className="!bg-muted-foreground" />
      <div className="font-semibold text-xs text-primary truncate max-w-[160px]">
        {data.operationId || data.stageCode}
      </div>
      <div className="text-[10px] text-muted-foreground mt-0.5">
        {state === "skipped" ? (
          <span className="line-through">reused</span>
        ) : (
          state
        )}
        {data.durationMs != null && state === "completed" && (
          <span className="ml-1 text-aeris-teal">{data.durationMs}ms</span>
        )}
      </div>
    </div>
  );
}

export function LayerNode({ data, selected }: BaseNodeProps) {
  return (
    <div
      className={cn(
        "px-4 py-2 shadow-sm rounded-md border bg-background text-left",
        selected && "border-primary ring-1 ring-primary",
      )}
    >
      <Handle type="target" position={Position.Left} className="!bg-muted-foreground" />
      <Handle type="source" position={Position.Right} className="!bg-muted-foreground" />
      <div className="font-semibold text-xs text-secondary-foreground truncate max-w-[160px]">
        {data.title ?? data.id}
      </div>
      <div className="text-[10px] text-muted-foreground">Layer</div>
    </div>
  );
}

export function ClaimNode({ data, selected }: BaseNodeProps) {
  return (
    <div
      className={cn(
        "px-4 py-2 shadow-sm rounded-md border bg-background text-left",
        selected && "border-primary ring-1 ring-primary",
      )}
    >
      <Handle type="target" position={Position.Left} className="!bg-muted-foreground" />
      <div className="font-semibold text-xs text-amber-500">Claim</div>
      <div className="text-[10px] text-muted-foreground font-mono truncate max-w-[160px]">{data.id}</div>
    </div>
  );
}

export const nodeTypes = {
  scene:     SceneNode,
  operation: OperationNode,
  layer:     LayerNode,
  claim:     ClaimNode,
  figure:    LayerNode,
  region:    SceneNode,
} as const;
