// features/missionCommand/store/mission-command-store.ts — shared state inside the Mission Command surface.
//
// what  : Scene selection, catalogue search term, focused mission, and in-flight upload tasks.
// where : Read by the data panel, the assistant panel and the globe layer of this feature only.
// how   : This is feature state, not global state, so it lives here rather than in store/. It exists to
//         stop three sibling panels from prop-drilling through the screen component: the catalogue selects
//         a scene, the assistant reads that selection as question context, and the globe flies to it —
//         none of them need to know the others exist.
//
//         Upload tasks are client state, not server state, which is why they belong in Zustand while the
//         resulting scenes belong in the query cache. Progress updates arrive dozens of times per upload
//         and have no meaning to the backend.

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { AssistantPanelControls } from "../types/assistant.types";
import type { GlobeViewerHandle } from "../types/globe.types";
import type { ImageryUploadTask } from "../types/imagery.types";

/** Selecting more scenes than this is almost always accidental and produces meaningless analyses. */
export const MAX_SELECTED_SCENES = 4;

interface MissionCommandState {
  selectedSceneIds: string[];
  catalogSearchTerm: string;
  focusedMissionId: string | null;
  uploadTasks: ImageryUploadTask[];

  /**
   * Which of the data panel's two lists are expanded.
   *
   * The catalogue and the mission list compete for the same vertical space, and which one matters
   * depends entirely on what the operator is doing — hunting for a scene, or checking what is running.
   * Collapsing one hands its space to the other rather than leaving both cramped.
   */
  isCatalogSectionExpanded: boolean;
  isMissionSectionExpanded: boolean;
  toggleCatalogSection: () => void;
  toggleMissionSection: () => void;

  /**
   * Imperative handles published by the globe and the assistant panel once they mount.
   *
   * These are live connection objects, not data — the same category as a WebSocket client — and they live
   * here rather than in refs threaded down through props for two reasons. First, commands must be able to
   * reach them from outside React entirely: the agent and voice layers will call dispatchCommand from
   * non-component code, and a React ref is unreachable from there. Second, it removes a four-level ref
   * prop chain from the globe. Both are null until their component mounts, so every caller must guard.
   *
   * This store is never persisted, so non-serialisable values here are safe.
   */
  globeViewer: GlobeViewerHandle | null;
  assistantControls: AssistantPanelControls | null;

  setGlobeViewer: (viewer: GlobeViewerHandle | null) => void;
  setAssistantControls: (controls: AssistantPanelControls | null) => void;

  isAutoRotating: boolean;
  setIsAutoRotating: (isAutoRotating: boolean) => void;

  toggleSceneSelection: (sceneId: string) => void;
  clearSceneSelection: () => void;
  setCatalogSearchTerm: (searchTerm: string) => void;
  setFocusedMissionId: (missionId: string | null) => void;

  addUploadTask: (task: ImageryUploadTask) => void;
  updateUploadTask: (localId: string, changes: Partial<ImageryUploadTask>) => void;
  removeUploadTask: (localId: string) => void;
  clearCompletedUploadTasks: () => void;
}

export const useMissionCommandStore = create<MissionCommandState>()(
  persist(
    (set) => ({
  selectedSceneIds: [],
  catalogSearchTerm: "",
  focusedMissionId: null,
  uploadTasks: [],
  isCatalogSectionExpanded: true,
  isMissionSectionExpanded: true,
  isAutoRotating: false,
  globeViewer: null,
  assistantControls: null,

  setIsAutoRotating: (isAutoRotating) => set({ isAutoRotating }),

  toggleCatalogSection: () =>
    set((state) => ({ isCatalogSectionExpanded: !state.isCatalogSectionExpanded })),
  toggleMissionSection: () =>
    set((state) => ({ isMissionSectionExpanded: !state.isMissionSectionExpanded })),

  setGlobeViewer: (viewer) => set({ globeViewer: viewer }),
  setAssistantControls: (controls) => set({ assistantControls: controls }),

  toggleSceneSelection: (sceneId) =>
    set((state) => {
      if (state.selectedSceneIds.includes(sceneId)) {
        return { selectedSceneIds: state.selectedSceneIds.filter((id) => id !== sceneId) };
      }
      // Oldest selection drops out once the cap is reached, so selecting always succeeds.
      const next = [...state.selectedSceneIds, sceneId];
      return { selectedSceneIds: next.slice(-MAX_SELECTED_SCENES) };
    }),

  clearSceneSelection: () => set({ selectedSceneIds: [] }),
  setCatalogSearchTerm: (searchTerm) => set({ catalogSearchTerm: searchTerm }),
  setFocusedMissionId: (missionId) => set({ focusedMissionId: missionId }),

  addUploadTask: (task) => set((state) => ({ uploadTasks: [task, ...state.uploadTasks] })),

  updateUploadTask: (localId, changes) =>
    set((state) => ({
      uploadTasks: state.uploadTasks.map((task) =>
        task.localId === localId ? { ...task, ...changes } : task,
      ),
    })),

  removeUploadTask: (localId) =>
    set((state) => ({
      uploadTasks: state.uploadTasks.filter((task) => task.localId !== localId),
    })),

  clearCompletedUploadTasks: () =>
    set((state) => ({
      uploadTasks: state.uploadTasks.filter((task) => task.state !== "complete"),
    })),
  }),
  {
    name: "mission-command-storage",
    partialize: (state) => ({
      isAutoRotating: state.isAutoRotating,
      isCatalogSectionExpanded: state.isCatalogSectionExpanded,
      isMissionSectionExpanded: state.isMissionSectionExpanded,
      selectedSceneIds: state.selectedSceneIds,
      focusedMissionId: state.focusedMissionId,
      catalogSearchTerm: state.catalogSearchTerm,
    }),
    version: 1,
  },
));
