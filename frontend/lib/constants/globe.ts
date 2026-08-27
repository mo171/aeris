// lib/constants/globe.ts — every tunable value the CesiumJS globe uses. No magic numbers in scene code.
//
// what  : Cesium base URL, basemap providers, camera geometry, marker level-of-detail, arc animation and
//         performance ceilings.
// where : Read by features/missionCommand/components/globe/*. Changing how the Earth looks or performs is
//         a change to this file, not to viewer code.
// how   : Cesium works in real-world units — degrees and metres — not the abstract radii the previous
//         react-three-fiber globe used. Every altitude below is metres above the ellipsoid, which is why
//         the numbers look large: 19,000 km is roughly "whole Earth in frame".

import { AERIS_COLOR_HEX } from "./theme";

/**
 * Where Cesium loads its Workers, Assets, ThirdParty and Widgets from at runtime.
 * These are copied into /public by scripts/copy-cesium-assets.mjs on postinstall, NOT bundled — they are
 * roughly 8 MB and must be fetched on demand. `window.CESIUM_BASE_URL` must be set to this before the
 * first Viewer is constructed or Cesium will request its workers from the wrong origin and fail silently.
 */
export const CESIUM_BASE_URL = "/cesium";

export const GLOBE_CAMERA = {
  /** Opening view. Centred on the Indian subcontinent, the primary area of interest for AERIS. */
  home: {
    longitude: 78.9,
    latitude: 20.6,
    altitudeMeters: 19_000_000,
  },
  /** Altitude used when flying to a specific scene or mission — close enough to read the region. */
  locateAltitudeMeters: 120_000,
  minimumZoomAltitudeMeters: 300,
  maximumZoomAltitudeMeters: 26_000_000,
  /** Multiplicative zoom step. Below 1 moves closer, above 1 moves away. */
  zoomInFactor: 0.55,
  zoomOutFactor: 1.8,
  /** Radians per second of idle rotation. Pauses while the operator is interacting. */
  idleRotationRadiansPerSecond: 0.018,
  /** How long after the last interaction before idle rotation resumes. */
  idleResumeDelayMs: 2_600,
  flyDurationSeconds: 2.2,
  /** A brisker curve for zoom steps, which should feel like a control rather than a journey. */
  zoomDurationSeconds: 0.6,
} as const;

/**
 * Basemap imagery.
 *
 * With a Cesium Ion token the globe uses Ion world imagery and real elevation — that is the intended
 * experience. Without one it falls back to a dark raster basemap so the application never boots to a
 * black sphere. The fallback is a safety net, not an equivalent option.
 */
export const GLOBE_BASEMAP = {
  fallbackTileUrl: "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
  fallbackAttribution: "© OpenStreetMap contributors © CARTO",
  fallbackMaximumLevel: 19,
} as const;

export const GLOBE_APPEARANCE = {
  /** Shown where no imagery tile has loaded yet, so gaps read as space rather than as a rendering fault. */
  baseColor: AERIS_COLOR_HEX.black,
  /** Day/night terminator driven by real sun position. A genuine detail, not a filter. */
  enableSunLighting: true,
  showGroundAtmosphere: true,
  showSkyAtmosphere: true,

  /**
   * Imagery grading.
   *
   * These were originally set much darker to keep overlays dominant, which drained the planet of colour
   * and made it look like a grey relief map. The Earth is the centrepiece of this screen and should look
   * like the Earth; marker prominence is controlled by the level-of-detail rules below instead, which is
   * the correct lever — dimming the whole planet to make dots readable is solving the wrong problem.
   */
  imageryBrightness: 1.02,
  imageryContrast: 1.12,
  imagerySaturation: 1.18,
  imageryGamma: 0.98,

  /** A slight cool shift ties the atmosphere to the AERIS palette without tinting the landmass. */
  atmosphereHueShift: -0.02,
  atmosphereSaturationShift: 0.08,
  atmosphereBrightnessShift: 0.05,
} as const;

