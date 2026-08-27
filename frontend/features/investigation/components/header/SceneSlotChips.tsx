// features/investigation/components/header/SceneSlotChips.tsx — the scenes this investigation is built on.

"use client";

import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { formatAbsoluteDate } from "@/lib/formatters";

import type { InvestigationSceneSlot } from "../../types/investigation.types";

interface SceneSlotChipsProps {
  sceneSlots: InvestigationSceneSlot[];
  onFocusScene: (slot: InvestigationSceneSlot) => void;
}

export function SceneSlotChips({ sceneSlots, onFocusScene }: SceneSlotChipsProps) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
      {sceneSlots.map((slot) => (
        <button
          key={slot.sceneId}
          type="button"
          onClick={() => onFocusScene(slot)}
          title={`${slot.name} · ${slot.coordinateReferenceSystem}`}
          className="flex items-center gap-1.5 rounded-sm transition-colors duration-fast hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <Chip tone={slot.modality === "sar" ? "blue" : "teal"}>{slot.role.toUpperCase()}</Chip>
          <span className="font-mono text-[10px] whitespace-nowrap text-muted-foreground">
            {formatAbsoluteDate(slot.capturedAt)} · {slot.sensorPlatform} · {slot.modality}
          </span>
        </button>
      ))}
    </div>
  );
}
