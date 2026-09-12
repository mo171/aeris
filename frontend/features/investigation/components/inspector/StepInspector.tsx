"use client";

import { X } from "lucide-react";
import { useInvestigationStore } from "../../store/investigation-store";
import type { AnalysisRun } from "../../types/analysis.types";
import { Button } from "@/components/ui/button";
import { getModel } from "@/mock/data/model.data"; // Ideally from a service/store

interface StepInspectorProps {
  run: AnalysisRun | null;
}

export function StepInspector({ run }: StepInspectorProps) {
  const selectedNodeId = useInvestigationStore((state) => state.selectedNodeId);
  const setSelectedNodeId = useInvestigationStore((state) => state.setSelectedNodeId);

  if (!selectedNodeId || !run) return null;

  // Assuming node IDs in trace steps match selectedNodeId for operations
  const step = run.traceSteps.find((s) => s.id === selectedNodeId);

  // Note: We might also want to inspect Scenes, Layers, Claims if they are selected.
  // For Phase B, we focus on inspecting the operations (steps) for parameters.
  
  if (!step) {
    return (
      <div className="flex h-full flex-col bg-surface-1 shadow-sm border-l overflow-hidden">
        <header className="flex h-10 items-center justify-between border-b px-4">
          <span className="font-semibold text-sm">Node Inspector</span>
          <Button variant="ghost" size="icon" onClick={() => setSelectedNodeId(null)}>
            <X className="size-4" />
          </Button>
        </header>
        <div className="p-4 text-xs text-muted-foreground">
          Node "{selectedNodeId}" is not a trace step operation, or not found.
        </div>
      </div>
    );
  }

  const model = step.model ? getModel(step.model.id) : null;

  return (
    <div className="flex h-full flex-col bg-surface-1 shadow-sm border-l overflow-hidden w-80">
      <header className="flex h-10 items-center justify-between border-b px-4">
        <span className="font-semibold text-sm">Step Inspector</span>
        <Button variant="ghost" size="icon" onClick={() => setSelectedNodeId(null)}>
          <X className="size-4" />
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        <section>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Operation</h4>
          <div className="text-sm">{step.operationId || step.stageCode}</div>
          <div className="text-xs text-muted-foreground mt-1">
            {model ? `${model.name} v${step.model?.version}` : ""}
          </div>
          <div className="text-xs text-muted-foreground italic mt-2">
            "{step.rationale}"
          </div>
        </section>

        <section>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Inputs</h4>
          <ul className="text-xs space-y-1">
            {step.inputs.map((input) => (
              <li key={input.id} className="text-muted-foreground">
                <span className="font-mono">{input.kind}</span>: {input.id}
              </li>
            ))}
            {step.inputs.length === 0 && <li className="text-muted-foreground">None</li>}
          </ul>
        </section>

        <section>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Parameters</h4>
          <div className="text-xs border rounded-md p-2 bg-background space-y-2">
            {Object.entries(step.parameters).length === 0 ? (
              <span className="text-muted-foreground">No tunable parameters</span>
            ) : (
              Object.entries(step.parameters).map(([key, value]) => (
                <div key={key} className="flex justify-between items-center">
                  <span className="font-medium">{key}</span>
                  <span className="font-mono text-aeris-teal bg-aeris-teal/10 px-1 py-0.5 rounded">
                    {String(value)}
                  </span>
                </div>
              ))
            )}
          </div>
        </section>

        <section>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Outputs</h4>
          <ul className="text-xs space-y-1">
            {step.outputs.map((output) => (
              <li key={output.id} className="text-muted-foreground">
                <span className="font-mono">{output.kind}</span>: {output.id}
              </li>
            ))}
            {step.outputs.length === 0 && <li className="text-muted-foreground">None</li>}
          </ul>
        </section>

        <section>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Runtime</h4>
          <div className="text-xs text-muted-foreground">
            State: <span className="text-foreground">{step.state}</span>
            <br />
            Duration: <span className="text-foreground">{step.durationMs ? `${step.durationMs}ms` : "N/A"}</span>
          </div>
        </section>
      </div>

      <footer className="border-t p-4">
        <Button className="w-full" disabled variant="outline">
          Edit Parameters (Phase C)
        </Button>
      </footer>
    </div>
  );
}
