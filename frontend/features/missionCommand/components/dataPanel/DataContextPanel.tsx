// features/missionCommand/components/dataPanel/DataContextPanel.tsx — the left panel of Mission Command.
//
// what  : Composes imagery intake, the scene catalogue, the mission list and the model fleet strip into
//         one column, and adds the header showing current scene selection.
// where : Rendered by MissionCommandScreen inside a PanelContainer.
// how   : Pure composition — every section owns its own data, states and errors, so this file has no
//         hooks, no queries and no conditionals about loading. That is what lets a section be added,
//         removed or reordered without touching anything else, and it keeps the panel's blast radius to
//         one section when something fails.
//
//         Order follows the operator's workflow: bring imagery in, find it, see what is already running,
//         confirm the tools are up.

"use client";

import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { useMissionCommandStore } from "../../store/mission-command-store";
import type { ImageryScene } from "../../types/imagery.types";
import type { Mission } from "../../types/mission.types";
import { ActiveMissionsList } from "./ActiveMissionsList";
import { ImageryCatalogList } from "./ImageryCatalogList";
import { ImageryUploadZone } from "./ImageryUploadZone";
import { ModelStatusStrip } from "./ModelStatusStrip";

interface DataContextPanelProps {
  onLocateScene: (scene: ImageryScene) => void;
  onLocateMission: (mission: Mission) => void;
}

export function DataContextPanel({ onLocateScene, onLocateMission }: DataContextPanelProps) {
  const selectedSceneIds = useMissionCommandStore((state) => state.selectedSceneIds);
  const clearSceneSelection = useMissionCommandStore((state) => state.clearSceneSelection);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-9 shrink-0 items-center justify-between gap-2 border-b border-border px-3">
        <h1 className="text-xs font-semibold tracking-wide text-foreground">Data &amp; Context</h1>
        <span
          className={cn(
            "flex items-center gap-1 transition-opacity duration-base",
            selectedSceneIds.length > 0 ? "opacity-100" : "pointer-events-none opacity-0",
          )}
        >
          <span className="font-mono text-[10px] tracking-wide text-aeris-teal uppercase">
            {selectedSceneIds.length} selected
          </span>
          <Button
            size="icon-xs"
            variant="ghost"
            aria-label="Clear scene selection"
            onClick={clearSceneSelection}
          >
            <X />
          </Button>
        </span>
      </header>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden pt-1">
        <ImageryUploadZone />
        <ImageryCatalogList onLocateScene={onLocateScene} />
        <ActiveMissionsList onLocateMission={onLocateMission} />
        <ModelStatusStrip />
      </div>
    </div>
  );
}
