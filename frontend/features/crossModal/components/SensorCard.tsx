// features/crossModal/components/SensorCard.tsx — one sensor, stated on its own terms.
//
// what  : A sensor's scene, what it physically measures, what it is blind to, how much of the area it
//         could not read, its findings count, and a control to view it alone on the stage.
// where : Two of these fill the Lab's left column — optical above, radar below.
// how   : STRUCTURALLY IDENTICAL BY CONSTRUCTION, and that is the whole point of it being one component
//         used twice rather than two components. The moment one column gains an affordance the other
//         lacks, the eye starts reading a hierarchy that is not in the data, and the comparison the page
//         exists for becomes a comparison of two interfaces instead of two sensors.
//
//         The palettes are the one deliberate asymmetry: optical renders in the system accent, radar
//         stays achromatic. Tinting a radar product in optical colours would be a lie about what produced
//         it, and it is exactly the confusion the design document warns about — "SAR outputs must never
//         be interpreted with optical intuition".
//
//         `blindTo` is shown at rest, not on hover. What a sensor CANNOT see is the fact an analyst needs
//         before they read a finding, not after they have doubted one.

"use client";

import { Eye, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SENSOR_PHRASING, SENSOR_PLATFORMS, type SensorId } from "@/lib/constants/cross-modal";
import { formatAbsoluteDate, formatPercentage } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import type { SensorRun } from "../types/cross-modal.types";

interface SensorCardProps {
  sensor: SensorId;
  run: SensorRun | null;
  findingCount: number;
  isSoloed: boolean;
  onToggleSolo: () => void;
  /** Radar only. Rendered as a slot so the two cards stay one component. */
  children?: React.ReactNode;
}

export function SensorCard({
  sensor,
  run,
  findingCount,
  isSoloed,
  onToggleSolo,
  children,
}: SensorCardProps) {
  const platform = SENSOR_PLATFORMS[sensor];
  const phrasing = SENSOR_PHRASING[sensor];
  const isRadar = sensor === "radar";
  const SoloIcon = isSoloed ? Eye : EyeOff;

  if (!run) {
    return (
      <section className="rounded-md border border-dashed border-border-soft px-2.5 py-2.5">
        <p className={cn("aeris-technical", isRadar ? "text-muted-foreground" : "text-aeris-teal")}>
          {platform.label}
        </p>
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
          No {platform.platform} observation is attached. Without it there is nothing to corroborate
          against, and every optical finding stands on a single sensor.
        </p>
      </section>
    );
  }

  return (
    <section
      className={cn(
        "rounded-md border px-2.5 py-2 transition-colors duration-base",
        isSoloed ? "border-aeris-teal/45 bg-aeris-teal/5" : "border-border-soft bg-surface-2/30",
      )}
    >
      <header className="flex items-center gap-1.5">
        <span
          className="size-2 shrink-0 rounded-full"
          style={{ backgroundColor: isRadar ? "#C3CAD6" : "#00E5FF" }}
          aria-hidden="true"
        />
        <span className={cn("aeris-technical", isRadar ? "text-[#C3CAD6]" : "text-aeris-teal")}>
          {platform.label}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground">{platform.platform}</span>

        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-pressed={isSoloed}
          aria-label={isSoloed ? `Show both sensors` : `Show ${platform.label} alone`}
          onClick={onToggleSolo}
          className="ml-auto"
        >
          <SoloIcon className={isSoloed ? "text-aeris-teal" : undefined} />
        </Button>
      </header>

      <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
        {formatAbsoluteDate(run.capturedAt)} · {run.modelId}@{run.modelVersion}
      </p>

      <dl className="mt-2 flex flex-col gap-1">
        <Row label="Measures">{platform.measures}</Row>
        <Row label="Reads">{platform.reads}</Row>
        {/* Stated at rest. What a sensor cannot see is what an analyst needs BEFORE a finding. */}
        <Row label="Blind to" tone="warning">
          {platform.blindTo}
        </Row>
      </dl>

      {children}

      <footer className="mt-2 flex items-center gap-3 border-t border-border-soft pt-1.5">
        <Stat label="findings" value={String(findingCount)} />
        <Stat
          label="unreadable"
          value={formatPercentage(run.obscuredFraction)}
          tone={run.obscuredFraction > 0.15 ? "warning" : "default"}
        />
        <Stat
          label="confidence"
          value={run.confidence === null ? "—" : formatPercentage(run.confidence)}
        />
      </footer>

      <p className="mt-1.5 font-mono text-[9px] leading-relaxed text-muted-foreground/70">
        {phrasing.caution}
      </p>
    </section>
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
      <dt className="w-16 shrink-0 font-mono text-[9px] tracking-wide text-muted-foreground/50 uppercase">
        {label}
      </dt>
      <dd
        className={cn(
          "min-w-0 flex-1 text-[10px] leading-relaxed",
          tone === "warning" ? "text-aeris-amber/80" : "text-muted-foreground",
        )}
      >
        {children}
      </dd>
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "warning";
}) {
  return (
    <span className="flex items-baseline gap-1">
      <span
        className={cn(
          "font-mono text-[11px] tabular-nums",
          tone === "warning" ? "text-aeris-amber" : "text-foreground",
        )}
      >
        {value}
      </span>
      <span className="font-mono text-[9px] tracking-wide text-muted-foreground/60 uppercase">
        {label}
      </span>
    </span>
  );
}
