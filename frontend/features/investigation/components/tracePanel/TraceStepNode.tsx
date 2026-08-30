// features/investigation/components/tracePanel/TraceStepNode.tsx — one pipeline stage, as a pip or a row.
//
// what  : Renders a single trace step in two densities: a pip for the collapsed spine, a full row with
//         label, model, timing and artefact control for the expanded one.
// where : Rendered by ExecutionSpine.
// how   : The running stage shimmers. That reuses the same idea as the satellite arcs on the globe —
//         motion travelling along a line to mean work in progress — so the visual language stays one
//         system across surfaces without any shared code.
//
//         A stage that produced an inspectable output is the only kind that is clickable, and it says so
//         by being the only kind that carries the eye icon. Making every row look interactive and having
//         most of them do nothing is worse than making the useful ones stand out.
//
//         WHY THIS MODEL is answered here rather than in the Model Observatory, because the operator
//         asking it is looking at the step that used it. The rationale is resolved from
//         lib/constants/models.ts by id — the wire carries the id, the copy lives in the catalogue — so
//         the trace and the Observatory cannot give two different answers. Steps with no model have no
//         second line, which keeps the spine dense where nothing was dispatched.

"use client";

import { Check, Eye, MinusCircle, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { getModel } from "@/lib/constants/models";
import { getPipelineStage } from "@/lib/constants/pipeline-stages";
import { ROUTES } from "@/lib/constants/routes";
import { formatDurationMs } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import type { AnalysisTraceStep, TraceStepState } from "../../types/analysis.types";

const STATE_TONE: Record<TraceStepState, string> = {
  pending: "bg-border text-muted-foreground",
  running: "bg-aeris-teal/70 text-aeris-teal",
  completed: "bg-aeris-teal text-aeris-teal",
  failed: "bg-aeris-red text-aeris-red",
  skipped: "bg-border text-muted-foreground/60",
};

interface TraceStepNodeProps {
  step: AnalysisTraceStep;
  variant: "pip" | "row";
  isArtefactActive: boolean;
  onPeekArtefact: (layerId: string) => void;
}

export function TraceStepNode({
  step,
  variant,
  isArtefactActive,
  onPeekArtefact,
}: TraceStepNodeProps) {
  const stage = getPipelineStage(step.stageCode);
  const tone = STATE_TONE[step.state];

  if (variant === "pip") {
    return (
      <span
        title={`${step.stageCode} · ${stage.label}`}
        className={cn(
          "block h-1.5 w-4 rounded-full",
          tone.split(" ")[0],
          step.state === "running" && "animate-pulse",
        )}
      />
    );
  }

  const canPeek = step.artefactLayerId !== null;
  const model = getModel(step.modelId);

  return (
    <div
      className={cn(
        "rounded-sm px-1.5 py-1 transition-colors duration-fast",
        isArtefactActive && "bg-aeris-teal/10",
      )}
    >
      <div className="flex items-center gap-2">
        <StateGlyph state={step.state} />

        <span className="w-7 shrink-0 font-mono text-[10px] text-muted-foreground">
          {step.stageCode}
        </span>

        <span className="min-w-0 flex-1 truncate text-xs text-foreground">
          {stage.label}
          {step.detail ? <span className="text-muted-foreground"> — {step.detail}</span> : null}
        </span>

        {model ? (
          <Link
            href={ROUTES.MODEL_OBSERVATORY}
            title={`${model.name} — open in the Model Observatory`}
            className="shrink-0 truncate rounded-sm font-mono text-[10px] text-muted-foreground/70 transition-colors duration-fast hover:text-aeris-teal focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            {model.id}
            {step.modelVersion ? `@${step.modelVersion}` : ""}
          </Link>
        ) : null}

        <span className="w-12 shrink-0 text-right font-mono text-[10px] tabular-nums text-muted-foreground">
          {step.durationMs === null ? "" : formatDurationMs(step.durationMs)}
        </span>

        {canPeek ? (
          <button
            type="button"
            onClick={() => onPeekArtefact(step.artefactLayerId!)}
            title={`Show what ${stage.label.toLowerCase()} produced`}
            className={cn(
              "shrink-0 rounded-sm p-0.5 transition-colors duration-fast hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              isArtefactActive ? "text-aeris-teal" : "text-muted-foreground",
            )}
          >
            <Eye className="size-3" aria-hidden="true" />
          </button>
        ) : (
          <span className="w-4 shrink-0" aria-hidden="true" />
        )}
      </div>

      {/* Why the router picked this model, on the step that used it. */}
      {model ? (
        <p className="mt-0.5 pr-16 pl-[3.15rem] text-[10px] leading-relaxed text-muted-foreground/60">
          {model.selectionRationale}
        </p>
      ) : null}
    </div>
  );
}

function StateGlyph({ state }: { state: TraceStepState }) {
  if (state === "failed") {
    return <TriangleAlert className="size-3 shrink-0 text-aeris-red" aria-hidden="true" />;
  }
  if (state === "skipped") {
    return <MinusCircle className="size-3 shrink-0 text-muted-foreground/60" aria-hidden="true" />;
  }
  if (state === "completed") {
    return <Check className="size-3 shrink-0 text-aeris-teal" aria-hidden="true" />;
  }
  return (
    <span
      className={cn(
        "size-3 shrink-0 rounded-full border",
        state === "running"
          ? "animate-pulse border-aeris-teal bg-aeris-teal/30"
          : "border-border",
      )}
      aria-hidden="true"
    />
  );
}
