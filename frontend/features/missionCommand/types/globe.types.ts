// features/missionCommand/types/globe.types.ts — the 3D Earth contract, including the renderer adapter.
//
// what  : Marker/track data types plus GlobeViewerHandle — the imperative interface any globe renderer
//         must satisfy.
// where : Implemented by components/globe/CesiumGlobe.tsx, consumed by GlobeControls and by the
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
  /**
   * Camera altitude above the ellipsoid, in metres. Omit to use the standard locate altitude.
   * Metres, not abstract radii: Cesium works in real-world units, and so should every caller — an
   * altitude is something an analyst can reason about, a radius multiplier is not.
   */
  altitudeMeters?: number;
  /** Animation length in milliseconds. Omit for the default cinematic duration. Zero jumps instantly. */
  durationMs?: number;
}

/** The imperative surface every globe renderer implementation must provide. */
export interface GlobeViewerHandle {
  flyTo: (target: GlobeFlyToTarget) => void;
  /**
   * Multiplies the camera's current altitude. Below 1 moves closer, above 1 moves away.
   * Multiplicative rather than additive because a fixed metre step that feels right at street level is
   * imperceptible at orbital altitude, and vice versa.
   */
  zoomByFactor: (factor: number) => void;
  resetView: () => void;
  setAutoRotate: (isEnabled: boolean) => void;
  isAutoRotating: () => boolean;
}

export type GlobeLayerId = "markers" | "satelliteTracks" | "graticule";
