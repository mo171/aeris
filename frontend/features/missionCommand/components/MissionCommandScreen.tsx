// features/missionCommand/components/MissionCommandScreen.tsx — the Mission Command Center surface.
//
// what  : Composes the application shell with the three zones of the command centre — the Data & Context
//         panel, the 3D Earth canvas, and the AERIS Assistant panel — and wires them to each other.
// where : Rendered by app/page.tsx, which contains nothing else.
// how   : The globe fills the whole content area and the panels float above it, with pointer events
//         disabled on the gap between them, so the operator can always grab and rotate the Earth. That is
//         what keeps the geospatial context present rather than framed, which is the point of the glass
//         treatment in the design report.
//
//         The two panels never talk to each other. Selection and focus flow through the feature store, and
//         camera moves flow through the globe handle that store publishes — so adding a fourth zone later
//         means adding a component, not rewiring the three that exist.
//
//         Each zone is wrapped in its own error boundary: a failure in the marker layer must cost the
//         globe, not the assistant and the catalogue as well.

"use client";

import { useCallback } from "react";

import { AppShell } from "@/components/sharedUI/functionalComponent/appShell/AppShell";
import { PanelContainer } from "@/components/sharedUI/functionalComponent/appShell/PanelContainer";
import { PanelErrorBoundary } from "@/components/sharedUI/functionalComponent/feedback/PanelErrorBoundary";
import { NotificationBell } from "@/features/notifications/components/NotificationBell";
import { BOOT_SEQUENCE_DELAY } from "@/lib/constants/motion";
import { useUiStore } from "@/store/ui-store";

import { useMissionCommandCommands } from "../hooks/use-mission-command-commands";
import { useMissionCommandStore } from "../store/mission-command-store";
import type { GlobeMarker } from "../types/globe.types";
import type { ImageryScene } from "../types/imagery.types";
import type { Mission } from "../types/mission.types";
import { AssistantPanel } from "./assistantPanel/AssistantPanel";
import { DataContextPanel } from "./dataPanel/DataContextPanel";
import { GlobeViewport } from "./globe/GlobeViewport";

/** Camera distance used when flying to a specific scene or mission — close enough to read the region. */
const LOCATE_CAMERA_DISTANCE = 1.75;

export function MissionCommandScreen() {
  const isDataPanelOpen = useUiStore((state) => state.isDataPanelOpen);
  const isAssistantPanelOpen = useUiStore((state) => state.isAssistantPanelOpen);
  const dataPanelWidth = useUiStore((state) => state.dataPanelWidth);
  const assistantPanelWidth = useUiStore((state) => state.assistantPanelWidth);
  const setDataPanelWidth = useUiStore((state) => state.setDataPanelWidth);
  const setAssistantPanelWidth = useUiStore((state) => state.setAssistantPanelWidth);

  const setFocusedMissionId = useMissionCommandStore((state) => state.setFocusedMissionId);
  const toggleSceneSelection = useMissionCommandStore((state) => state.toggleSceneSelection);

  useMissionCommandCommands();

  // The globe handle is read at call time rather than subscribed to: these callbacks fire from user
  // interaction, long after mount, and re-creating them whenever the globe re-registers would churn every
  // memoised list row below them for no benefit.
  const flyToPosition = useCallback((latitude: number, longitude: number) => {
    useMissionCommandStore.getState().globeViewer?.flyTo({
      latitude,
      longitude,
      distance: LOCATE_CAMERA_DISTANCE,
    });
  }, []);

  const handleLocateScene = useCallback(
    (scene: ImageryScene) => {
      toggleSceneSelection(scene.id);
      flyToPosition(scene.centroid.latitude, scene.centroid.longitude);
    },
    [flyToPosition, toggleSceneSelection],
  );

  const handleLocateMission = useCallback(
    (mission: Mission) => {
      setFocusedMissionId(mission.id);
      flyToPosition(mission.centroid.latitude, mission.centroid.longitude);
    },
    [flyToPosition, setFocusedMissionId],
  );

  const handleMarkerSelect = useCallback(
    (marker: GlobeMarker) => {
      if (marker.missionId) {
        setFocusedMissionId(marker.missionId);
      }
      flyToPosition(marker.position.latitude, marker.position.longitude);
    },
    [flyToPosition, setFocusedMissionId],
  );

  return (
    <AppShell headerActionsSlot={<NotificationBell />}>
      <PanelErrorBoundary panelName="Globe">
        <GlobeViewport onMarkerSelect={handleMarkerSelect} />
      </PanelErrorBoundary>

      {/* The overlay itself ignores pointer events; each panel opts back in. */}
      <div className="pointer-events-none absolute inset-0 flex gap-3 p-3">
        <PanelContainer
          side="left"
          isOpen={isDataPanelOpen}
          width={dataPanelWidth}
          onWidthCommit={setDataPanelWidth}
          revealDelaySeconds={BOOT_SEQUENCE_DELAY.dataPanel}
          ariaLabel="Data and context panel"
        >
          <PanelErrorBoundary panelName="Data & Context">
            <DataContextPanel
              onLocateScene={handleLocateScene}
              onLocateMission={handleLocateMission}
            />
          </PanelErrorBoundary>
        </PanelContainer>

        <div className="min-w-0 flex-1" aria-hidden="true" />

        <PanelContainer
          side="right"
          isOpen={isAssistantPanelOpen}
          width={assistantPanelWidth}
          onWidthCommit={setAssistantPanelWidth}
          revealDelaySeconds={BOOT_SEQUENCE_DELAY.assistantPanel}
          ariaLabel="AERIS assistant panel"
        >
          <PanelErrorBoundary panelName="Assistant">
            <AssistantPanel />
          </PanelErrorBoundary>
        </PanelContainer>
      </div>
    </AppShell>
  );
}
