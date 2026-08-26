// store/geo-stage-store.ts — the shared 3D stage's handle and the camera handoff between surfaces.
//
// what  : Holds the live GeoStageHandle published by the Cesium viewer, its readiness flag, and the
//         pending descent that carries a camera flight across a route change.
// where : Written by components/sharedUI/functionalComponent/geoStage/CesiumStage.tsx. Read by
//         features/missionCommand (through its globe adapter) and features/investigation.
// how   : Global rather than feature-scoped because the viewer outlives every page in the geospatial
//         route group — that is the whole point of the shared stage, and it is what makes the globe→AOI
//         descent one continuous camera move instead of a cross-fade between two WebGL contexts.
//
//         The handle is a live connection object, the same category as a WebSocket client, not server
//         cache — so holding it here does not violate the server-state/UI-state separation. This store is
//         never persisted, so a non-serialisable value is safe. Every consumer must guard for null: the
//         handle is absent until the viewer paints, and absent again the moment it tears down.
//
//         `pendingDescent` exists because the navigation is deliberately NOT awaited. Mission Command
//         starts the flight and routes immediately; the workspace mounts around a camera already in
//         motion and consumes this to know it must not restart the flight it is already inside.

import { create } from "zustand";

import type {
  GeoStageHandle,
  StageBoundingBox,
  StageFlyToTarget,
} from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";

export interface PendingDescent {
  investigationId: string;
  target: StageFlyToTarget;
  bounds: StageBoundingBox | null;
  startedAt: number;
}

interface GeoStageState {
  handle: GeoStageHandle | null;
  isReady: boolean;
  pendingDescent: PendingDescent | null;

  setHandle: (handle: GeoStageHandle | null) => void;
  setReady: (isReady: boolean) => void;
  beginDescent: (descent: PendingDescent) => void;
  /** Reads and clears the descent in one step, so two mounts can never both claim it. */
  consumeDescent: (investigationId: string) => PendingDescent | null;
}

export const useGeoStageStore = create<GeoStageState>((set, get) => ({
  handle: null,
  isReady: false,
  pendingDescent: null,

  setHandle: (handle) => set({ handle }),
  setReady: (isReady) => set({ isReady }),
  beginDescent: (descent) => set({ pendingDescent: descent }),

  consumeDescent: (investigationId) => {
    const { pendingDescent } = get();
    if (!pendingDescent || pendingDescent.investigationId !== investigationId) {
      return null;
    }
    set({ pendingDescent: null });
    return pendingDescent;
  },
}));

/** Imperative access for callers outside React — the command bus and, later, the agent layer. */
export function getGeoStage(): GeoStageHandle | null {
  return useGeoStageStore.getState().handle;
}
