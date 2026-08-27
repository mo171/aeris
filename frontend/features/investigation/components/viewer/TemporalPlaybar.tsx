// features/investigation/components/viewer/TemporalPlaybar.tsx — what the comparator is comparing.
//
// what  : Labels the two sides of the split with their scenes and dates, and switches what is being
//         compared.
// where : Rendered into the centre column of InvestigationScreen, beneath the tool cluster.
// how   : Naming both sides matters more than it looks. A split screen with no labels leaves the operator
//         guessing which half is the earlier observation, and a change-detection answer read off the wrong
//         side is worse than no answer at all.
//
//         Switching the binding is what makes pages 3 and 4 configurations of this workspace: temporal
//         compares T0 against T1, cross-modal compares SAR against optical, and nothing else changes.

"use client";

import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { Button } from "@/components/ui/button";
import { COMPARATOR_BINDING } from "@/lib/constants/investigation";
import { formatAbsoluteDate } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import { useInvestigationStore } from "../../store/investigation-store";
import type { InvestigationSceneSlot, WorkspaceMode } from "../../types/investigation.types";

const BINDING_LABEL: Record<WorkspaceMode, string> = {
  temporal: "Temporal",
  crossModal: "Cross-modal",
};

interface TemporalPlaybarProps {
  sceneSlots: InvestigationSceneSlot[];
}

export function TemporalPlaybar({ sceneSlots }: TemporalPlaybarProps) {
  const comparatorBinding = useInvestigationStore((state) => state.comparatorBinding);
  const setComparatorBinding = useInvestigationStore((state) => state.setComparatorBinding);

  const binding = COMPARATOR_BINDING[comparatorBinding];
  const slotFor = (role: string) => sceneSlots.find((slot) => slot.role === role) ?? null;
  const leftSlot = slotFor(binding.left);
  const rightSlot = slotFor(binding.right);

  const hasCrossModal = sceneSlots.some((slot) => slot.role === "sar");

  return (
    <div className="pointer-events-auto flex items-center gap-3 rounded-md border border-border bg-surface-2/70 px-2.5 py-1.5 backdrop-blur-md">
      <SideLabel align="left" slot={leftSlot} />

      <span className="h-3 w-px bg-border" aria-hidden="true" />

      <div className="flex items-center gap-1">
        {(Object.keys(BINDING_LABEL) as WorkspaceMode[]).map((mode) => (
          <Button
            key={mode}
            type="button"
            size="sm"
            variant="ghost"
            disabled={mode === "crossModal" && !hasCrossModal}
            onClick={() => setComparatorBinding(mode)}
            className={cn(
              "h-6 px-2 font-mono text-[10px] tracking-wide",
              comparatorBinding === mode ? "text-aeris-teal" : "text-muted-foreground",
            )}
          >
            {BINDING_LABEL[mode]}
          </Button>
        ))}
      </div>

      <span className="h-3 w-px bg-border" aria-hidden="true" />

      <SideLabel align="right" slot={rightSlot} />
    </div>
  );
}

function SideLabel({
  align,
  slot,
}: {
  align: "left" | "right";
  slot: InvestigationSceneSlot | null;
}) {
  if (!slot) {
    return (
      <span className="aeris-technical text-muted-foreground/60">
        {align === "left" ? "No left scene" : "No right scene"}
      </span>
    );
  }

  return (
    <span className={cn("flex items-center gap-1.5", align === "right" && "flex-row-reverse")}>
      <Chip tone={slot.modality === "sar" ? "blue" : "teal"}>{slot.role.toUpperCase()}</Chip>
      <span className="font-mono text-[10px] whitespace-nowrap text-muted-foreground">
        {formatAbsoluteDate(slot.capturedAt)}
      </span>
    </span>
  );
}