export const GLOBE_MARKERS = {
  /** Pixel size at unit scale, before magnitude and distance scaling. */
  basePixelSize: 4.5,
  /** Added on top of base size, scaled by the marker's magnitude. */
  magnitudePixelRange: 4.5,
  outlineWidth: 1,
  /** A dark rim keeps a bright marker legible against bright terrain such as desert or cloud. */
  outlineColor: AERIS_COLOR_HEX.black,

  /**
   * Distance-based scaling: (nearDistance, nearScale, farDistance, farScale).
   * Markers shrink as the camera pulls back so a global view reads as a constellation of fine points
   * rather than a field of overlapping blobs.
   */
  scaleByDistance: {
    nearMeters: 150_000,
    nearScale: 1.7,
    farMeters: 22_000_000,
    farScale: 0.5,
  },
  /** Markers soften rather than vanish at extreme range, which keeps the globe from looking speckled. */
  translucencyByDistance: {
    nearMeters: 150_000,
    nearAlpha: 1,
    farMeters: 30_000_000,
    farAlpha: 0.4,
  },

  /**
   * Level of detail, by status.
   *
   * A marker is drawn only while the camera is closer than its range. This is what keeps the orbital view
   * clean: from space you see alerts and active investigations, and the routine monitoring feed reveals
   * itself as you descend. Importance is status-first because that is what the operator triages on — a
   * globe that renders every observation at every altitude communicates nothing.
   *
   * Evaluated on the GPU, so hiding markers this way costs nothing.
   */
  visibilityRangeMeters: {
    alert: 6.0e7,
    active: 3.2e7,
    monitoring: 9.0e6,
    archived: 2.5e6,
  },
  /** Range multiplier from magnitude: a low-magnitude marker needs a closer camera than a high one. */
  magnitudeRangeFloor: 0.6,
  magnitudeRangeSpan: 0.8,

  /** Alert markers pulse; nothing else does, so the motion always carries meaning. */
  pulsePixelAmplitude: 3,
  pulseSpeed: 2.4,

  /**
   * Hard ceiling on markers uploaded to the GPU. All markers live in a single PointPrimitiveCollection,
   * so tens of thousands cost one draw call; the cap only bounds memory if the feed returns something
   * absurd. When it bites, the lowest-magnitude markers are dropped first.
   */
  maxRenderedMarkers: 20_000,
  statusColor: {
    active: AERIS_COLOR_HEX.teal,
    monitoring: AERIS_COLOR_HEX.blue,
    alert: AERIS_COLOR_HEX.red,
    archived: AERIS_COLOR_HEX.grayDim,
  },
} as const;

export const GLOBE_SATELLITE_ARCS = {
  maxVisibleArcs: 12,
  sampleCount: 96,
  widthPixels: 1.6,
  /**
   * Apex height as a fraction of the ground distance the arc spans. At 0.08 a hemisphere-crossing pass
   * peaks around 800 km, which is roughly true low-Earth-orbit altitude — the arcs read as satellite
   * passes rather than as decorative rings thrown around the planet.
   */
  apexHeightRatio: 0.08,
  /** Cycles per second for the travelling pulse. */
  pulseSpeed: 0.22,
  /** How sharply the trail falls off behind the pulse head. Higher is a shorter, tighter comet. */
  trailFalloff: 16,
  /** Resting opacity of the arc line itself, before the pulse passes over it. */
  restAlpha: 0.07,
  /** Additional opacity carried by the pulse head. */
  pulseAlpha: 0.85,
  trailColor: AERIS_COLOR_HEX.blue,
  headColor: AERIS_COLOR_HEX.teal,
} as const;

/**
 * Seconds spent morphing between the globe, the flat map and the 2.5D view.
 *
 * Long enough to read as the same Earth changing shape rather than two unrelated views being swapped,
 * short enough that an analyst switching to 2D to digitise something is not kept waiting.
 */
export const GLOBE_PROJECTION_MORPH_SECONDS = 1.1;

/**
 * How often the scene is rendered while a hidden tab is still trying to reach its first frame.
 *
 * Browsers starve requestAnimationFrame in a hidden tab, which stops Cesium's own render loop dead: the
 * scene never paints, readiness never fires, and an operator returning to a tab they opened earlier finds
 * it still saying "initialising". Timers keep running when hidden, so the loop is handed to one until a
 * frame has been painted — and then stops, because a hidden tab has nothing to show anyone and rendering
 * a full globe on a timer forever would burn a laptop battery for no one. Browsers clamp background
 * timers to roughly a second anyway, so asking for much less than that buys nothing.
 */
export const GLOBE_HIDDEN_TAB_RENDER_INTERVAL_MS = 500;

/**
 * Resolution-scale ceiling. Uncapped device pixel ratio on a high-density display is the single most
 * common cause of an otherwise healthy globe running at thirty frames per second.
 */
export const GLOBE_MAX_RESOLUTION_SCALE = 1.5;
