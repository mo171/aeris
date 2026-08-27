// features/investigation/components/answerPanel/InvestigatePlanSheet.tsx — the plan, before anything runs.
//
// what  : Shows the steps an autonomous investigation intends to take, lets the operator strike any of
//         them out, and runs the rest.
// where : Rendered by AnswerPanel when a plan has been prepared.
// how   : Showing the plan first is what makes the macro an instrument rather than a demo script. A
//         rehearsed sequence cannot survive a judge deleting a step; this one can, because the backend
//         receives the approved plan rather than a fixed one.
//
//         Each step names the model it will use, so the operator is approving specific work rather than
//         a vague promise to look into it.

"use client";

import { Play, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { getPipelineStage } from "@/lib/constants/pipeline-stages";
import { cn } from "@/lib/utils";

import type { AnalysisPlan } from "../../types/analysis.types";

interface InvestigatePlanSheetProps {
  plan: AnalysisPlan;
  onToggleStep: (stepId: string) => void;
  onExecute: () => void;
  onDismiss: () => void;
}

export function InvestigatePlanSheet({
  plan,
  onToggleStep,
  onExecute,
  onDismiss,
}: InvestigatePlanSheetProps) {
  const enabledCount = plan.steps.filter((step) => step.isEnabled).length;

  return (
    <section className="rounded-md border border-aeris-teal/40 bg-surface-2 p-3">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="aeris-technical text-aeris-teal">Planned investigation</h3>
          <p className="mt-1 text-sm leading-snug text-foreground">{plan.summary}</p>
        </div>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-label="Dismiss the plan"
          onClick={onDismiss}
        >
          <X />
        </Button>
      </header>

      <ol className="mt-3 flex flex-col gap-1.5">
        {plan.steps.map((step) => (
          <li key={step.id} className="flex items-start gap-2">
            <Checkbox
              id={step.id}
              checked={step.isEnabled}
              onCheckedChange={() => onToggleStep(step.id)}
              className="mt-0.5"
            />
            <label htmlFor={step.id} className="min-w-0 cursor-pointer">
              <span
                className={cn(
                  "block text-xs font-medium",
                  step.isEnabled ? "text-foreground" : "text-muted-foreground line-through",
                )}
              >
                {step.title}
              </span>
              <span className="block text-[11px] leading-snug text-muted-foreground">
                {step.description}
              </span>
              <span className="mt-0.5 block font-mono text-[10px] text-muted-foreground/70">
                {step.stageCode} · {getPipelineStage(step.stageCode).label} · {step.modelId}
              </span>
            </label>
          </li>
        ))}
      </ol>

      <Button
        type="button"
        size="sm"
        className="mt-3 w-full"
        disabled={enabledCount === 0}
        onClick={onExecute}
      >
        <Play />
        Run {enabledCount} {enabledCount === 1 ? "step" : "steps"}
      </Button>
    </section>
  );
}
