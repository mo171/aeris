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

  /**
   * How close the camera may get.
   *
   * Was 180 m, which stopped the camera well before the imagery ran out — the operator's basemap resolves
   * to under a metre per pixel, so there were four zoom levels of detail nothing could reach. 55 m puts a
   * single building across the viewport, which is the scale object detections are actually checked at.
   */
  minimumZoomAltitudeMeters: 55,
  maximumZoomAltitudeMeters: 3_000_000,

  /** Pitch presets the tilt control steps through. Nadir for digitising, oblique for reading relief. */
  pitchPresetsDegrees: [-90, -62, -35] as const,
  /** One press of a rotate control. Twenty-two and a half degrees is a sixteenth of a turn. */
  orbitStepDegrees: 22.5,
  /** How long a commanded tilt or orbit takes. Short enough to feel like a control, not a flight. */
  orientDurationSeconds: 0.55,

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

/**
 * How the scene conveys height.
 *
 * Two separate mechanisms, because a city and a landscape hold their vertical information in different
 * places. Terrain exaggeration makes real relief legible over ground that is nearly flat; building
 * massing supplies the vertical structure that terrain data does not contain at all.
 */
export const SCENE_RELIEF = {
  /**
   * Terrain exaggeration on ARRIVAL: true scale.
   *
   * The scene should not distort before anyone has asked it to. An operator who descends onto a place and
   * is shown terrain 2.4 times its real height has been handed a picture that disagrees with every
   * measurement on the page, without being told.
   */
  defaultTerrainExaggeration: 1,

  /**
   * The boost an operator opts into, for open landscape.
   *
   * Where there are no buildings, a 30 m elevation model holds the only vertical information there is, and
   * relief across a few kilometres of farmland or desert is a fraction of a percent of the view. Scaling
   * height makes that readable. It scales height ONLY — horizontal position and every measured area are
   * untouched — and the factor is shown, so the scene never silently claims true scale.
   */
  boostedTerrainExaggeration: 2.4,
  exaggerationRange: { minimum: 1, maximum: 5, step: 0.2 },
  /**
   * How the built environment renders on entering the workspace: nothing.
   *
   * The descent lands on the operator's imagery and nothing else. Massing is genuinely useful but it is a
   * choice about how to READ the scene, and making it the default meant every investigation opened with
   * geometry nobody asked for, fetching tiles nobody had requested, over ground that in half the world has
   * no footprints anyway.
   *
   * Both alternatives stay one click away, and both are honest about their cost: massing is free and sits
   * on top of the imagery; photorealistic is metered and replaces it.
   */
  defaultBuildingMode: "none" as const,
  /**
   * Massing colour. A mid slate — desaturated, but light enough to read.
   *
   * Buildings are context here, not the finding, so this is deliberately not the default white, which
   * out-contrasts every evidence colour and turns an analysis surface into an architectural render. The
   * first attempt went too far the other way: near-black massing over dark imagery is invisible, which is
   * no better than not drawing it. The tileset carries normals, so sunlight separates the faces and a
   * mid-tone reads as volume without shouting.
   */
  buildingColorCss: "#33414F",
  buildingAlpha: 0.96,
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

/**
 * The detached scene inspector window.
 *
 * Portrait-ish because a quicklook is square and the metadata reads as a column beneath it. Sized to sit
 * comfortably beside a maximised workspace on one monitor rather than covering it.
 */
export const SCENE_POPOUT_WINDOW = {
  widthPx: 560,
  heightPx: 860,
  /** A detached window fires no close event the opener can subscribe to, so its state is polled. */
  closePollIntervalMs: 1_500,
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
