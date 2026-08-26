// features/missionCommand/types/globe.types.ts — the 3D Earth contract, including the renderer adapter.
//
// what  : Marker/track data types plus GlobeViewerHandle — the imperative interface any globe renderer
//         must satisfy.
// where : Implemented by components/globe/GlobeCanvas.tsx, consumed by use-globe-viewport.ts and by the
//         `globe.*` commands.
// how   : This handle is the reason the renderer is swappable. The rest of the application only ever calls
//         flyTo / resetView / setAutoRotate, so replacing the react-three-fiber implementation with
//         CesiumJS later means writing one new component that satisfies this interface — no consumer,
//         command or hook changes. Camera state is exchanged through this imperative handle rather than
//         through React state because it updates every frame, and per-frame React renders would tank the
//         frame budget.

import type { z } from "zod";

import type {
  globeMarkerSchema,
  satelliteTrackSchema,
} from "../schemas/mission.schema";

export type GlobeMarker = z.infer<typeof globeMarkerSchema>;
export type SatelliteTrack = z.infer<typeof satelliteTrackSchema>;

export interface GeographicPoint {
  latitude: number;
  longitude: number;
}

export interface GlobeFlyToTarget extends GeographicPoint {
  /** Camera distance from the globe centre in globe radii. Omit to keep the current distance. */
  distance?: number;
  /** Animation length in milliseconds. Omit for the default cinematic duration. */
  durationMs?: number;
}

/** The imperative surface every globe renderer implementation must provide. */
export interface GlobeViewerHandle {
  flyTo: (target: GlobeFlyToTarget) => void;
  /** Moves the camera along its current view axis. Negative values move closer. */
  zoomBy: (distanceDelta: number) => void;
  resetView: () => void;
  setAutoRotate: (isEnabled: boolean) => void;
  isAutoRotating: () => boolean;
}

export type GlobeLayerId = "markers" | "satelliteTracks" | "graticule";
