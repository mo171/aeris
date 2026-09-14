"use client";

import React, { useMemo } from "react";
import { GitGraphCanvas, type GitGraphNode } from "@/components/sharedUI/gitGraphCanvas";
import { useInvestigationStore } from "../../store/investigation-store";
import type { AnalysisRun } from "../../types/analysis.types";
import type { InvestigationSceneSlot } from "../../types/investigation.types";
import { formatDurationMs } from "@/lib/formatters";
import { ChevronDown, ChevronRight, Activity, Clock, Layers, FileJson, Settings2 } from "lucide-react";

interface AnalysisCanvasProps {
  run: AnalysisRun | null;
  layersById: Record<string, any>;
  claimsById: Record<string, any>;
  sceneSlots: readonly InvestigationSceneSlot[];
}

const stateColors: Record<string, string> = {
  completed: "#79C267", // Solid Green
  running: "#51A0E9", // Solid Blue
  failed: "#F27777", // Solid Red
  skipped: "#a1a1aa", // zinc-400
  pending: "#d4d4d8", // zinc-300
};

export function AnalysisCanvas({ run }: AnalysisCanvasProps) {
  const setSelectedNodeId = useInvestigationStore((state) => state.setSelectedNodeId);

  const nodes = useMemo<GitGraphNode[]>(() => {
    if (!run || !run.traceSteps) return [];
    
    // We reverse so the newest is at the top
    const steps = [...run.traceSteps].reverse();
    
    return steps.map((step) => {
      const color = stateColors[step.state] || stateColors.pending;

      return {
        id: step.id,
        parents: step.dependsOn || [],
        color,
        renderRow: (node, isExpanded, toggleExpand) => (
          <div className="flex items-center justify-between py-1">
            <div className="flex items-center gap-3">
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              )}
              <span className="font-mono text-sm font-semibold text-zinc-200 uppercase tracking-widest">
                {step.stageCode}
              </span>
              <span className="text-xs text-zinc-400 truncate max-w-[300px]">
                {step.rationale || "Processing..."}
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs font-mono">
              <span className="uppercase tracking-widest text-[10px] font-bold text-zinc-500">
                {step.state}
              </span>
              {step.durationMs != null && (
                <span className="font-medium" style={{ color: color }}>
                  {formatDurationMs(step.durationMs)}
                </span>
              )}
            </div>
          </div>
        ),
        renderDetails: () => (
          <div className="flex flex-col gap-4 text-sm text-zinc-300">
            {step.rationale && (
              <div>
                <strong className="text-zinc-100 text-[10px] uppercase tracking-widest block mb-1">Rationale</strong>
                <span className="text-zinc-400">{step.rationale}</span>
              </div>
            )}
            
            {step.detail && (
              <div>
                <strong className="text-zinc-100 text-[10px] uppercase tracking-widest block mb-1">Evidence / Detail</strong>
                <span className="text-zinc-400 whitespace-pre-wrap">{step.detail}</span>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4 mt-2">
              <div className="flex flex-col gap-3 p-3 bg-[#09090b] rounded-md border border-zinc-800">
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 flex items-center gap-1"><Activity className="w-3 h-3"/> State</span>
                  <span className="font-mono capitalize" style={{ color: color }}>{step.state}</span>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 flex items-center gap-1"><Clock className="w-3 h-3"/> Latency</span>
                  <span className="font-mono">{step.durationMs ? formatDurationMs(step.durationMs) : '—'}</span>
                </div>
              </div>

              <div className="flex flex-col gap-3 p-3 bg-[#09090b] rounded-md border border-zinc-800">
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 flex items-center gap-1"><Layers className="w-3 h-3"/> Artefact / Output</span>
                  <span className="font-mono text-zinc-300 break-all">{step.artefactLayerId || (step.outputs && step.outputs.length > 0 ? `${step.outputs.length} outputs generated` : 'None')}</span>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] uppercase tracking-widest text-zinc-500 flex items-center gap-1"><Settings2 className="w-3 h-3"/> Operation</span>
                  <span className="font-mono text-zinc-300">{step.operationId || 'System Pipeline'}</span>
                </div>
              </div>
            </div>

            {(step.inputs && step.inputs.length > 0) && (
              <div className="mt-2 p-3 bg-[#09090b] rounded-md border border-zinc-800">
                <span className="text-[10px] uppercase tracking-widest text-zinc-500 flex items-center gap-1 mb-2"><FileJson className="w-3 h-3"/> Inputs Referenced</span>
                <ul className="flex flex-wrap gap-2">
                  {step.inputs.map((input, idx) => (
                    <li key={idx} className="text-xs font-mono bg-zinc-900 border border-zinc-700 px-2 py-0.5 rounded text-zinc-400">
                      {input.kind}: {input.id}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ),
      };
    });
  }, [run]);

  if (!run || !run.traceSteps || run.traceSteps.length === 0) {
    return <div className="flex h-full items-center justify-center text-xs text-muted-foreground">No analysis trace available.</div>;
  }

  return (
    <div className="h-full w-full bg-[#09090b] overflow-y-auto overflow-x-hidden p-6" onClick={() => setSelectedNodeId(null)}>
      <GitGraphCanvas nodes={nodes} className="max-w-4xl mx-auto" />
    </div>
  );
}
