// features/investigation/components/answerPanel/MetricStat.tsx — one computed figure from a claim.

"use client";

import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { useCountUp } from "@/hooks/use-count-up";
import { cn } from "@/lib/utils";

import type { ClaimMetric } from "../../types/evidence.types";

const DIRECTION_PRESENTATION = {
  increase: { icon: ArrowUpRight, className: "text-aeris-teal" },
  decrease: { icon: ArrowDownRight, className: "text-aeris-amber" },
  neutral: { icon: Minus, className: "text-muted-foreground" },
} as const;

interface MetricStatProps {
  metric: ClaimMetric;
  className?: string;
}

export function MetricStat({ metric, className }: MetricStatProps) {
  const animatedValue = useCountUp(metric.value);
  const { icon: DirectionIcon, className: directionClassName } =
    DIRECTION_PRESENTATION[metric.direction];

  return (
    <div className={cn("flex flex-col gap-0.5", className)}>
      <span className="flex items-baseline gap-1">
        <DirectionIcon className={cn("size-3.5 shrink-0", directionClassName)} aria-hidden="true" />
        <span className="font-mono text-2xl leading-none tracking-tight tabular-nums text-foreground">
          {animatedValue.toFixed(metric.precision)}
        </span>
        <span className="font-mono text-xs text-muted-foreground">{metric.unit}</span>
      </span>
      <span className="aeris-technical truncate">{metric.label}</span>
    </div>
  );
}
