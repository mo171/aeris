// features/missionCommand/components/MissionCommandScreen.tsx — the Mission Command Center surface.
//
// what  : Composes the application shell with the three zones of the command centre — the Data & Context
//         panel, the 3D Earth canvas, and the AERIS Assistant panel — and wires them to each other.
// where : Rendered by app/(geospatial)/page.tsx, which contains nothing else.
// how   : The Earth is NOT rendered here. It belongs to the shared stage mounted by the route group's
//         layout, which is what lets the camera keep flying across the navigation into the Investigation
//         Workspace. This screen contributes the panels that float over it, with pointer events disabled
//         on the gap between them so the operator can always grab and rotate the Earth. That is what keeps
//         the geospatial context present rather than framed, which is the point of the glass treatment in
//         the design report.
//
//         The two panels never talk to each other. Selection and focus flow through the feature store, and
//         camera moves flow through the globe handle that store publishes — so adding a fourth zone later
//         means adding a component, not rewiring the three that exist.
//
//         Each zone is wrapped in its own error boundary: a failure in the marker layer must cost the
//         globe, not the assistant and the catalogue as well.

"use client";

import { useCallback } from "react";

import { PanelContainer } from "@/components/sharedUI/functionalComponent/appShell/PanelContainer";
import { PanelErrorBoundary } from "@/components/sharedUI/functionalComponent/feedback/PanelErrorBoundary";
import { GLOBE_CAMERA } from "@/lib/constants/globe";
import { BOOT_SEQUENCE_DELAY } from "@/lib/constants/motion";
import { useUiStore } from "@/store/ui-store";

import { useInvestigationLaunch } from "@/features/investigation/hooks/use-investigation-launch";

import { useGlobeStageBinding } from "../hooks/use-globe-stage-binding";
import { useMissionCommandCommands } from "../hooks/use-mission-command-commands";
import { useMissionCommandStore } from "../store/mission-command-store";
import type { GlobeMarker } from "../types/globe.types";
import type { ImageryScene } from "../types/imagery.types";
import type { Mission } from "../types/mission.types";
import { AssistantPanel } from "./assistantPanel/AssistantPanel";
import { DataContextPanel } from "./dataPanel/DataContextPanel";
import { GlobeControls } from "./globe/GlobeControls";

export function MissionCommandScreen() {
  const isDataPanelOpen = useUiStore((state) => state.isDataPanelOpen);
  const isAssistantPanelOpen = useUiStore((state) => state.isAssistantPanelOpen);
  const dataPanelWidth = useUiStore((state) => state.dataPanelWidth);
  const assistantPanelWidth = useUiStore((state) => state.assistantPanelWidth);
  const setDataPanelWidth = useUiStore((state) => state.setDataPanelWidth);
  const setAssistantPanelWidth = useUiStore((state) => state.setAssistantPanelWidth);

  const setFocusedMissionId = useMissionCommandStore((state) => state.setFocusedMissionId);
  const toggleSceneSelection = useMissionCommandStore((state) => state.toggleSceneSelection);

  // Starting an investigation is investigation-domain work; only its trigger belongs to this surface.
  const { launch, isLaunching } = useInvestigationLaunch();


  // The globe handle is read at call time rather than subscribed to: these callbacks fire from user
  // interaction, long after mount, and re-creating them whenever the globe re-registers would churn every
  // memoised list row below them for no benefit.
  const flyToPosition = useCallback((latitude: number, longitude: number) => {
    useMissionCommandStore.getState().globeViewer?.flyTo({
      latitude,
      longitude,
      altitudeMeters: GLOBE_CAMERA.locateAltitudeMeters,
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

  const handleInvestigate = useCallback(() => {
    const { selectedSceneIds } = useMissionCommandStore.getState();
    if (selectedSceneIds.length === 0) {
      return;
    }
    launch({ sceneIds: selectedSceneIds, seedQuery: null, missionId: null });
  }, [launch]);

  // Registered after the callbacks exist so the stage can route a marker click straight into them.
  useGlobeStageBinding({ onMarkerSelect: handleMarkerSelect });
  useMissionCommandCommands();

  return (
    /* The overlay itself ignores pointer events; each panel opts back in. */
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
              onInvestigate={handleInvestigate}
              isLaunchingInvestigation={isLaunching}
            />
          </PanelErrorBoundary>
        </PanelContainer>

        {/*
          The free space between the panels. The globe's own controls live here rather than being anchored
          to the viewport, so they can never end up underneath a panel at any panel width.
        */}
        <div className="relative min-w-0 flex-1">
          <GlobeControls />
        </div>

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
  );
}
