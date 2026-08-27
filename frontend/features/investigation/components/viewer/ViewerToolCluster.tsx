// features/investigation/components/viewer/ViewerToolCluster.tsx — the floating tools over the scene.
//
// what  : One control cluster: draw a region, sweep the comparator, play the loop, switch to volumetric,
//         clear the spotlight, and reset the view.
// where : Rendered into the centre column of InvestigationScreen — the free space between the panels.
// how   : It lives in the centre column rather than being anchored to the viewport, so it can never end
//         up underneath a panel at any panel width. That was a real defect on Mission Command and this
//         surface starts on the right side of it.
//
//         Every button dispatches a command rather than calling a handler. A button and its spoken or
//         agent-issued equivalent are therefore literally the same call and cannot diverge in behaviour.

"use client";

import { Box, Crosshair, Pause, Play, RotateCcw, SplitSquareHorizontal } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { dispatchCommand } from "@/lib/command-bus";
import { COMMAND_IDS } from "@/lib/constants/commands";
import { cn } from "@/lib/utils";

import { useInvestigationStore } from "../../store/investigation-store";

export function ViewerToolCluster() {
  const isRegionDrawArmed = useInvestigationStore((state) => state.isRegionDrawArmed);
  const isPlaybackRunning = useInvestigationStore((state) => state.isPlaybackRunning);
  const renderMode = useInvestigationStore((state) => state.renderMode);
  const spotlightClaimId = useInvestigationStore((state) => state.spotlightClaimId);

  return (
    <div className="pointer-events-auto flex items-center gap-1 rounded-md border border-border bg-surface-2/80 p-1 backdrop-blur-md">
      <ToolButton
        label={isRegionDrawArmed ? "Cancel region" : "Draw a region to ask about"}
        isActive={isRegionDrawArmed}
        onClick={() =>
          void dispatchCommand(
            isRegionDrawArmed
              ? COMMAND_IDS.investigation.cancelRegionDraw
              : COMMAND_IDS.investigation.beginRegionDraw,
          )
        }
      >
        <Crosshair />
      </ToolButton>

      <ToolButton
        label="Sweep before to after"
        onClick={() => void dispatchCommand(COMMAND_IDS.investigation.sweepSplit)}
      >
        <SplitSquareHorizontal />
      </ToolButton>

      <ToolButton
        label={isPlaybackRunning ? "Stop the loop" : "Play the before/after loop"}
        isActive={isPlaybackRunning}
        onClick={() => void dispatchCommand(COMMAND_IDS.investigation.togglePlayback)}
      >
        {isPlaybackRunning ? <Pause /> : <Play />}
      </ToolButton>

      <span className="mx-0.5 h-4 w-px bg-border" aria-hidden="true" />

      <ToolButton
        label={renderMode === "extruded" ? "Flatten change regions" : "Raise change regions"}
        isActive={renderMode === "extruded"}
        onClick={() => void dispatchCommand(COMMAND_IDS.investigation.toggleVolumetric)}
      >
        <Box />
      </ToolButton>

      {spotlightClaimId !== null ? (
        <ToolButton
          label="Clear the evidence spotlight"
          isActive
          onClick={() => void dispatchCommand(COMMAND_IDS.investigation.clearSpotlight)}
        >
          <Crosshair />
        </ToolButton>
      ) : null}

      <ToolButton
        label="Reset the view"
        onClick={() => void dispatchCommand(COMMAND_IDS.investigation.resetView)}
      >
        <RotateCcw />
      </ToolButton>
    </div>
  );
}

interface ToolButtonProps {
  label: string;
  onClick: () => void;
  isActive?: boolean;
  children: ReactNode;
}

function ToolButton({ label, onClick, isActive, children }: ToolButtonProps) {
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
