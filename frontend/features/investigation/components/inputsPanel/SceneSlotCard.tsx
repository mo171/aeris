// features/investigation/components/inputsPanel/SceneSlotCard.tsx — one scene attached to the investigation.

"use client";

import { Radar, Satellite } from "lucide-react";

import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { formatAbsoluteDate, formatGroundSampleDistance } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import type { InvestigationSceneSlot, SceneRole } from "../../types/investigation.types";

const ROLE_LABEL: Record<SceneRole, string> = {
  t0: "T0",
  t1: "T1",
  sar: "SAR",
  aux: "AUX",
};

interface SceneSlotCardProps {
  slot: InvestigationSceneSlot;
  isVisible: boolean;
  onToggleVisibility: () => void;
  onFocus: () => void;
}

export function SceneSlotCard({
  slot,
  isVisible,
  onToggleVisibility,
  onFocus,
}: SceneSlotCardProps) {
  const Icon = slot.modality === "sar" ? Radar : Satellite;

  return (
    <div
      className={cn(
        "rounded-md border border-border-soft bg-surface-2/50 p-2 transition-opacity duration-base",
        !isVisible && "opacity-50",
      )}
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          onClick={onToggleVisibility}
          aria-pressed={isVisible}
          aria-label={isVisible ? `Hide ${slot.name}` : `Show ${slot.name}`}
          className="mt-0.5 shrink-0 rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <Icon
            className={cn("size-3.5", isVisible ? "text-aeris-teal" : "text-muted-foreground")}
            aria-hidden="true"
          />
        </button>

        <button
          type="button"
          onClick={onFocus}
          className="min-w-0 flex-1 rounded-sm text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <span className="flex items-center gap-1.5">
            <Chip tone={slot.modality === "sar" ? "blue" : "teal"}>{ROLE_LABEL[slot.role]}</Chip>
            <span className="truncate text-xs font-medium text-foreground">{slot.name}</span>
          </span>
          <span className="mt-1 block font-mono text-[10px] text-muted-foreground">
            {formatAbsoluteDate(slot.capturedAt)} · {slot.sensorPlatform} ·{" "}
            {formatGroundSampleDistance(slot.groundSampleDistanceMeters)}
          </span>
          <span className="block font-mono text-[10px] text-muted-foreground/70">
            {slot.coordinateReferenceSystem} ·{" "}
            {slot.cloudCoverPercentage === null
              ? "Cloud n/a"
              : `${Math.round(slot.cloudCoverPercentage)}% cloud`}
          </span>
        </button>
      </div>
    </div>
  );
}
