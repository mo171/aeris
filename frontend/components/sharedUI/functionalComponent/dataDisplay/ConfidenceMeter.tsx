// components/sharedUI/functionalComponent/dataDisplay/ConfidenceMeter.tsx — confidence as a banded bar.
//
// what  : Renders a 0–1 confidence value as a labelled bar whose colour reflects the confidence band.
// where : Used on assistant answers, mission cards, and later in the Evidence Explorer.
// how   : Every AERIS claim carries a confidence, and the operator must be able to read it without doing
//         arithmetic. The colour bands are fixed here so "high confidence" means the same thing on every
//         surface — an inconsistent threshold across screens would be actively misleading.

import { cn } from "@/lib/utils";

const HIGH_CONFIDENCE_THRESHOLD = 0.85;
const MODERATE_CONFIDENCE_THRESHOLD = 0.6;

interface ConfidenceMeterProps {
  /** 0–1. Null renders an explicit "not asserted" state rather than an empty bar. */
  value: number | null;
  showLabel?: boolean;
  className?: string;
}

export function ConfidenceMeter({ value, showLabel = true, className }: ConfidenceMeterProps) {
  if (value === null) {
    return (
      <span className={cn("aeris-technical", className)} title="No confidence asserted">
        Confidence not asserted
      </span>
    );
  }

  const percentage = Math.round(value * 100);
  const band = resolveBand(value);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div
        className="h-1 w-16 overflow-hidden rounded-full bg-muted"
        role="meter"
        aria-valuenow={percentage}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Answer confidence"
      >
        <div
          className={cn("h-full rounded-full transition-[width] duration-slow", band.barClass)}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {showLabel ? (
        <span className={cn("font-mono text-[10px] tracking-wide", band.textClass)}>
          {percentage}% {band.label}
        </span>
      ) : null}
    </div>
  );
}

function resolveBand(value: number) {
  if (value >= HIGH_CONFIDENCE_THRESHOLD) {
    return { label: "HIGH", barClass: "bg-aeris-green", textClass: "text-aeris-green" };
  }
  if (value >= MODERATE_CONFIDENCE_THRESHOLD) {
    return { label: "MODERATE", barClass: "bg-aeris-amber", textClass: "text-aeris-amber" };
  }
  return { label: "LOW", barClass: "bg-aeris-red", textClass: "text-aeris-red" };
}
