import React, { useMemo, useState } from "react";
import { GitGraphCanvas, type GitGraphNode } from "@/components/sharedUI/gitGraphCanvas";
import { useInvestigationStore } from "../../store/investigation-store";
import type { AnalysisRun, AnalysisTraceStep } from "../../types/analysis.types";
import type { InvestigationSceneSlot } from "../../types/investigation.types";
import { formatDurationMs } from "@/lib/formatters";
import { ChevronDown, ChevronRight, Activity, Clock, Layers, FileJson, Settings2, Sliders, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";

interface AnalysisCanvasProps {
  run: AnalysisRun | null;
  layersById: Record<string, any>;
  claimsById: Record<string, any>;
  sceneSlots: readonly InvestigationSceneSlot[];
  onRerunStep?: (stepId: string, parameterOverrides: Record<string, any>) => void;
}

const stateColors: Record<string, string> = {
  completed: "#79C267", // Solid Green
  running: "#51A0E9", // Solid Blue
  failed: "#F27777", // Solid Red
  skipped: "#a1a1aa", // zinc-400
  pending: "#d4d4d8", // zinc-300
};

function StepParametersCard({
  step,
  onRerunStep,
}: {
  step: AnalysisTraceStep;
  onRerunStep?: (stepId: string, parameterOverrides: Record<string, any>) => void;
}) {
  const isFusion = /fusion|s12|cross-modal/i.test(step.stageCode || step.operationId || "");
  const isSar = /sar|s05|radar/i.test(step.stageCode || step.operationId || "");

  const [confidenceThreshold, setConfidenceThreshold] = useState<number>(
    typeof step.parameters?.confidenceThreshold === "number" ? step.parameters.confidenceThreshold : 0.85,
  );
  const [sarWeightRatio, setSarWeightRatio] = useState<number>(
    typeof step.parameters?.sarWeightRatio === "number" ? step.parameters.sarWeightRatio : 0.65,
  );
  const [filterWindow, setFilterWindow] = useState<string>(
    typeof step.parameters?.filterWindow === "string" ? step.parameters.filterWindow : "5x5",
  );
  const [decibelCutoff, setDecibelCutoff] = useState<number>(
    typeof step.parameters?.decibelCutoff === "number" ? step.parameters.decibelCutoff : -18,
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleRerun = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsSubmitting(true);
    const overrides = isFusion
      ? { confidenceThreshold, sarWeightRatio }
      : isSar
        ? { filterWindow, decibelCutoff }
        : { confidenceThreshold };
    onRerunStep?.(step.id, overrides);
    setTimeout(() => setIsSubmitting(false), 1200);
  };

  return (
    <div
      className="mt-3 p-3.5 bg-slate-950/80 rounded-lg border border-indigo-500/30 shadow-inner flex flex-col gap-3"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between border-b border-indigo-500/20 pb-2">
        <span className="text-[11px] uppercase tracking-wider font-semibold text-indigo-300 flex items-center gap-1.5 font-mono">
          <Sliders className="w-3.5 h-3.5 text-indigo-400" />
          Tunable Parameters &amp; Checkpoint
        </span>
        <span className="text-[10px] font-mono text-zinc-500">
          Stage {step.stageCode}
        </span>
      </div>

      {isFusion && (
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between text-xs">
              <span className="text-zinc-400">Confidence Threshold</span>
              <span className="font-mono text-indigo-300 font-bold">{confidenceThreshold.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min="0.50"
              max="0.95"
              step="0.01"
              value={confidenceThreshold}
              onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
            <span className="text-[10px] text-zinc-500">Lower to detect weaker crane &amp; reclamation signatures</span>
          </div>

          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between text-xs">
              <span className="text-zinc-400">SAR Weight Ratio</span>
              <span className="font-mono text-indigo-300 font-bold">{sarWeightRatio.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min="0.1"
              max="0.9"
              step="0.05"
              value={sarWeightRatio}
              onChange={(e) => setSarWeightRatio(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
            <span className="text-[10px] text-zinc-500">Favors radar backscatter over optical reflectance</span>
          </div>
        </div>
      )}

      {isSar && (
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between text-xs">
              <span className="text-zinc-400">Backscatter Cutoff</span>
              <span className="font-mono text-indigo-300 font-bold">{decibelCutoff} dB</span>
            </div>
            <input
              type="range"
              min="-25"
              max="-10"
              step="1"
              value={decibelCutoff}
              onChange={(e) => setDecibelCutoff(parseInt(e.target.value, 10))}
              className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="text-zinc-400 text-xs">Lee Speckle Filter Window</span>
            <select
              value={filterWindow}
              onChange={(e) => setFilterWindow(e.target.value)}
              className="bg-zinc-900 border border-zinc-700 text-xs rounded px-2 py-1 text-zinc-200"
            >
              <option value="3x3">3x3 (Fine Edge Preservation)</option>
              <option value="5x5">5x5 (Standard Coherence)</option>
              <option value="7x7">7x7 (High Smoothing)</option>
            </select>
          </div>
        </div>
      )}

      {!isFusion && !isSar && (
        <div className="flex flex-col gap-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-zinc-400">Sensitivity Threshold</span>
            <span className="font-mono text-indigo-300 font-bold">{confidenceThreshold.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min="0.50"
            max="0.99"
            step="0.01"
            value={confidenceThreshold}
            onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
            className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
          />
        </div>
      )}

      <Button
        size="sm"
        disabled={isSubmitting || step.state === "running"}
        onClick={handleRerun}
        className="w-full mt-1 bg-gradient-to-r from-teal-500 via-indigo-500 to-indigo-600 hover:from-teal-600 hover:to-indigo-700 text-white font-mono text-xs font-semibold shadow-md flex items-center justify-center gap-2 h-8 transition-all"
      >
        <Zap className={`w-3.5 h-3.5 text-amber-300 ${isSubmitting ? "animate-spin" : "animate-pulse"}`} />
        {isSubmitting ? "Re-executing Downstream Pipeline..." : "⚡ Re-run Pipeline from this Step"}
      </Button>
    </div>
  );
}

export function AnalysisCanvas({ run, onRerunStep }: AnalysisCanvasProps) {
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

            <StepParametersCard step={step} onRerunStep={onRerunStep} />

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
  }, [onRerunStep, run]);

  if (!run || !run.traceSteps || run.traceSteps.length === 0) {
    return <div className="flex h-full items-center justify-center text-xs text-muted-foreground">No analysis trace available.</div>;
  }

  return (
    <div className="h-full w-full bg-[#09090b] overflow-y-auto overflow-x-hidden p-6" onClick={() => setSelectedNodeId(null)}>
      <GitGraphCanvas nodes={nodes} className="max-w-4xl mx-auto" />
    </div>
  );
}
