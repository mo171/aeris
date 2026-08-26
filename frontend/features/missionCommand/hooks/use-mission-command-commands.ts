// features/missionCommand/hooks/use-mission-command-commands.ts — this surface's agent-invocable capabilities.
//
// what  : Registers every Mission Command action with the command bus: globe navigation, imagery
//         selection and search, mission focus, and assistant control.
// where : Called once by MissionCommandScreen. Unregisters automatically when the surface unmounts.
// how   : This hook is the contract between the interface and the agent. Anything the operator can do here
//         is declared once, with a Zod parameter schema and a plain-language description, and is then
//         reachable three ways — by clicking the control, by keyboard shortcut, and by an agent or voice
//         intent calling dispatchCommand. No separate agent adapter will ever be needed.
//
//         Handlers reach the globe and the assistant through the store's imperative handles, read at call
//         time with getState() rather than captured at registration. That matters: a command may be
//         dispatched before the globe has mounted or after the assistant has unmounted, and reading the
//         handle late means the command is simply a no-op instead of a crash or a stale reference.
//
//         Commands that take parameters are hidden from the palette, since a palette has nowhere to
//         collect arguments; they remain fully available to code and to the agent.

"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { z } from "zod";
import { Crosshair, Eraser, Orbit, RotateCcw, Search, Sparkles, Upload, X } from "lucide-react";

import { defineCommand, useRegisterCommands } from "@/lib/command-bus";
import { COMMAND_IDS } from "@/lib/constants/commands";
import { QUERY_KEYS } from "@/lib/constants/query-keys";
import { useUiStore } from "@/store/ui-store";

import { useMissionCommandStore } from "../store/mission-command-store";
import type { Mission, MissionPage } from "../types/mission.types";

