// features/missionCommand/components/globe/GlobeControls.tsx — the floating camera controls over the globe.
//
// what  : One bottom bar carrying the marker legend and the zoom / rotation / reset controls.
// where : Rendered by MissionCommandScreen into the centre column of the panel overlay — the free space
//         between the data and assistant panels.
// how   : It is positioned inside that centre column rather than against the viewport on purpose. The
//         legend was previously anchored to the viewport's bottom-left, which put it underneath the Data
//         & Context panel where it was invisible. Living in the centre column means the controls can only
//         ever occupy space no panel is using, at any panel width.
//
//         Legend and controls share a single row rather than floating independently, so they cannot
//         collide with each other as the column narrows.
//
//         They act through the GlobeViewerHandle published in the feature store, which is the same path
//         the command bus uses. A button and its equivalent command therefore cannot diverge in
//         behaviour, because they are literally the same call. That handle's presence is also the
//         readiness signal — the bar fades in once the globe has published itself.

"use client";

import { Building2, Images, Minus, Orbit, Plus, RotateCcw, Slash } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { GlowDot, type GlowDotTone } from "@/components/sharedUI/dumbComponent/GlowDot";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { GLOBE_CAMERA } from "@/lib/constants/globe";
import { cn } from "@/lib/utils";

import { useMissionCommandStore } from "../../store/mission-command-store";
import type { MissionStatus } from "../../types/mission.types";
import type { StageBuildingMode } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";

const MARKER_LEGEND: readonly { status: MissionStatus; label: string; tone: GlowDotTone }[] = [
  { status: "alert", label: "Alert", tone: "red" },
  { status: "active", label: "Active", tone: "teal" },
  { status: "monitoring", label: "Monitoring", tone: "blue" },
  { status: "archived", label: "Archived", tone: "neutral" },
];

const BUILDING_MODES: readonly {
  id: StageBuildingMode;
  label: string;
  icon: typeof Building2;
  hint: string;
}[] = [
    { id: "none", label: "Flat", icon: Slash, hint: "No buildings — imagery draped on terrain only" },
    {
      id: "massing",
      label: "Massing",
      icon: Building2,
      hint: "OpenStreetMap footprints extruded to real heights. Free, and your imagery stays visible underneath.",
    },
    {
      id: "photorealistic",
      label: "Photoreal",
      icon: Images,
      hint: "Google photogrammetry — textured 3D. Metered per tile, and it replaces the ground.",
    },
  ];

export function GlobeControls() {
  const globeViewer = useMissionCommandStore((state) => state.globeViewer);
  const isAutoRotating = useMissionCommandStore((state) => state.isAutoRotating);
  const setIsAutoRotating = useMissionCommandStore((state) => state.setIsAutoRotating);
  const [buildingMode, setBuildingMode] = useState<StageBuildingMode>("none");

  const isGlobeReady = globeViewer !== null;

  useEffect(() => {
    if (globeViewer) {
      setBuildingMode(globeViewer.getBuildingMode());

      // Apply the persisted auto-rotation state when the globe initializes
      const persistedAutoRotate = useMissionCommandStore.getState().isAutoRotating;
      if (globeViewer.isAutoRotating() !== persistedAutoRotate) {
        globeViewer.setAutoRotate(persistedAutoRotate);
      }
    }
  }, [globeViewer]);

  const handleAutoRotateToggle = () => {
    const next = !isAutoRotating;
    setIsAutoRotating(next);
    globeViewer?.setAutoRotate(next);
  };

  const handleBuildingModeSelect = (mode: StageBuildingMode) => {
    setBuildingMode(mode);
    globeViewer?.setBuildingMode(mode);
  };

  return (
    <div
      className={cn(
        "absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 transition-opacity duration-slow ease-expo",
        isGlobeReady ? "opacity-100" : "pointer-events-none opacity-0",
      )}
    >
      <div className="pointer-events-none flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-border bg-surface-2/70 px-2.5 py-1.5 backdrop-blur-md">
        <span className="aeris-technical">Markers</span>
        {MARKER_LEGEND.map((entry) => (
          <span key={entry.status} className="flex items-center gap-1.5">
            <GlowDot tone={entry.tone} isPulsing={entry.status === "alert"} />
            <span className="font-mono text-[10px] tracking-wide text-muted-foreground">
              {entry.label}
            </span>
          </span>
        ))}
      </div>

      <div className="pointer-events-auto flex shrink-0 items-center gap-1 rounded-md border border-border bg-surface-2/80 p-1 backdrop-blur-md">
        <GlobeControlButton
          label="Zoom in"
          onClick={() => globeViewer?.zoomByFactor(GLOBE_CAMERA.zoomInFactor)}
        >
          <Plus />
        </GlobeControlButton>
        <GlobeControlButton
          label="Zoom out"
          onClick={() => globeViewer?.zoomByFactor(GLOBE_CAMERA.zoomOutFactor)}
        >
          <Minus />
        </GlobeControlButton>

        <span className="mx-0.5 h-4 w-px bg-border" aria-hidden="true" />

        <GlobeControlButton
          label={isAutoRotating ? "Stop rotation" : "Resume rotation"}
          isActive={isAutoRotating}
          onClick={handleAutoRotateToggle}
        >
          <Orbit />
        </GlobeControlButton>
        <GlobeControlButton label="Reset view" onClick={() => globeViewer?.resetView()}>
          <RotateCcw />
        </GlobeControlButton>

        <span className="mx-0.5 h-4 w-px bg-border" aria-hidden="true" />

        {BUILDING_MODES.map(({ id, label, icon: Icon, hint }) => {
          const isPhotorealUnavailable =
            id === "photorealistic" && globeViewer && !globeViewer.isPhotorealisticAvailable();
          const unavailableReason = isPhotorealUnavailable
            ? "Set NEXT_PUBLIC_GOOGLE_MAPS_API_KEY to enable photorealistic tiles"
            : null;

          return (
            <Tooltip key={id}>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  aria-label={`${label} buildings`}
                  aria-pressed={buildingMode === id}
                  disabled={Boolean(isPhotorealUnavailable || !globeViewer)}
                  onClick={() => handleBuildingModeSelect(id)}
                  className={cn(
                    "h-7 gap-1 px-1.5 font-mono text-[10px] tracking-wide",
                    buildingMode === id ? "bg-aeris-teal/15 text-aeris-teal hover:bg-aeris-teal/25 hover:text-aeris-teal" : "text-muted-foreground",
                    isPhotorealUnavailable && "text-muted-foreground/35",
                  )}
                >
                  <Icon className="size-3" />
                  {label}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-64">
                {unavailableReason ?? hint}
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}

interface GlobeControlButtonProps {
  label: string;
  onClick: () => void;
  isActive?: boolean;
  children: ReactNode;
}

function GlobeControlButton({ label, onClick, isActive, children }: GlobeControlButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-label={label}
          aria-pressed={isActive}
          onClick={onClick}
          className={cn(
            isActive && "bg-aeris-teal/15 text-aeris-teal hover:bg-aeris-teal/25 hover:text-aeris-teal",
          )}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top">{label}</TooltipContent>
    </Tooltip>
  );
}
