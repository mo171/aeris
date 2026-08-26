// features/missionCommand/components/globe/GlobeControls.tsx — the floating camera controls over the globe.
//
// what  : Zoom, reset-view and auto-rotate controls, plus the marker status legend.
// where : Overlaid on the globe by GlobeViewport.
// how   : These are DOM controls, not 3D objects, so they stay crisp at any resolution and are reachable
//         by keyboard and screen readers — a control drawn inside the canvas is neither.
//
//         They act through the GlobeViewerHandle published in the feature store, which is the same path
//         the command bus uses. A button and its equivalent command therefore cannot diverge in behaviour,
//         because they are literally the same call.

"use client";

import { Minus, Orbit, Plus, RotateCcw } from "lucide-react";
import { useState, type ReactNode } from "react";

import { GlowDot, type GlowDotTone } from "@/components/sharedUI/dumbComponent/GlowDot";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { useMissionCommandStore } from "../../store/mission-command-store";
import type { MissionStatus } from "../../types/mission.types";

const ZOOM_STEP_DISTANCE = 0.45;

const MARKER_LEGEND: readonly { status: MissionStatus; label: string; tone: GlowDotTone }[] = [
  { status: "alert", label: "Alert", tone: "red" },
  { status: "active", label: "Active", tone: "teal" },
  { status: "monitoring", label: "Monitoring", tone: "blue" },
  { status: "archived", label: "Archived", tone: "neutral" },
];

interface GlobeControlsProps {
  className?: string;
}

export function GlobeControls({ className }: GlobeControlsProps) {
  const globeViewer = useMissionCommandStore((state) => state.globeViewer);
  const [isAutoRotating, setIsAutoRotating] = useState(true);

  const handleAutoRotateToggle = () => {
    const next = !isAutoRotating;
    setIsAutoRotating(next);
    globeViewer?.setAutoRotate(next);
  };

  return (
    <>
      <div
        className={cn(
          "pointer-events-auto absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-md border border-border bg-surface-2/80 p-1 backdrop-blur-md",
          className,
        )}
      >
        <GlobeControlButton
          label="Zoom in"
          onClick={() => globeViewer?.zoomBy(-ZOOM_STEP_DISTANCE)}
        >
          <Plus />
        </GlobeControlButton>
        <GlobeControlButton
          label="Zoom out"
          onClick={() => globeViewer?.zoomBy(ZOOM_STEP_DISTANCE)}
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

      <div
        className={cn(
          "pointer-events-none absolute bottom-4 left-4 flex flex-col gap-1 rounded-md border border-border bg-surface-2/70 px-2.5 py-2 backdrop-blur-md",
          className,
        )}
      >
        <span className="aeris-technical mb-0.5">Marker status</span>
        {MARKER_LEGEND.map((entry) => (
          <span key={entry.status} className="flex items-center gap-2">
            <GlowDot tone={entry.tone} isPulsing={entry.status === "alert"} />
            <span className="font-mono text-[10px] tracking-wide text-muted-foreground">
              {entry.label}
            </span>
          </span>
        ))}
      </div>
    </>
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
