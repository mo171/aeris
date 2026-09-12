"use client";

import { useState, useCallback } from "react";
import { X, Pencil } from "lucide-react";
import { useInvestigationStore } from "../../store/investigation-store";
import type { AnalysisRun } from "../../types/analysis.types";
import type { ParameterValue } from "@/lib/constants/parameters";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SPECIALIST_MODELS } from "@/lib/constants/models";
import { dispatchCommand } from "@/lib/command-bus";
import { COMMAND_IDS } from "@/lib/constants/commands";

interface StepInspectorProps {
  run: AnalysisRun | null;
}

export function StepInspector({ run }: StepInspectorProps) {
  const selectedNodeId = useInvestigationStore((state) => state.selectedNodeId);
  const setSelectedNodeId = useInvestigationStore((state) => state.setSelectedNodeId);

  const [isEditing, setIsEditing] = useState(false);
  const [draftParams, setDraftParams] = useState<Record<string, ParameterValue>>({});

  const step = run?.traceSteps.find((s) => s.id === selectedNodeId) ?? null;

  const handleSelect = useCallback(
    (nodeId: string | null) => {
      setSelectedNodeId(nodeId);
      setIsEditing(false);
      if (nodeId) {
        const s = run?.traceSteps.find((t) => t.id === nodeId);
        setDraftParams(s ? { ...s.parameters } : {});
      }
    },
    [run, setSelectedNodeId],
  );

  // Keep draft in sync when a new node is selected
  if (step && Object.keys(draftParams).length === 0 && Object.keys(step.parameters).length > 0) {
    setDraftParams({ ...step.parameters });
  }

  if (!selectedNodeId || !run) return null;

  if (!step) {
    return (
      <div className="flex h-full flex-col bg-surface-1 shadow-sm border-l overflow-hidden w-80">
        <header className="flex h-10 shrink-0 items-center justify-between border-b px-4">
          <span className="font-semibold text-sm">Node Inspector</span>
          <Button variant="ghost" size="icon" onClick={() => handleSelect(null)}>
            <X className="size-4" />
          </Button>
        </header>
        <div className="p-4 text-xs text-muted-foreground">
          This node is not an inspectable trace step.
        </div>
      </div>
    );
  }

  const model = step.model ? SPECIALIST_MODELS[step.model.id as keyof typeof SPECIALIST_MODELS] : null;
  const hasParams = Object.keys(step.parameters).length > 0;
  const hasEdits = JSON.stringify(draftParams) !== JSON.stringify(step.parameters);

  const handleRerun = () => {
    void dispatchCommand(COMMAND_IDS.investigation.rerunStep, {
      stepId: step.id,
      parameterOverrides: draftParams,
    });
    setIsEditing(false);
  };

  const handleParamChange = (key: string, rawValue: string) => {
    const original = step.parameters[key];
    // Preserve the type of the original value
    let coerced: ParameterValue = rawValue;
    if (typeof original === "number") {
      const n = parseFloat(rawValue);
      coerced = isNaN(n) ? original : n;
    } else if (typeof original === "boolean") {
      coerced = rawValue === "true";
    }
    setDraftParams((prev) => ({ ...prev, [key]: coerced }));
  };

  return (
    <div className="flex h-full flex-col bg-surface-1 shadow-sm border-l overflow-hidden w-80">
      <header className="flex h-10 shrink-0 items-center justify-between border-b px-4">
        <span className="font-semibold text-sm">Step Inspector</span>
        <div className="flex items-center gap-1">
          {!isEditing && hasParams && (
            <Button
              variant="ghost"
              size="icon"
              title="Edit parameters"
              onClick={() => { setIsEditing(true); setDraftParams({ ...step.parameters }); }}
            >
              <Pencil className="size-3.5" />
            </Button>
          )}
          <Button variant="ghost" size="icon" onClick={() => handleSelect(null)}>
            <X className="size-4" />
          </Button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* Operation */}
        <section>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Operation</h4>
          <div className="text-sm font-medium">{step.operationId || step.stageCode}</div>
          {model && (
            <div className="text-xs text-muted-foreground mt-1">
              {model.name} · v{step.model?.version}
            </div>
          )}
          {step.rationale && (
            <div className="text-xs text-muted-foreground italic mt-2">"{step.rationale}"</div>
          )}
        </section>

        {/* Inputs */}
        <section>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Inputs</h4>
          <ul className="space-y-1">
            {step.inputs.length === 0 ? (
              <li className="text-xs text-muted-foreground">None</li>
            ) : (
              step.inputs.map((input) => (
                <li key={input.id} className="text-xs">
                  <span className="font-mono text-muted-foreground">{input.kind}</span>
                  <span className="text-foreground"> {input.id}</span>
                </li>
              ))
            )}
          </ul>
        </section>

        {/* Parameters */}
        <section>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Parameters</h4>
          {!hasParams ? (
            <p className="text-xs text-muted-foreground">No tunable parameters.</p>
          ) : (
            <div className="border rounded-md p-2 bg-background space-y-3">
              {Object.entries(step.parameters).map(([key, value]) => (
                <div key={key}>
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-xs font-medium">{key}</span>
                    {!isEditing && (
                      <span className="font-mono text-xs text-aeris-teal bg-aeris-teal/10 px-1.5 py-0.5 rounded">
                        {String(value)}
                      </span>
                    )}
                  </div>
                  {isEditing && (
                    <Input
                      className="h-7 text-xs font-mono"
                      value={String(draftParams[key] ?? value)}
                      onChange={(e) => handleParamChange(key, e.target.value)}
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Outputs */}
        <section>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Outputs</h4>
          <ul className="space-y-1">
            {step.outputs.length === 0 ? (
              <li className="text-xs text-muted-foreground">None</li>
            ) : (
              step.outputs.map((output) => (
                <li key={output.id} className="text-xs">
                  <span className="font-mono text-muted-foreground">{output.kind}</span>
                  <span className="text-foreground"> {output.id}</span>
                </li>
              ))
            )}
          </ul>
        </section>

        {/* Runtime */}
        <section>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Runtime</h4>
          <div className="text-xs text-muted-foreground space-y-1">
            <div>
              State:{" "}
              <span
                className={
                  step.state === "completed"
                    ? "text-aeris-teal"
                    : step.state === "skipped"
                      ? "text-muted-foreground line-through"
                      : step.state === "failed"
                        ? "text-destructive"
                        : "text-foreground"
                }
              >
                {step.state}
              </span>
            </div>
            {step.state === "skipped" && step.detail && (
              <div className="text-[10px] italic">{step.detail}</div>
            )}
            <div>
              Duration:{" "}
              <span className="text-foreground">
                {step.durationMs != null ? `${step.durationMs}ms` : "—"}
              </span>
            </div>
          </div>
        </section>
      </div>

      {/* Footer actions */}
      <footer className="shrink-0 border-t p-3 space-y-2">
        {isEditing ? (
          <>
            <Button
              className="w-full"
              size="sm"
              onClick={handleRerun}
              disabled={!hasEdits}
            >
              Re-run from here
            </Button>
            <Button
              className="w-full"
              size="sm"
              variant="ghost"
              onClick={() => { setIsEditing(false); setDraftParams({ ...step.parameters }); }}
            >
              Cancel
            </Button>
          </>
        ) : (
          <Button
            className="w-full"
            size="sm"
            variant="outline"
            disabled={!hasParams}
            onClick={() => { setIsEditing(true); setDraftParams({ ...step.parameters }); }}
          >
            Edit Parameters & Re-run
          </Button>
        )}
      </footer>
    </div>
  );
}
