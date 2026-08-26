// features/missionCommand/components/dataPanel/ImageryCatalogItem.tsx — one scene row in the catalogue.
//
// what  : Renders a scene's identity and the acquisition metadata that decides whether it can answer a
//         given question, with a selection state.
// where : Rendered by ImageryCatalogList inside the virtualiser.
// how   : Which metadata is shown is a product decision, not a layout one. Modality, ground sample
//         distance, cloud cover and temporal role are exactly the four facts that determine whether a
//         scene is usable for an analysis, so they are always visible rather than hidden behind an expand.
//
//         Memoised because the virtualiser re-renders its window on every scroll frame; without it,
//         scrolling would re-render every visible row continuously.

"use client";

import { memo } from "react";
import { Check } from "lucide-react";

import { Chip, type ChipTone } from "@/components/sharedUI/dumbComponent/Chip";
import {
  formatAbsoluteDate,
  formatBytes,
  formatCoordinates,
  formatGroundSampleDistance,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";

import type { ImageryScene, SensorModality } from "../../types/imagery.types";

const MODALITY_TONE: Record<SensorModality, ChipTone> = {
  optical: "teal",
  sar: "blue",
  multispectral: "green",
  hyperspectral: "amber",
};

const MODALITY_LABEL: Record<SensorModality, string> = {
  optical: "Optical",
  sar: "SAR",
  multispectral: "MSI",
  hyperspectral: "HSI",
};

interface ImageryCatalogItemProps {
  scene: ImageryScene;
  isSelected: boolean;
  onToggleSelect: (sceneId: string) => void;
  onLocate: (scene: ImageryScene) => void;
}

export const ImageryCatalogItem = memo(function ImageryCatalogItem({
  scene,
  isSelected,
  onToggleSelect,
  onLocate,
}: ImageryCatalogItemProps) {
  const isUnavailable = scene.processingState !== "ready";

  return (
    <div className="px-2 pb-1.5">
      <button
        type="button"
        onClick={() => onToggleSelect(scene.id)}
        onDoubleClick={() => onLocate(scene)}
        aria-pressed={isSelected}
        className={cn(
          "group/scene w-full rounded-md border px-2.5 py-2 text-left transition-colors duration-fast",
          isSelected
            ? "border-aeris-teal/55 bg-aeris-teal/[0.08]"
            : "border-border-soft bg-surface-2/40 hover:border-border hover:bg-surface-3/50",
          isUnavailable && "opacity-60",
        )}
      >
        <div className="flex items-start gap-2">
          <span
            className={cn(
              "mt-0.5 flex size-3.5 shrink-0 items-center justify-center rounded-[3px] border transition-colors duration-fast",
              isSelected
                ? "border-aeris-teal bg-aeris-teal text-aeris-black"
                : "border-border group-hover/scene:border-aeris-teal/50",
            )}
            aria-hidden="true"
          >
            {isSelected ? <Check className="size-2.5" strokeWidth={3.5} /> : null}
          </span>

          <span className="min-w-0 flex-1">
            <span className="block truncate text-[11px] font-medium text-foreground">
              {scene.name}
            </span>
            <span className="mt-0.5 block truncate font-mono text-[10px] text-muted-foreground">
              {scene.sensorPlatform} · {formatCoordinates(scene.centroid.latitude, scene.centroid.longitude)}
            </span>
          </span>
        </div>

        <div className="mt-1.5 flex flex-wrap items-center gap-1 pl-5.5">
          <Chip tone={MODALITY_TONE[scene.modality]}>{MODALITY_LABEL[scene.modality]}</Chip>
          <Chip title="Ground sample distance">
            {formatGroundSampleDistance(scene.groundSampleDistanceMeters)}
          </Chip>
          {scene.cloudCoverPercentage === null ? (
            <Chip tone="blue" title="SAR is unaffected by cloud">
              Cloud n/a
            </Chip>
          ) : (
            <Chip
              tone={scene.cloudCoverPercentage > 40 ? "amber" : "neutral"}
              title="Cloud cover"
            >
              Cloud {scene.cloudCoverPercentage.toFixed(0)}%
            </Chip>
          )}
          {scene.temporalRole !== "single" ? (
            <Chip tone="teal" title="Position in a bi-temporal pair">
              {scene.temporalRole.toUpperCase()}
            </Chip>
          ) : null}
          {isUnavailable ? (
            <Chip tone={scene.processingState === "failed" ? "red" : "amber"}>
              {scene.processingState}
            </Chip>
          ) : null}
        </div>

        <div className="mt-1 flex items-center justify-between pl-5.5 font-mono text-[9px] tracking-wide text-muted-foreground/75 uppercase">
          <span>{formatAbsoluteDate(scene.capturedAt)}</span>
          <span>
            {scene.bandCount} band{scene.bandCount === 1 ? "" : "s"} · {formatBytes(scene.fileSizeBytes)}
          </span>
        </div>
      </button>
    </div>
  );
});
