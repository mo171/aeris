// features/investigation/components/inputsPanel/RampOverrideSelect.tsx — per-layer color ramp override.
//
// what  : A compact select dropdown allowing the operator to change the color ramp used to render an
//         evidence layer — for instance, switching a vegetation index from the default green ramp to a
//         diverging palette to emphasise loss.
// where : Rendered inside EvidenceLayerRow or the LayerMetadataDrawer.
// how   : The set of available ramps is the closed `colorRampIdSchema` enum from layer.schema.ts.
//         The override is stored as view state in the investigation store, not written back to the
//         layer descriptor — this is an operator display preference, not a data mutation.

"use client";

import { Palette } from "lucide-react";

import { cn } from "@/lib/utils";

/** The same closed set as colorRampIdSchema, kept inline so this component has no schema import. */
const RAMP_OPTIONS = [
  { id: "true-color", label: "True Color", swatch: "bg-gradient-to-r from-emerald-800 via-amber-600 to-sky-400" },
  { id: "sar-grayscale", label: "SAR Grayscale", swatch: "bg-gradient-to-r from-zinc-900 to-zinc-100" },
  { id: "change-diverging", label: "Change (diverging)", swatch: "bg-gradient-to-r from-blue-500 via-zinc-100 to-red-500" },
  { id: "index-vegetation", label: "Vegetation Index", swatch: "bg-gradient-to-r from-amber-800 via-yellow-400 to-green-600" },
  { id: "confidence-magma", label: "Confidence (magma)", swatch: "bg-gradient-to-r from-zinc-900 via-rose-600 to-amber-300" },
  { id: "detection-teal", label: "Detection (teal)", swatch: "bg-gradient-to-r from-zinc-800 to-teal-400" },
  { id: "mask-amber", label: "Mask (amber)", swatch: "bg-gradient-to-r from-zinc-800 to-amber-400" },
  { id: "artefact-neutral", label: "Artefact (neutral)", swatch: "bg-gradient-to-r from-zinc-700 to-zinc-400" },
] as const;

interface RampOverrideSelectProps {
  currentRampId: string;
  onRampChange: (rampId: string) => void;
  className?: string;
}

export function RampOverrideSelect({
  currentRampId,
  onRampChange,
  className,
}: RampOverrideSelectProps) {
  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      <Palette className="size-3 shrink-0 text-muted-foreground" />
      <select
        value={currentRampId}
        onChange={(e) => onRampChange(e.target.value)}
        className="min-w-0 flex-1 truncate rounded border border-border-soft bg-surface-2/60 px-1.5 py-0.5 font-mono text-[10px] text-foreground focus:border-aeris-teal focus:outline-none focus:ring-1 focus:ring-aeris-teal/30"
        aria-label="Color ramp"
      >
        {RAMP_OPTIONS.map((ramp) => (
          <option key={ramp.id} value={ramp.id}>
            {ramp.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Preview-only: renders the ramp swatch for a given ramp id. */
export function RampSwatch({ rampId, className }: { rampId: string; className?: string }) {
  const ramp = RAMP_OPTIONS.find((r) => r.id === rampId);
  return (
    <div
      className={cn("h-2 w-full rounded-full", ramp?.swatch ?? "bg-zinc-600", className)}
      title={ramp?.label ?? rampId}
    />
  );
}