export function useMissionCommandCommands(): void {
  const queryClient = useQueryClient();

  const toggleDataPanel = useUiStore((state) => state.toggleDataPanel);
  const toggleSceneSelection = useMissionCommandStore((state) => state.toggleSceneSelection);
  const clearSceneSelection = useMissionCommandStore((state) => state.clearSceneSelection);
  const setCatalogSearchTerm = useMissionCommandStore((state) => state.setCatalogSearchTerm);
  const setFocusedMissionId = useMissionCommandStore((state) => state.setFocusedMissionId);

  const commands = useMemo(() => {
    const getGlobeViewer = () => useMissionCommandStore.getState().globeViewer;
    const getAssistantControls = () => useMissionCommandStore.getState().assistantControls;

    const findCachedMission = (missionId: string): Mission | undefined => {
      const cached = queryClient.getQueryData<{ pages: MissionPage[] }>(
        QUERY_KEYS.missions.active(),
      );
      return cached?.pages
        .flatMap((page) => page.items)
        .find((mission) => mission.id === missionId);
    };

    return [
      defineCommand({
        id: COMMAND_IDS.globe.flyTo,
        title: "Fly to coordinates",
        description:
          "Move the 3D Earth camera to a geographic position. Latitude is -90 to 90, longitude is -180 to 180. altitudeMeters is optional and is the camera height above the ground in metres; smaller values are closer.",
        group: "globe",
        isPaletteVisible: false,
        paramsSchema: z.object({
          latitude: z.number().min(-90).max(90),
          longitude: z.number().min(-180).max(180),
          altitudeMeters: z.number().positive().optional(),
          durationMs: z.number().int().nonnegative().optional(),
        }),
        handler: (target) => getGlobeViewer()?.flyTo(target),
      }),
      defineCommand({
        id: COMMAND_IDS.globe.resetView,
        title: "Reset globe view",
        description: "Return the 3D Earth camera to its default orientation and distance.",
        group: "globe",
        keywords: ["camera", "home", "recentre"],
        icon: RotateCcw,
        paramsSchema: z.void(),
        handler: () => getGlobeViewer()?.resetView(),
      }),
      defineCommand({
        id: COMMAND_IDS.globe.toggleAutoRotate,
        title: "Toggle globe rotation",
        description: "Start or stop the idle rotation of the 3D Earth.",
        group: "globe",
        keywords: ["spin", "rotate", "idle"],
        icon: Orbit,
        paramsSchema: z.void(),
        handler: () => {
          const viewer = getGlobeViewer();
          viewer?.setAutoRotate(!viewer.isAutoRotating());
        },
      }),

      defineCommand({
        id: COMMAND_IDS.imagery.openUpload,
        title: "Open imagery intake",
        description: "Reveal the data panel so satellite imagery can be uploaded.",
        group: "imagery",
        keywords: ["upload", "import", "geotiff", "add"],
        icon: Upload,
        paramsSchema: z.void(),
        handler: () => toggleDataPanel(true),
      }),
      defineCommand({
        id: COMMAND_IDS.imagery.select,
        title: "Select a scene",
        description:
          "Toggle a satellite scene in or out of the assistant's question context, by its scene identifier.",
        group: "imagery",
        isPaletteVisible: false,
        paramsSchema: z.object({ sceneId: z.string().min(1) }),
        handler: ({ sceneId }) => {
          toggleDataPanel(true);
          toggleSceneSelection(sceneId);
        },
      }),
      defineCommand({
        id: COMMAND_IDS.imagery.clearSelection,
        title: "Clear scene selection",
        description: "Remove every scene from the assistant's question context.",
        group: "imagery",
        keywords: ["deselect", "reset", "context"],
        icon: X,
        paramsSchema: z.void(),
        handler: () => clearSceneSelection(),
      }),
      defineCommand({
        id: COMMAND_IDS.imagery.search,
        title: "Search the imagery catalogue",
        description:
          "Filter the scene catalogue by place name, sensor platform or modality. Pass an empty string to clear the filter.",
        group: "imagery",
        isPaletteVisible: false,
        icon: Search,
        paramsSchema: z.object({ searchTerm: z.string() }),
        handler: ({ searchTerm }) => {
          toggleDataPanel(true);
          setCatalogSearchTerm(searchTerm);
        },
      }),

      defineCommand({
        id: COMMAND_IDS.missions.open,
        title: "Open a mission",
        description: "Focus a mission by its identifier and fly the globe to its area of interest.",
        group: "missions",
        isPaletteVisible: false,
        icon: Crosshair,
        paramsSchema: z.object({ missionId: z.string().min(1) }),
        handler: ({ missionId }) => {
          setFocusedMissionId(missionId);
          const mission = findCachedMission(missionId);
          if (mission) {
            getGlobeViewer()?.flyTo({
              latitude: mission.centroid.latitude,
              longitude: mission.centroid.longitude,
            });
          }
        },
      }),

      defineCommand({
        id: COMMAND_IDS.assistant.ask,
        title: "Ask AERIS",
        description:
          "Send a natural-language question to the AERIS agent using the currently selected scenes as context.",
        group: "assistant",
        isPaletteVisible: false,
        paramsSchema: z.object({ prompt: z.string().min(1) }),
        handler: ({ prompt }) => getAssistantControls()?.ask(prompt),
      }),
      defineCommand({
        id: COMMAND_IDS.assistant.focusComposer,
        title: "Focus the assistant",
        description: "Place the cursor in the assistant question box.",
        group: "assistant",
        keywords: ["ask", "question", "type", "chat"],
        shortcut: ["ctrl", "/"],
        icon: Sparkles,
        paramsSchema: z.void(),
        handler: () => getAssistantControls()?.focusComposer(),
      }),
      defineCommand({
        id: COMMAND_IDS.assistant.stop,
        title: "Stop the assistant",
        description: "Cancel the answer currently being generated.",
        group: "assistant",
        keywords: ["cancel", "abort", "halt"],
        paramsSchema: z.void(),
        handler: () => getAssistantControls()?.stop(),
      }),
      defineCommand({
        id: COMMAND_IDS.assistant.clear,
        title: "Clear the conversation",
        description: "Discard the current assistant transcript and start a fresh session.",
        group: "assistant",
        keywords: ["reset", "new", "wipe"],
        icon: Eraser,
        paramsSchema: z.void(),
        handler: () => getAssistantControls()?.clear(),
      }),
    ];
  }, [
    clearSceneSelection,
    queryClient,
    setCatalogSearchTerm,
    setFocusedMissionId,
    toggleDataPanel,
    toggleSceneSelection,
  ]);

  useRegisterCommands(commands);
}
