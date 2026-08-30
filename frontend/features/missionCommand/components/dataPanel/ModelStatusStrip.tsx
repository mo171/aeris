// features/missionCommand/components/dataPanel/ModelStatusStrip.tsx — health of the specialist model fleet.
//
// what  : A collapsible summary of which specialist models are available, with per-model latency and queue
//         depth on expand.
// where : The bottom section of the Data & Context panel.
// how   : Collapsed by default and summarised as counts, because the operator only needs the detail when
//         something is wrong. It sits in the data panel rather than being hidden in the Model Observatory
//         because routing depends on it: asking a change-detection question while the change detector is
//         offline should be visible before the question is asked, not after it fails.

"use client";

import { ChevronDown, Cpu } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { GlowDot, type GlowDotTone } from "@/components/sharedUI/dumbComponent/GlowDot";
import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { ErrorState } from "@/components/sharedUI/functionalComponent/feedback/ErrorState";
import { getModel } from "@/lib/constants/models";
import { ROUTES } from "@/lib/constants/routes";
import { formatDurationMs } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import { useModelStatus } from "../../hooks/use-model-status";
import type { ModelHealth } from "../../types/model.types";

const HEALTH_TONE: Record<ModelHealth, GlowDotTone> = {
  online: "green",
  warming: "blue",
  degraded: "amber",
  offline: "red",
};

export function ModelStatusStrip() {
  const { models, onlineCount, degradedCount, offlineCount, isLoading, error, refetch } =
    useModelStatus();
  const [isExpanded, setIsExpanded] = useState(false);

  if (error) {
    return (
      <section className="shrink-0 border-t border-border-soft">
        <ErrorState error={error} onRetry={refetch} className="py-6" />
      </section>
    );
  }

  return (
    <section className="shrink-0 border-t border-border-soft pt-2 pb-1">
      <SectionHeader
        title="Model fleet"
        trailing={
          <button
            type="button"
            onClick={() => setIsExpanded((previous) => !previous)}
            aria-expanded={isExpanded}
            className="flex items-center gap-1 rounded-sm px-1 text-muted-foreground transition-colors duration-fast hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <span className="font-mono text-[10px]">{isExpanded ? "Hide" : "Detail"}</span>
            <ChevronDown
              className={cn(
                "size-3 transition-transform duration-base ease-expo",
                isExpanded && "rotate-180",
              )}
              aria-hidden="true"
            />
          </button>
        }
      />

      <div className="flex items-center gap-3 px-3 pt-1.5 pb-1">
        {isLoading ? (
          <span className="font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
            Checking fleet…
          </span>
        ) : (
          <>
            <FleetCount tone="green" label="online" count={onlineCount} />
            <FleetCount tone="amber" label="degraded" count={degradedCount} />
            <FleetCount tone="red" label="offline" count={offlineCount} />
            <Cpu className="ml-auto size-3.5 text-muted-foreground/60" aria-hidden="true" />
          </>
        )}
      </div>

      {isExpanded ? (
        <>
          <ul className="max-h-40 overflow-y-auto px-3 pb-1">
            {models.map((model) => (
              <li
                key={model.id}
                className="flex items-center gap-2 border-t border-border-soft/60 py-1.5 first:border-t-0"
              >
                <GlowDot tone={HEALTH_TONE[model.health]} isPulsing={model.health === "warming"} />
                <span className="min-w-0 flex-1 truncate text-[10px] text-foreground">
                  {getModel(model.id)?.name ?? model.id}
                </span>
                <span className="shrink-0 font-mono text-[9px] text-muted-foreground">
                  v{model.version}
                </span>
                <span
                  className="shrink-0 font-mono text-[9px] text-muted-foreground"
                  title="Median latency"
                >
                  {formatDurationMs(model.medianLatencyMs)}
                </span>
                {model.queueDepth > 0 ? (
                  <span className="shrink-0 font-mono text-[9px] text-aeris-amber" title="Queue depth">
                    ×{model.queueDepth}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>

          {/* This strip answers "is it up". What each model is, and why the router picks it, is the
              Observatory's job — so the detail view ends by pointing at it rather than restating it. */}
          <Link
            href={ROUTES.MODEL_OBSERVATORY}
            className="mx-3 mb-1 block rounded-sm py-1 font-mono text-[9px] tracking-wide text-muted-foreground uppercase transition-colors duration-fast hover:text-aeris-teal focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            Open the Model Observatory →
          </Link>
        </>
      ) : null}

    </section>
  );
}

function FleetCount({
  tone,
  label,
  count,
}: {
  tone: GlowDotTone;
  label: string;
  count: number;
}) {
  return (
    <span className="flex items-center gap-1.5">
      <GlowDot tone={count > 0 ? tone : "neutral"} />
      <span className="font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
        {count} {label}
      </span>
    </span>
  );
}
