// features/investigation/components/tracePanel/ExecutionSpine.tsx — the pipeline trace, as an instrument.
//
// what  : The S1–S20 analysis pipeline as a spine of stage nodes: collapsed to a strip of pips and a total
//         latency, expanded to a full walk with per-stage timing, model and inspectable output.
// where : The bottom zone of InvestigationScreen, spanning the full width beneath the panels.
// how   : Most systems render a pipeline trace as a checklist and it decorates the screen. This one is
//         clickable: a stage that produced an intermediate product loads it onto the scene — the cloud
//         mask, the co-registration residual, the index map. The provenance requirements already oblige
//         the backend to retain those artefacts, so surfacing them costs a URI it already holds and buys
//         the operator the ability to see exactly what the machine saw at that moment.
//
//         Collapsed by default. The trace is the credibility layer, not the working surface, and it should
//         be one glance away rather than permanently occupying the bottom of the screen.
//
//         Stage labels are looked up locally from the pipeline constants rather than sent over the wire.
//         The backend sends a short code; the copy stays editable without a deploy, and a code that does
//         not exist fails at the schema boundary instead of rendering as a blank row.

"use client";

import { ChevronUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { dispatchCommand } from "@/lib/command-bus";
import { COMMAND_IDS } from "@/lib/constants/commands";
import { INVESTIGATION_LAYOUT } from "@/lib/constants/investigation";
import { formatDurationMs } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

import { useInvestigationStore } from "../../store/investigation-store";
import type { AnalysisRun } from "../../types/analysis.types";
import { TraceStepNode } from "./TraceStepNode";
import { AnalysisCanvas } from "./AnalysisCanvas";
import type { Claim } from "../../types/evidence.types";
import type { EvidenceLayer } from "../../types/layer.types";
import type { InvestigationSceneSlot } from "../../types/investigation.types";
import type { InvestigationVersion } from "../../types/version.types";
import { VersionCanvas } from "./VersionCanvas";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

interface ExecutionSpineProps {
  run: AnalysisRun | null;
  layersById: Record<string, EvidenceLayer>;
  claimsById: Record<string, Claim>;
  sceneSlots: readonly InvestigationSceneSlot[];
  versions: InvestigationVersion[];
}

export function ExecutionSpine({ run, layersById, claimsById, sceneSlots, versions }: ExecutionSpineProps) {
  const isExpanded = useInvestigationStore((state) => state.isTraceExpanded);
  const traceView = useInvestigationStore((state) => state.traceView);
  const setTraceView = useInvestigationStore((state) => state.setTraceView);
  const toggleTraceExpanded = useInvestigationStore((state) => state.toggleTraceExpanded);
  const artefactLayerId = useInvestigationStore((state) => state.artefactLayerId);

  const steps = run?.traceSteps ?? [];
  const completedCount = steps.filter((step) => step.state === "completed").length;

  const handleArtefactPeek = (layerId: string) => {
    void dispatchCommand(
      artefactLayerId === layerId
        ? COMMAND_IDS.investigation.clearArtefact
        : COMMAND_IDS.investigation.peekArtefact,
      artefactLayerId === layerId ? undefined : { layerId },
    );
  };

  return (
    <section
      style={{
        height: isExpanded
          ? INVESTIGATION_LAYOUT.traceExpandedHeightPx
          : INVESTIGATION_LAYOUT.traceCollapsedHeightPx,
      }}
      className="pointer-events-auto flex flex-col overflow-hidden rounded-md border border-border bg-surface-2/80 backdrop-blur-md transition-[height] duration-base ease-expo"
    >
      <header className="flex h-[34px] shrink-0 items-center gap-3 px-2">
        <button
          type="button"
          onClick={() => toggleTraceExpanded()}
          aria-expanded={isExpanded}
          className="flex items-center gap-1.5 rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <ChevronUp
            className={cn(
              "size-3 text-muted-foreground transition-transform duration-base ease-expo",
              isExpanded && "rotate-180",
            )}
            aria-hidden="true"
          />
          <span className="aeris-technical">Trace</span>
        </button>

        {steps.length === 0 ? (
          <span className="font-mono text-[10px] text-muted-foreground/60">
            No analysis has run yet
          </span>
        ) : (
          <>
            {!isExpanded ? (
              <ol className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden">
                {steps.map((step) => (
                  <li key={step.id}>
                    <TraceStepNode
                      step={step}
                      variant="pip"
                      isArtefactActive={artefactLayerId === step.artefactLayerId}
                      onPeekArtefact={handleArtefactPeek}
                    />
                  </li>
                ))}
              </ol>
            ) : (
              <span className="min-w-0 flex-1" />
            )}

            <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">
              {completedCount}/{steps.length}
              {run?.totalDurationMs != null ? ` · ${formatDurationMs(run.totalDurationMs)}` : ""}
            </span>
          </>
        )}
      </header>

      {isExpanded ? (
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            <div className="flex justify-end mb-2">
              <Dialog open={traceView === "canvas"} onOpenChange={(open) => setTraceView(open ? "canvas" : "rows")}>
                <DialogTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs"
                  >
                    View Analysis Canvas
                  </Button>
                </DialogTrigger>
                <DialogContent className="!max-w-[95vw] w-[1600px] h-[90vh] flex flex-col overflow-hidden p-0 border-border bg-slate-950">
                  <DialogTitle className="sr-only">Analysis Canvas</DialogTitle>
                  <Tabs defaultValue="trace" className="flex-1 flex flex-col min-h-0 h-full">
                    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 bg-slate-900/80 p-1 rounded-lg backdrop-blur-md border border-slate-700/50 shadow-2xl">
                      <TabsList className="bg-transparent gap-1">
                        <TabsTrigger value="trace" className="rounded-md px-6 py-2 data-[state=active]:bg-indigo-500/20 data-[state=active]:text-indigo-300">Analysis Trace</TabsTrigger>
                        <TabsTrigger value="versions" className="rounded-md px-6 py-2 data-[state=active]:bg-indigo-500/20 data-[state=active]:text-indigo-300">Version History</TabsTrigger>
                      </TabsList>
                    </div>
                    
                    <TabsContent value="trace" className="flex-1 min-h-0 w-full h-full m-0 data-[state=inactive]:hidden outline-none">
                      <AnalysisCanvas
                        run={run}
                        layersById={layersById}
                        claimsById={claimsById}
                        sceneSlots={sceneSlots}
                      />
                    </TabsContent>
                    
                    <TabsContent value="versions" className="flex-1 min-h-0 w-full h-full m-0 data-[state=inactive]:hidden outline-none">
                      <VersionCanvas versions={versions} />
                    </TabsContent>
                  </Tabs>
                </DialogContent>
              </Dialog>
            </div>
            <ol className="flex flex-col gap-0.5">
              {steps.map((step) => (
                <li key={step.id}>
                  <TraceStepNode
                    step={step}
                    variant="row"
                    isArtefactActive={artefactLayerId === step.artefactLayerId}
                    onPeekArtefact={handleArtefactPeek}
                  />
                </li>
              ))}
            </ol>

            {artefactLayerId !== null ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="mt-1 h-6 text-aeris-teal"
                onClick={() => void dispatchCommand(COMMAND_IDS.investigation.clearArtefact)}
              >
                Clear inspected output
              </Button>
            ) : null}
          </div>
      ) : null}
    </section>
  );
}
