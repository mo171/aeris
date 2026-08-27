// features/investigation/components/viewer/RegionPromptPopover.tsx — "ask this region".
//
// what  : A prompt anchored to the region the operator just drew, offering questions scoped to it.
// where : Rendered by InvestigationScreen over the full scene area whenever a region exists.
// how   : Anchored to where the drag ended rather than recomputed from the geometry every frame. The
//         prompt should stay where the operator finished; a camera that keeps drifting would otherwise
//         drag the popover around with it and make the tool feel unstable.
//
//         The suggestions come from the backend, because what is worth asking about a polygon depends on
//         which imagery covers it and what has already been analysed there. Offering a fixed list would be
//         guessing, and guessing wrong in front of an analyst is expensive.

"use client";

import { Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { INVESTIGATION_LAYOUT } from "@/lib/constants/investigation";
import { formatCoordinates } from "@/lib/formatters";

import type { RegionSuggestion } from "../../types/analysis.types";
import type { StageDrawnRegion } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";

interface RegionPromptPopoverProps {
  region: StageDrawnRegion;
  suggestions: RegionSuggestion[];
  isLoading: boolean;
  onAsk: (prompt: string) => void;
  onDismiss: () => void;
}

export function RegionPromptPopover({
  region,
  suggestions,
  isLoading,
  onAsk,
  onDismiss,
}: RegionPromptPopoverProps) {
  const centreLatitude = (region.bounds.north + region.bounds.south) / 2;
  const centreLongitude = (region.bounds.east + region.bounds.west) / 2;

  return (
    <div
      style={{
        left: region.screenAnchor.x + INVESTIGATION_LAYOUT.regionPromptOffsetPx,
        top: region.screenAnchor.y + INVESTIGATION_LAYOUT.regionPromptOffsetPx,
      }}
      className="pointer-events-auto absolute z-20 w-64 rounded-md border border-aeris-teal/40 bg-surface-2/95 p-2 shadow-lg backdrop-blur-md"
    >
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="aeris-technical text-aeris-teal">Ask this region</h3>
          <p className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">
            {region.areaHectares >= 100
              ? `${(region.areaHectares / 100).toFixed(2)} km²`
              : `${region.areaHectares.toFixed(2)} ha`}
            {" · "}
            {formatCoordinates(centreLatitude, centreLongitude)}
          </p>
        </div>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-label="Discard this region"
          onClick={onDismiss}
        >
          <X />
        </Button>
      </header>

      <div className="mt-2 flex flex-col gap-1">
        {isLoading ? (
          <span className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
            <Spinner className="size-3" />
            Working out what is worth asking here…
          </span>
        ) : suggestions.length === 0 ? (
          <p className="py-1 text-xs text-muted-foreground">
            No scoped suggestions. Type a question and it will still be limited to this region.
          </p>
        ) : (
          suggestions.map((suggestion) => (
            <Button
              key={suggestion.id}
              type="button"
              size="sm"
              variant="ghost"
              className="h-auto justify-start py-1.5 text-left whitespace-normal"
              onClick={() => onAsk(suggestion.prompt)}
            >
              <Search className="shrink-0" />
              <span className="text-xs">{suggestion.label}</span>
            </Button>
          ))
        )}
      </div>
    </div>
  );
}
