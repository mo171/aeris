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
        "px-6 py-4 shadow-lg rounded-xl border border-border bg-slate-900/95 backdrop-blur-md text-left transition-all min-w-[220px] max-w-[260px]",
        selected && "border-primary ring-2 ring-primary ring-offset-2 ring-offset-slate-950",
      )}
    >
      <Handle type="source" position={Position.Bottom} className="!bg-muted-foreground w-4 h-4" />
      <div className="font-semibold text-xs text-muted-foreground uppercase tracking-widest">Scene</div>
      <div className="text-sm text-foreground font-mono truncate max-w-[200px] mt-1">{data.sceneId ?? data.id}</div>
    </div>
  );
}

const operationStateStyle: Record<string, string> = {
  completed: "border-teal-500/50 bg-teal-950/40 shadow-[0_0_25px_rgba(20,184,166,0.2)]",
  running:   "border-blue-500/60 bg-blue-950/40 animate-pulse shadow-[0_0_25px_rgba(59,130,246,0.3)]",
  skipped:   "border-slate-700 bg-slate-800/40 opacity-70",
  failed:    "border-red-500/50 bg-red-950/40 shadow-[0_0_25px_rgba(239,68,68,0.2)]",
  pending:   "border-slate-700 bg-slate-900/80",
};

export function OperationNode({ data, selected }: BaseNodeProps) {
  const state: string = data.state ?? "pending";
  const stateClass = operationStateStyle[state] ?? operationStateStyle.pending;

  return (
    <div
      className={cn(
        "px-6 py-4 shadow-lg rounded-xl border text-left backdrop-blur-md transition-all min-w-[220px] max-w-[260px]",
        stateClass,
        selected && "ring-2 ring-primary ring-offset-2 ring-offset-slate-950",
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-muted-foreground w-4 h-4" />
      <Handle type="source" position={Position.Bottom} className="!bg-muted-foreground w-4 h-4" />
      <div className="font-bold text-base text-foreground truncate max-w-[200px]">
        {data.operationId || data.stageCode}
      </div>
      <div className="text-sm text-muted-foreground mt-2 flex items-center justify-between">
        {state === "skipped" ? (
          <span className="line-through">reused</span>
        ) : (
          <span className="uppercase tracking-widest text-[10px] font-bold text-slate-400">{state}</span>
        )}
        {data.durationMs != null && state === "completed" && (
          <span className="ml-3 text-teal-400 font-mono font-medium">{data.durationMs}ms</span>
        )}
      </div>
    </div>
  );
}

export function LayerNode({ data, selected }: BaseNodeProps) {
  return (
    <div
      className={cn(
        "px-6 py-4 shadow-lg rounded-xl border border-border bg-slate-900/95 backdrop-blur-md text-left transition-all min-w-[220px] max-w-[260px]",
        selected && "border-primary ring-2 ring-primary ring-offset-2 ring-offset-slate-950",
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-muted-foreground w-4 h-4" />
      <Handle type="source" position={Position.Bottom} className="!bg-muted-foreground w-4 h-4" />
      <div className="font-bold text-base text-foreground truncate max-w-[200px]">
        {data.title ?? data.id}
      </div>
      <div className="text-xs text-muted-foreground mt-2 uppercase tracking-widest font-bold">Layer</div>
    </div>
  );
}

export function ClaimNode({ data, selected }: BaseNodeProps) {
  return (
    <div
      className={cn(
        "px-6 py-4 shadow-lg rounded-xl border border-amber-500/40 bg-amber-950/40 backdrop-blur-md text-left transition-all min-w-[220px] max-w-[260px]",
        selected && "border-amber-500 ring-2 ring-amber-500 ring-offset-2 ring-offset-slate-950",
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-amber-500/60 w-4 h-4" />
      <div className="font-bold text-base text-amber-500">Claim</div>
      <div className="text-sm text-amber-500/70 font-mono truncate max-w-[200px] mt-1">{data.id}</div>
    </div>
  );
}

export function VersionNode({ data, selected }: BaseNodeProps) {
  const date = new Date(data.createdAt).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div
      className={cn(
        "px-6 py-4 shadow-lg rounded-full border border-border bg-slate-900/95 backdrop-blur-md text-left transition-all min-w-[220px] max-w-[260px] flex flex-col items-center justify-center text-center",
        selected && "border-indigo-500 ring-2 ring-indigo-500 ring-offset-2 ring-offset-slate-950",
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-indigo-500 w-4 h-4" />
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-500 w-4 h-4" />
      <div className="font-bold text-lg text-foreground truncate w-full px-2">
        {data.label}
      </div>
      <div className="text-xs text-indigo-400 font-mono mt-1">
        {data.id.substring(0, 8)}
      </div>
      <div className="text-xs text-muted-foreground mt-1">
        {date}
      </div>
    </div>
  );
}

export const nodeTypes = {
  scene:     SceneNode,
  operation: OperationNode,
  layer:     LayerNode,
  claim:     ClaimNode,
  version:   VersionNode,
  figure:    LayerNode,
  region:    SceneNode,
} as const;
