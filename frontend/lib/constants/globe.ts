// lib/constants/globe.ts — every tunable number the 3D Earth uses. No magic values inside the scene code.
//
// what  : Geometry, camera, land-dot sampling, marker, arc and level-of-detail configuration for the globe.
// where : Read by features/missionCommand/components/globe/*. Changing the look or the performance profile
//         of the Earth is a change to this file, not to shader or scene code.
// how   : The globe renders land as an instanced point cloud sampled from a rasterised land mask, so the
//         only quality/performance dial that matters is LAND_DOT_SAMPLING. The LOD thresholds cap how many
//         markers and labels are drawn — these exist because the marker feed is unbounded in production.

import { AERIS_COLOR_INT } from "./theme";

/** Unit-sphere radius. Every other distance below is expressed as a multiple of this. */
export const GLOBE_RADIUS = 1;

export const GLOBE_CAMERA = {
  fieldOfView: 38,
  initialDistance: 3.05,
  minDistance: 1.45,
  maxDistance: 4.6,
  /** Radians per second of idle auto-rotation. Pauses while the operator is interacting. */
  idleRotationSpeed: 0.028,
  /** How long after the last interaction before idle rotation resumes, in milliseconds. */
  idleResumeDelayMs: 2_600,
  dampingFactor: 0.06,
} as const;

export const LAND_DOT_SAMPLING = {
  /** Static asset rasterised into a land mask at runtime. Served from /public, never bundled into JS. */
  geometryUrl: "/geo/land-110m.json",
  /** Equirectangular raster resolution used for the land/water test. */
  maskWidth: 1024,
  maskHeight: 512,
  /** Angular spacing between candidate dots. Lower = denser globe, more instances. */
  spacingDegrees: 1.35,
  /** Dots are pushed marginally off the sphere so they never z-fight with the base sphere. */
  surfaceOffset: 0.002,
  dotSize: 0.0075,
} as const;

export const GLOBE_APPEARANCE = {
  oceanColor: AERIS_COLOR_INT.black,
  landDotColor: AERIS_COLOR_INT.teal,
  landDotOpacity: 0.62,
  graticuleColor: AERIS_COLOR_INT.stroke,
  graticuleOpacity: 0.3,
  /** Latitude/longitude line spacing in degrees. */
  graticuleStepDegrees: 15,
  atmosphereColor: AERIS_COLOR_INT.teal,
  atmosphereIntensity: 1.05,
  atmosphereScale: 1.16,
  /** Rim light that separates the terminator from the background. */
  rimColor: AERIS_COLOR_INT.blue,
} as const;

export const GLOBE_MARKERS = {
  /** Base point size in pixels at unit distance, before magnitude scaling and pulse. */
  baseSize: 26,
  /**
   * Hard cap on markers uploaded to the GPU. Markers render as a single instanced point cloud with the
   * pulse animated entirely in the vertex shader, so tens of thousands cost one draw call and no
   * per-frame CPU work. The cap exists only to bound memory if the feed ever returns something absurd;
   * when it bites, the lowest-magnitude markers are dropped first.
   */
  maxRenderedMarkers: 20_000,
  /** Only the N highest-magnitude markers get a DOM label — labels are the genuinely expensive part. */
  maxLabelledMarkers: 5,
  pulseSpeed: 2.1,
  statusColor: {
    active: AERIS_COLOR_INT.teal,
    monitoring: AERIS_COLOR_INT.blue,
    alert: AERIS_COLOR_INT.red,
    archived: AERIS_COLOR_INT.grayDim,
  },
} as const;

export const GLOBE_SATELLITE_ARCS = {
  /** Ambient data streams from the design report's idle-state wow factor. */
  maxVisibleArcs: 16,
  segmentCount: 64,
  /** Peak altitude of an arc as a fraction of globe radius. */
  altitudeFactor: 0.34,
  travelSpeed: 0.16,
  color: AERIS_COLOR_INT.blue,
  headColor: AERIS_COLOR_INT.teal,
} as const;

/** Device-pixel-ratio ceiling. Uncapped DPR on a 4K display is the single biggest cause of jank. */
export const GLOBE_MAX_PIXEL_RATIO = 1.75;
