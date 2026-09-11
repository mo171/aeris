// features/modelObservatory/components/ModelObservatoryScreen.tsx — the specialist model registry.
//
// what  : Every model AERIS can dispatch to, with its live health, the pipeline stages it serves, why the
//         router selects it, and what it is known to get wrong.
// where : Rendered by app/(reference)/models/page.tsx.
// how   : A JOIN, not a fetch. What a model IS comes from lib/constants/models.ts; how it is DOING comes
//         from the status feed. That split is the same one pipeline-stages.ts uses, and it is why the trace
//         and this page can never give an operator two different accounts of the same model.
//
//         SELECTION RATIONALE IS THE POINT OF THE PAGE. The design document asks for capabilities,
//         versions, performance "and why they were selected". The first three are a status table anyone
//         could build; the fourth is the one that tells an analyst whether the routing decision behind
//         their answer was reasonable, so it gets the width and sits above the numbers.
//
//         THE LOADING STATE IS PLAIN MARKUP, NOT PanelSkeleton. Rendering that skeleton here leaves the
//         page permanently on its server HTML — it never hydrates, so the status query never fires and the
//         skeleton never resolves. Reproduced on a clean production build, on both surfaces in this route
//         group, and unaffected by `force-dynamic`; swapping the skeleton for plain markup fixes it every
//         time. Root cause not yet found — see fcontext/memory.md before reintroducing it.
//
//         LIMITATIONS SIT BESIDE THE RATIONALE, deliberately. A registry that only lists what each model is
//         good at teaches an operator to trust all of them equally. Every entry here states where it fails,
//         on the same row, in the same weight.

"use client";

import { GlassPanel } from "@/components/sharedUI/dumbComponent/GlassPanel";
import { GlowDot, type GlowDotTone } from "@/components/sharedUI/dumbComponent/GlowDot";
import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { ErrorState } from "@/components/sharedUI/functionalComponent/feedback/ErrorState";
import { PanelSkeleton } from "@/components/sharedUI/functionalComponent/feedback/PanelSkeleton";
import { useModelStatus } from "@/features/missionCommand/hooks/use-model-status";
import type { ModelHealth, ModelStatus } from "@/features/missionCommand/types/model.types";
import {
  MODEL_CAPABILITY_LABEL,
  MODEL_ORDER,
  SPECIALIST_MODELS,
  type SpecialistModel,
} from "@/lib/constants/models";
import { getPipelineStage } from "@/lib/constants/pipeline-stages";
import { formatDurationMs } from "@/lib/formatters";
import { cn } from "@/lib/utils";

const HEALTH_TONE: Record<ModelHealth, GlowDotTone> = {
  online: "green",
  warming: "blue",
  degraded: "amber",
  offline: "red",
};

/** What each health state means for a question asked right now. */
const HEALTH_CONSEQUENCE: Record<ModelHealth, string> = {
  online: "Available",
  warming: "Loading — first request will be slow",
  degraded: "Answering, but slower and under load",
  offline: "Unavailable — questions needing it will be refused",
};

export function ModelObservatoryScreen() {
  const { models, onlineCount, degradedCount, offlineCount, isLoading, error, refetch } =
    useModelStatus();

  const statusById = new Map(models.map((model) => [model.id, model]));

  return (
    <div className="absolute inset-0 overflow-y-auto p-4">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-3">
        <GlassPanel className="overflow-hidden">
          <SectionHeader
            title="Model Observatory"
            trailing={
              <span className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
                <FleetCount tone="green" count={onlineCount} label="online" />
                <FleetCount tone="amber" count={degradedCount} label="degraded" />
                <FleetCount tone="red" count={offlineCount} label="offline" />
              </span>
            }
          />
          <p className="px-3 pb-2 text-[11px] leading-relaxed text-muted-foreground">
            Every specialist AERIS can dispatch to. The router picks one per stage using the rule stated on
            each entry — the same text the execution trace shows against the step that used it.
          </p>
        </GlassPanel>

        {error ? (
          <GlassPanel>
            <ErrorState error={error} onRetry={refetch} />
          </GlassPanel>
        ) : isLoading ? (
          <PanelSkeleton rowCount={3} rowHeight={180} />
        ) : (
          <ul className="flex flex-col gap-2">
            {MODEL_ORDER.map((modelId) => (
              <li key={modelId}>
                <ModelCard
                  model={SPECIALIST_MODELS[modelId]}
                  status={statusById.get(modelId) ?? null}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function ModelCard({ model, status }: { model: SpecialistModel; status: ModelStatus | null }) {
  return (
    <GlassPanel className="p-3">
      <header className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {status ? (
          <GlowDot tone={HEALTH_TONE[status.health]} isPulsing={status.health === "warming"} />
        ) : (
          <GlowDot tone="neutral" />
        )}

        <h2 className="text-sm font-medium text-foreground">{model.name}</h2>

        <span className="rounded-[2px] border border-border-soft px-1 font-mono text-[9px] tracking-wide text-muted-foreground uppercase">
          {MODEL_CAPABILITY_LABEL[model.capability]}
        </span>

        <span className="font-mono text-[10px] text-muted-foreground/70">{model.family}</span>

        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
          {/* A model with no status row is declared but not deployed. Saying so beats an empty cell. */}
          {status ? `v${status.version}` : "not deployed"}
        </span>
      </header>

      <p className="mt-1.5 text-xs leading-relaxed text-foreground">{model.role}</p>

      <dl className="mt-2 flex flex-col gap-1.5 border-t border-border-soft pt-2">
        <Row label="Chosen when">{model.selectionRationale}</Row>
        <Row label="Fails on" tone="warning">
          {model.limitations}
        </Row>
      </dl>

      <footer className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border-soft pt-1.5">
        <span className="flex flex-wrap items-center gap-1">
          {model.stageCodes.map((stageCode) => (
            <span
              key={stageCode}
              title={getPipelineStage(stageCode).label}
              className="rounded-[2px] bg-surface-2 px-1 font-mono text-[9px] text-muted-foreground"
            >
              {stageCode} · {getPipelineStage(stageCode).label}
            </span>
          ))}
        </span>

        {status ? (
          <span className="ml-auto flex items-center gap-3 font-mono text-[10px] text-muted-foreground">
            <span title="Median latency">{formatDurationMs(status.medianLatencyMs)}</span>
            {status.queueDepth > 0 ? (
              <span className="text-aeris-amber" title="Queue depth">
                ×{status.queueDepth} queued
              </span>
            ) : null}
            <span
              className={cn(
                status.health === "online" ? "text-muted-foreground" : "text-aeris-amber",
              )}
            >
              {HEALTH_CONSEQUENCE[status.health]}
            </span>
          </span>
        ) : null}
      </footer>
    </GlassPanel>
  );
}

function Row({
  label,
  children,
  tone = "default",
}: {
  label: string;
  children: React.ReactNode;
  tone?: "default" | "warning";
}) {
  return (
    <div className="flex gap-2">
      <dt className="w-20 shrink-0 font-mono text-[9px] tracking-wide text-muted-foreground/50 uppercase">
        {label}
      </dt>
      <dd
        className={cn(
          "min-w-0 flex-1 text-[11px] leading-relaxed",
          tone === "warning" ? "text-aeris-amber/80" : "text-muted-foreground",
        )}
      >
        {children}
      </dd>
    </div>
  );
}

function FleetCount({
  tone,
  count,
  label,
}: {
  tone: GlowDotTone;
  count: number;
  label: string;
}) {
  return (
    <span className="flex items-center gap-1">
      <GlowDot tone={count > 0 ? tone : "neutral"} />
      {count} {label}
    </span>
  );
}
