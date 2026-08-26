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

import { Minus, Orbit, Plus, RotateCcw } from "lucide-react";
import { useState, type ReactNode } from "react";

import { GlowDot, type GlowDotTone } from "@/components/sharedUI/dumbComponent/GlowDot";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { GLOBE_CAMERA } from "@/lib/constants/globe";
import { cn } from "@/lib/utils";

import { useMissionCommandStore } from "../../store/mission-command-store";
import type { MissionStatus } from "../../types/mission.types";

const MARKER_LEGEND: readonly { status: MissionStatus; label: string; tone: GlowDotTone }[] = [
  { status: "alert", label: "Alert", tone: "red" },
  { status: "active", label: "Active", tone: "teal" },
  { status: "monitoring", label: "Monitoring", tone: "blue" },
  { status: "archived", label: "Archived", tone: "neutral" },
];

export function GlobeControls() {
  const globeViewer = useMissionCommandStore((state) => state.globeViewer);
  const [isAutoRotating, setIsAutoRotating] = useState(true);

  const isGlobeReady = globeViewer !== null;

  const handleAutoRotateToggle = () => {
    const next = !isAutoRotating;
    setIsAutoRotating(next);
    globeViewer?.setAutoRotate(next);
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
          className={cn(isActive && "text-aeris-teal")}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top">{label}</TooltipContent>
    </Tooltip>
  );
}
