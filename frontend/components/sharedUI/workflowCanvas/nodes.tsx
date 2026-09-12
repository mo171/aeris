import { Handle, Position } from "@xyflow/react";
import type { WorkflowNode } from "@/features/investigation/lib/workflow-graph";
import { cn } from "@/lib/utils";

interface BaseNodeProps {
  data: WorkflowNode["data"];
  selected?: boolean;
}

export function SceneNode({ data, selected }: BaseNodeProps) {
  return (
    <div className={cn("px-4 py-2 shadow-sm rounded-md border bg-background", selected && "border-primary")}>
      <Handle type="source" position={Position.Right} />
      <div className="font-semibold text-xs">Scene</div>
      <div className="text-[10px] text-muted-foreground">{data.sceneId}</div>
    </div>
  );
}

export function OperationNode({ data, selected }: BaseNodeProps) {
  return (
    <div className={cn("px-4 py-2 shadow-sm rounded-md border bg-background", selected && "border-primary")}>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div className="font-semibold text-xs text-primary">{data.operationId || data.stageCode}</div>
      <div className="text-[10px] text-muted-foreground">{data.state}</div>
    </div>
  );
}

export function LayerNode({ data, selected }: BaseNodeProps) {
  return (
    <div className={cn("px-4 py-2 shadow-sm rounded-md border bg-background", selected && "border-primary")}>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div className="font-semibold text-xs text-secondary">{data.title}</div>
      <div className="text-[10px] text-muted-foreground">Layer</div>
    </div>
  );
}

export function ClaimNode({ data, selected }: BaseNodeProps) {
  return (
    <div className={cn("px-4 py-2 shadow-sm rounded-md border bg-background", selected && "border-primary")}>
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
      <div className="font-semibold text-xs text-accent">Claim</div>
      <div className="text-[10px] text-muted-foreground truncate w-32">{data.id}</div>
    </div>
  );
}

// Map kinds to components
export const nodeTypes = {
  scene: SceneNode,
  operation: OperationNode,
  layer: LayerNode,
  claim: ClaimNode,
  // Placeholders for figure and region
  figure: ClaimNode,
  region: ClaimNode,
};
