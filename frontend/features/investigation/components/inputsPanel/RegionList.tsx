// features/investigation/components/inputsPanel/RegionList.tsx — the areas of interest the operator drew.
//
// what  : Lists every committed region with its measured area, lets one be made the active scope, and
//         removes them.
// where : A section of InputsPanel.
// how   : Several regions can exist at once because an analyst comparing two sites needs both on screen.
//         Exactly one is active, and only that one scopes the next question — an interface where every
//         drawn shape silently contributes to the query is one where the operator cannot tell what they
//         actually asked.
//
//         Each row states its measured area, because that number is what the backend crops to and what
//         the answer will quote. Seeing it in the list is how an operator notices they drew 4,000
//         hectares when they meant 40.

"use client";

import { Crosshair, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { StageDrawnRegion } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";

const MODE_LABEL: Record<StageDrawnRegion["mode"], string> = {
  rectangle: "Box",
  polygon: "Polygon",
  freehand: "Traced",
  circle: "Radius",
};

interface RegionListProps {
  regions: readonly StageDrawnRegion[];
  activeRegionId: string | null;
  onSelect: (regionId: string | null) => void;
  onRemove: (regionId: string) => void;
}

export function RegionList({ regions, activeRegionId, onSelect, onRemove }: RegionListProps) {
  return (
    <ul className="flex flex-col gap-1">
      {regions.map((region) => {
        const isActive = region.id === activeRegionId;

        return (
          <li key={region.id}>
            <div
              className={cn(
                "flex items-center gap-1.5 rounded-md border px-2 py-1.5 transition-colors duration-fast",
                isActive
                  ? "border-aeris-teal/60 bg-aeris-teal/5"
                  : "border-border-soft bg-surface-2/40",
              )}
            >
              <button
                type="button"
                onClick={() => onSelect(isActive ? null : region.id)}
                aria-pressed={isActive}
                className="flex min-w-0 flex-1 items-center gap-1.5 rounded-sm text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <Crosshair
                  className={cn(
                    "size-3 shrink-0",
                    isActive ? "text-aeris-teal" : "text-muted-foreground",
                  )}
                  aria-hidden="true"
                />
                <span className="min-w-0">
                  <span className="block truncate text-xs text-foreground">
                    {MODE_LABEL[region.mode]}
                  </span>
                  <span className="block font-mono text-[10px] tabular-nums text-muted-foreground">
                    {region.areaHectares >= 100
                      ? `${(region.areaHectares / 100).toFixed(2)} km²`
                      : `${region.areaHectares.toFixed(2)} ha`}
                    {" · "}
                    {region.perimeterMeters >= 1_000
                      ? `${(region.perimeterMeters / 1_000).toFixed(2)} km`
                      : `${Math.round(region.perimeterMeters)} m`}
                  </span>
                </span>
              </button>

              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                aria-label="Remove this region"
                onClick={() => onRemove(region.id)}
              >
                <Trash2 />
              </Button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
