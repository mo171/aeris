"use client";

import React from "react";
import { Surface } from "@webprodigies/flute";

import { GeoStage } from "@/components/sharedUI/functionalComponent/geoStage/GeoStage";
import { TooltipProvider } from "@/components/ui/tooltip";
import { DataContextPanel } from "@/features/missionCommand/components/dataPanel/DataContextPanel";
import { AssistantPanel } from "@/features/missionCommand/components/assistantPanel/AssistantPanel";
import { GlobeControls } from "@/features/missionCommand/components/globe/GlobeControls";

const surfaceStyle = {
  position: "absolute",
  overflow: "hidden",
};

export default function MissionCommandIntroScene() {
  return (
    <TooltipProvider delayDuration={220}>
      <>
        <Surface id="globe-stage" style={{ ...surfaceStyle, inset: 0, zIndex: 0 }}>
          <GeoStage />
        </Surface>

        <Surface
          id="data-context"
          style={{ ...surfaceStyle, left: 16, top: 24, bottom: 16, width: 360, zIndex: 2 }}
        >
          <DataContextPanel
            onLocateScene={() => undefined}
            onInvestigate={() => undefined}
            isLaunchingInvestigation={false}
          />
        </Surface>

        <Surface
          id="assistant-rail"
          style={{ ...surfaceStyle, right: 16, top: 24, bottom: 16, width: 390, zIndex: 3 }}
        >
          <AssistantPanel />
        </Surface>

        <Surface
          id="globe-controls"
          style={{ ...surfaceStyle, left: 390, right: 420, bottom: 22, height: 48, zIndex: 4 }}
        >
          <GlobeControls />
        </Surface>
      </>
    </TooltipProvider>
  );
}
