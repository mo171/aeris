import React, { useMemo, useState } from "react";
import { GitGraphCanvas, type GitGraphNode } from "@/components/sharedUI/gitGraphCanvas";
import { useInvestigationStore } from "../../store/investigation-store";
import type { AnalysisRun, AnalysisTraceStep } from "../../types/analysis.types";
import type { InvestigationSceneSlot } from "../../types/investigation.types";
import { formatDurationMs } from "@/lib/formatters";
import {
  ChevronDown,
  ChevronRight,
  Activity,
  Clock,
  Layers,
  FileJson,
  Settings2,
  SlidersHorizontal,
  RotateCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

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
      className="mt-3 p-3 bg-surface-2/60 rounded-md border border-border/80 flex flex-col gap-3"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between border-b border-border/60 pb-2">
        <span className="text-[10px] uppercase tracking-widest font-mono font-medium text-muted-foreground flex items-center gap-1.5">
          <SlidersHorizontal className="size-3 text-muted-foreground" />
          Checkpoint Parameters
        </span>
        <span className="text-[10px] font-mono text-muted-foreground/80 bg-surface-3/80 border border-border/50 px-1.5 py-0.5 rounded">
          Stage {step.stageCode}
        </span>
      </div>

      {isFusion && (
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center text-xs">
              <span className="text-muted-foreground text-[11px] font-mono">Confidence Threshold</span>
              <span className="font-mono text-xs text-foreground bg-surface-3 border border-border/60 px-1.5 py-0.5 rounded font-medium">
                {confidenceThreshold.toFixed(2)}
              </span>
            </div>
            <input
              type="range"
              min="0.50"
              max="0.95"
              step="0.01"
              value={confidenceThreshold}
              onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
              className="w-full h-1 bg-surface-4 rounded-full appearance-none cursor-pointer accent-foreground hover:accent-aeris-teal transition-colors"
            />
            <span className="text-[10px] text-muted-foreground/70 leading-tight">
              Lower to detect weaker crane &amp; reclamation signatures
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center text-xs">
              <span className="text-muted-foreground text-[11px] font-mono">SAR Weight Ratio</span>
              <span className="font-mono text-xs text-foreground bg-surface-3 border border-border/60 px-1.5 py-0.5 rounded font-medium">
                {sarWeightRatio.toFixed(2)}
              </span>
            </div>
            <input
              type="range"
              min="0.1"
              max="0.9"
              step="0.05"
              value={sarWeightRatio}
              onChange={(e) => setSarWeightRatio(parseFloat(e.target.value))}
              className="w-full h-1 bg-surface-4 rounded-full appearance-none cursor-pointer accent-foreground hover:accent-aeris-teal transition-colors"
            />
            <span className="text-[10px] text-muted-foreground/70 leading-tight">
              Favors radar backscatter over optical reflectance
            </span>
          </div>
        </div>
      )}

      {isSar && (
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center text-xs">
              <span className="text-muted-foreground text-[11px] font-mono">Backscatter Cutoff</span>
              <span className="font-mono text-xs text-foreground bg-surface-3 border border-border/60 px-1.5 py-0.5 rounded font-medium">
                {decibelCutoff} dB
              </span>
            </div>
            <input
              type="range"
              min="-25"
              max="-10"
              step="1"
              value={decibelCutoff}
              onChange={(e) => setDecibelCutoff(parseInt(e.target.value, 10))}
              className="w-full h-1 bg-surface-4 rounded-full appearance-none cursor-pointer accent-foreground hover:accent-aeris-teal transition-colors"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="text-muted-foreground text-[11px] font-mono">Lee Speckle Filter Window</span>
            <select
              value={filterWindow}
              onChange={(e) => setFilterWindow(e.target.value)}
              className="bg-surface-3 border border-border text-xs rounded px-2 py-1 text-foreground font-mono focus:outline-none focus:border-aeris-teal/50"
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
          <div className="flex justify-between items-center text-xs">
            <span className="text-muted-foreground text-[11px] font-mono">Sensitivity Threshold</span>
            <span className="font-mono text-xs text-foreground bg-surface-3 border border-border/60 px-1.5 py-0.5 rounded font-medium">
              {confidenceThreshold.toFixed(2)}
            </span>
          </div>
          <input
            type="range"
            min="0.50"
            max="0.99"
            step="0.01"
            value={confidenceThreshold}
            onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
            className="w-full h-1 bg-surface-4 rounded-full appearance-none cursor-pointer accent-foreground hover:accent-aeris-teal transition-colors"
          />
        </div>
      )}

      <Button
        variant="outline"
        size="sm"
        disabled={isSubmitting || step.state === "running"}
        onClick={handleRerun}
        className="w-full mt-1 border-border/90 bg-surface-3/60 hover:bg-surface-4 hover:border-aeris-teal/40 text-foreground font-mono text-xs font-medium flex items-center justify-center gap-2 h-8 rounded-md transition-colors"
      >
        <RotateCw className={cn("size-3.5 text-muted-foreground transition-transform", isSubmitting && "animate-spin text-aeris-teal")} />
        <span>{isSubmitting ? "Re-executing pipeline..." : `Branch Execution from Stage ${step.stageCode}`}</span>
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
              <div className="flex flex-col gap-3 p-3 bg-surface-2/60 rounded-md border border-border">
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] uppercase tracking-widest text-muted-foreground flex items-center gap-1.5 font-mono"><Activity className="w-3 h-3"/> State</span>
                  <span className="font-mono text-xs font-semibold capitalize" style={{ color: color }}>{step.state}</span>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] uppercase tracking-widest text-muted-foreground flex items-center gap-1.5 font-mono"><Clock className="w-3 h-3"/> Latency</span>
                  <span className="font-mono text-xs text-foreground">{step.durationMs ? formatDurationMs(step.durationMs) : '—'}</span>
                </div>
              </div>

              <div className="flex flex-col gap-3 p-3 bg-surface-2/60 rounded-md border border-border">
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] uppercase tracking-widest text-muted-foreground flex items-center gap-1.5 font-mono"><Layers className="w-3 h-3"/> Artefact / Output</span>
                  <span className="font-mono text-xs text-foreground break-all">{step.artefactLayerId || (step.outputs && step.outputs.length > 0 ? `${step.outputs.length} outputs generated` : 'None')}</span>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-[10px] uppercase tracking-widest text-muted-foreground flex items-center gap-1.5 font-mono"><Settings2 className="w-3 h-3"/> Operation</span>
                  <span className="font-mono text-xs text-foreground">{step.operationId || 'System Pipeline'}</span>
                </div>
              </div>
            </div>

            <StepParametersCard step={step} onRerunStep={onRerunStep} />

            {(step.inputs && step.inputs.length > 0) && (
              <div className="mt-2 p-3 bg-surface-2/60 rounded-md border border-border">
                <span className="text-[10px] uppercase tracking-widest text-muted-foreground flex items-center gap-1.5 mb-2 font-mono"><FileJson className="w-3 h-3"/> Inputs Referenced</span>
                <ul className="flex flex-wrap gap-2">
                  {step.inputs.map((input, idx) => (
                    <li key={idx} className="text-xs font-mono bg-surface-3 border border-border/70 px-2 py-0.5 rounded text-muted-foreground">
                      {input.kind}: <span className="text-foreground">{input.id}</span>
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
    return <div className="flex h-full items-center justify-center text-xs text-muted-foreground font-mono">No analysis trace available.</div>;
  }

  return (
    <div className="h-full w-full bg-background overflow-y-auto overflow-x-hidden p-6" onClick={() => setSelectedNodeId(null)}>
      <GitGraphCanvas nodes={nodes} className="max-w-4xl mx-auto" />
    </div>
  );
}
