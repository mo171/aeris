// features/missionCommand/components/assistantPanel/ExecutionTraceBlock.tsx — the agent's audit trail.
//
// what  : Renders the ordered execution steps behind an answer, each with its state, detail and duration.
// where : Rendered inside every AERIS message in the assistant panel.
// how   : This is the component that separates AERIS from a chatbot. It shows which specialist model ran,
//         in what order, with what parameters and how long it took — the provenance the product promises,
//         visible while the answer is still being produced rather than reconstructed afterwards.
//
//         It expands automatically while the answer streams, then collapses to a one-line summary once
//         complete, unless the operator has expressed a preference. A transcript where every trace stays
//         open becomes unreadable after three questions; one where they are always closed hides the thing
//         that makes the answer trustworthy.

"use client";

import { Check, ChevronDown, LoaderCircle, Minus, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { formatDurationMs } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import type { AssistantMessageStatus, ExecutionStepState, ExecutionTraceStep } from "../../types/assistant.types";

interface ExecutionTraceBlockProps {
  steps: readonly ExecutionTraceStep[];
  messageStatus: AssistantMessageStatus;
}

export function ExecutionTraceBlock({ steps, messageStatus }: ExecutionTraceBlockProps) {
  const [operatorPreference, setOperatorPreference] = useState<boolean | null>(null);
  const isStreaming = messageStatus === "streaming";
  const isExpanded = operatorPreference ?? isStreaming;

  const totalDurationMs = useMemo(
    () => steps.reduce((total, step) => total + (step.durationMs ?? 0), 0),
    [steps],
  );

  if (steps.length === 0) {
    return null;
  }

  return (
    <div className="mt-2 overflow-hidden rounded-md border border-border-soft bg-aeris-black/40">
      <button
        type="button"
        onClick={() => setOperatorPreference(!isExpanded)}
        aria-expanded={isExpanded}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left transition-colors duration-fast hover:bg-surface-2/50"
      >
        <span className="aeris-technical">Execution trace</span>
        <span className="font-mono text-[10px] text-muted-foreground">
          {steps.length} step{steps.length === 1 ? "" : "s"}
          {totalDurationMs > 0 ? ` · ${formatDurationMs(totalDurationMs)}` : ""}
        </span>
        <ChevronDown
          className={cn(
            "ml-auto size-3 shrink-0 text-muted-foreground transition-transform duration-base ease-expo",
            isExpanded && "rotate-180",
          )}
          aria-hidden="true"
        />
      </button>

      {isExpanded ? (
        <ol className="border-t border-border-soft px-2.5 py-1.5">
          {steps.map((step, index) => (
            <li key={step.id} className="flex items-start gap-2 py-1">
              <span className="mt-px shrink-0">
                <ExecutionStepIcon state={step.state} />
              </span>

              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-1.5">
                  <span
                    className={cn(
                      "font-mono text-[10px] tracking-wide",
                      step.state === "running" ? "text-aeris-teal" : "text-foreground/85",
                    )}
                  >
                    {String(index + 1).padStart(2, "0")} {step.label}
                  </span>
                  {step.durationMs !== null ? (
                    <span className="ml-auto shrink-0 font-mono text-[9px] text-muted-foreground">
                      {formatDurationMs(step.durationMs)}
                    </span>
                  ) : null}
                </span>
                {step.detail ? (
                  <span className="mt-0.5 block font-mono text-[9px] leading-relaxed text-muted-foreground">
                    {step.detail}
                  </span>
                ) : null}
              </span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}

function ExecutionStepIcon({ state }: { state: ExecutionStepState }) {
  switch (state) {
    case "running":
      return <LoaderCircle className="size-3 animate-spin text-aeris-teal" aria-label="Running" />;
    case "completed":
      return <Check className="size-3 text-aeris-green" aria-label="Completed" />;
    case "failed":
      return <TriangleAlert className="size-3 text-aeris-red" aria-label="Failed" />;
    case "skipped":
      return <Minus className="size-3 text-muted-foreground" aria-label="Skipped" />;
    case "pending":
      return (
        <span
          className="mt-1 block size-1.5 rounded-full border border-muted-foreground/60"
          aria-label="Pending"
        />
      );
  }
}
