// lib/constants/investigation.ts — every tunable value the Investigation Workspace uses.
//
// what  : Camera geometry for the descent, comparator behaviour, playbar timing, panel sizing and the
//         limits that stop the workspace from being handed something it cannot render.
// where : Read by features/investigation/* and by the geoStage comparator and camera code.
// how   : Split from lib/constants/globe.ts on purpose. The globe is an orbital instrument and the
//         workspace is a close-range one — they want different zoom limits, different flight curves and
//         different idle behaviour, and folding both into one table would mean every change to one risks
//         the other.

export const INVESTIGATION_CAMERA = {
  /** Altitude the descent settles at over an area of interest. Close enough to read individual blocks. */
  aoiAltitudeMeters: 9_000,
  /** Altitude used when framing a single piece of evidence. */
  evidenceAltitudeMeters: 2_600,
  /** Extra vertical room left around a bounding box when framing it, as a fraction of its diagonal. */
  frameMarginRatio: 0.35,

  minimumZoomAltitudeMeters: 180,
  maximumZoomAltitudeMeters: 3_000_000,

  /** The globe-to-AOI flight. Long enough to read as a journey, short enough not to test patience. */
  descentDurationSeconds: 3.4,
  /** Flights inside the workspace — framing evidence, jumping between scenes. */
  localFlightDurationSeconds: 1.4,
  zoomInFactor: 0.55,
  zoomOutFactor: 1.8,
  zoomDurationSeconds: 0.5,

  /** Slow orbit used by present mode and by auto-play, in radians per second. */
  presentOrbitRadiansPerSecond: 0.012,
  /** Pitch the descent settles into. Slightly off nadir so relief and extrusions read as three-dimensional. */
  restingPitchDegrees: -62,
} as const;

export const INVESTIGATION_COMPARATOR = {
  /** Starting handle position, 0 (fully T1) to 1 (fully T0). */
  defaultPosition: 0.5,
  minimumPosition: 0.02,
  maximumPosition: 0.98,
  /** How close to a change centroid the handle must be dragged before it snaps to it, in screen fraction. */
  snapThreshold: 0.045,
  /** Duration of a commanded sweep across the scene — the reveal AERIS performs while it narrates. */
  sweepDurationMs: 2_600,
  /** Auto-play dissolve: seconds held at each end, seconds spent crossing. */
  playbackHoldSeconds: 1.1,
  playbackCrossSeconds: 1.8,
} as const;

export const INVESTIGATION_LAYOUT = {
  /** The trace spine's two heights. It is a strip by default and a panel when opened. */
  traceCollapsedHeightPx: 34,
  traceExpandedHeightPx: 216,
  identityStripHeightPx: 52,
  /** Region-draw popover offset from the drawn shape's screen position. */
  regionPromptOffsetPx: 14,
} as const;

export const INVESTIGATION_LIMITS = {
  /** Scenes attachable to one investigation. Beyond this the comparator stops being meaningful. */
  maximumScenes: 6,
  /** Vector features rendered before the stack starts dropping the least significant. */
  maximumVectorFeatures: 4_000,
  /** Above this, Cesium entities are the wrong renderer and the deck.gl overlay becomes justified. */
  deckGlConsiderationThreshold: 100_000,
  /** Trace steps retained in memory for one run. A run that emits more than this is malfunctioning. */
  maximumTraceSteps: 60,
} as const;

/** Which scene role occupies which side of the comparator, per workspace mode. */
export const COMPARATOR_BINDING = {
  temporal: { left: "t0", right: "t1" },
  crossModal: { left: "sar", right: "t1" },
} as const;

export type ComparatorBindingId = keyof typeof COMPARATOR_BINDING;
