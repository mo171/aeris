// components/sharedUI/functionalComponent/geoStage/geo-stage.types.ts — the renderer-agnostic contract of the shared 3D stage.
//
// what  : Every type the rest of the application needs in order to drive the Earth: camera verbs, globe
//         marker/track feeds, scene layer descriptors, the comparator, region drawing and appearance.
// where : Implemented by CesiumStage.tsx; consumed by features/missionCommand and features/investigation
//         through the handle published in store/geo-stage-store.ts.
// how   : This file contains no `cesium` import and never will. It is the reason a renderer swap costs
//         three call sites instead of a rewrite — the react-three-fiber → CesiumJS migration already
//         proved that, and the same boundary now covers the analysis surface as well as the globe.
//
//         The API is grouped by concern rather than flattened. A page uses only the groups it needs:
//         Mission Command touches `camera`, `globeLayers` and `appearance`; the Investigation Workspace
//         touches `camera`, `sceneLayers`, `comparator` and `regionDraw`. Grouping keeps each surface's
//         dependency on the stage legible, and makes an unused capability obvious at the call site.
//
//         Layer descriptors are DATA, not components. Adding a new analysis product — a flood mask, a
//         backscatter difference, a confidence field — means the backend emits one more descriptor and
//         no frontend file changes. That is the single decision that keeps this surface from growing
//         linearly with the science behind it.

/** Which instrument the stage is currently acting as. Governs zoom limits, idle behaviour and layers. */
export type StageMode = "globe" | "scene";

/**
 * Projection the scene is drawn in.
 *
 * `3D` is the globe. `2D` is a flat nadir projection — what an analyst wants for digitising an area of
 * interest, because in perspective every polygon edge is foreshortened by an amount that depends on where
 * it sits on screen, and precise tracing becomes guesswork. `columbus` is the 2.5D middle ground: a flat
 * map that still honours height, so extruded change is readable without perspective distortion.
 */
export type StageProjection = "3D" | "2D" | "columbus";

export interface StageGeoPoint {
  latitude: number;
  longitude: number;
}

export interface StageBoundingBox {
  west: number;
  south: number;
  east: number;
  north: number;
}

export interface StageFlyToTarget extends StageGeoPoint {
  /** Camera altitude above the ellipsoid in metres. Omit for the current mode's default. */
  altitudeMeters?: number;
  /** Animation length in milliseconds. Omit for the mode default; zero jumps instantly. */
  durationMs?: number;
  pitchDegrees?: number;
  headingDegrees?: number;
}

export interface StageFrameOptions {
  durationMs?: number;
  /** Extra room left around the box, as a fraction of its diagonal. */
  marginRatio?: number;
  pitchDegrees?: number;
}

/** A restorable camera pose. Persisted with an investigation so a shared URL reopens the same view. */
export interface StageCameraBookmark {
  latitude: number;
  longitude: number;
  altitudeMeters: number;
  headingDegrees: number;
  pitchDegrees: number;
}

export interface StageCameraApi {
  flyTo: (target: StageFlyToTarget) => void;
  /** Frames a bounding box, choosing the altitude that fits it. Used by the descent and by evidence focus. */
  flyToBoundingBox: (bounds: StageBoundingBox, options?: StageFrameOptions) => void;
  /**
   * Multiplies the camera's current altitude. Below 1 moves closer, above 1 moves away.
   * Multiplicative because a fixed metre step that feels right at street level is imperceptible from orbit.
   */
  zoomByFactor: (factor: number) => void;
  getBookmark: () => StageCameraBookmark | null;
  applyBookmark: (bookmark: StageCameraBookmark, durationMs?: number) => void;
  setAutoRotate: (isEnabled: boolean) => void;
  isAutoRotating: () => boolean;
  setZoomLimits: (minimumMeters: number, maximumMeters: number) => void;
  isFlying: () => boolean;
}

// ── Globe layers (Mission Command) ────────────────────────────────────────────────────────────────

export type StageMarkerStatus = "active" | "monitoring" | "alert" | "archived";

export interface StageMarker {
  id: string;
  label: string;
  position: StageGeoPoint;
  status: StageMarkerStatus;
  /** 0–1 relative importance. Drives radius, pulse amplitude and level-of-detail range. */
  magnitude: number;
}

export interface StageSatelliteTrack {
  id: string;
  origin: StageGeoPoint;
  destination: StageGeoPoint;
  /** 0–1 offset so no two arcs pulse in unison. */
  phase: number;
}

export interface StageGlobeLayersApi {
  setMarkers: (markers: readonly StageMarker[]) => void;
  setSatelliteTracks: (tracks: readonly StageSatelliteTrack[]) => void;
  setMarkerClickHandler: (handler: ((markerId: string) => void) | null) => void;
  clear: () => void;
}

// ── Scene layers (Investigation Workspace) ────────────────────────────────────────────────────────

export type StageLayerKind =
  | "raster-tiles"
  | "raster-mask"
  | "polygon-vector"
  | "point-vector"
  | "bbox-vector";

/** Draped classification and extrusion are different Cesium primitives, so this is not a boolean. */
export type StageLayerRenderMode = "draped" | "extruded";

/** Which half of the comparator a layer belongs to. Only raster layers can be split. */
export type StageComparatorSide = "left" | "right" | "both";

export type StageColorRampId =
  | "true-color"
  | "sar-grayscale"
  | "change-diverging"
  | "index-vegetation"
  | "confidence-magma"
  | "detection-teal"
  | "mask-amber"
  | "artefact-neutral";

export type StageFeatureGeometry =
  | { type: "polygon"; ring: readonly StageGeoPoint[] }
  | { type: "point"; position: StageGeoPoint }
  | { type: "bbox"; bounds: StageBoundingBox };

/**
 * One renderable piece of evidence.
 *
 * The numeric properties are not decoration: `magnitude` drives extrusion height, `confidence` drives
 * the muted rendering of uncertain regions, and `areaHectares` is what the answer panel quotes. A feature
 * arriving without them can be drawn but cannot be reasoned about.
 */
export interface StageFeature {
  id: string;
  label: string;
  geometry: StageFeatureGeometry;
  /** 0–1. Drives extrusion height and bloom ordering. */
  magnitude: number;
  confidence: number | null;
  areaHectares: number | null;
}

export interface StageLayer {
  id: string;
  kind: StageLayerKind;
  renderMode: StageLayerRenderMode;
  title: string;
  colorRampId: StageColorRampId;
  opacity: number;
  isVisible: boolean;
  comparatorSide: StageComparatorSide;
  /** Raster layers only. An XYZ template with {z}/{x}/{y} placeholders. */
  tileUrlTemplate: string | null;
  /** Attribution the tile provider requires. Rendered in the credit strip. */
  attribution: string | null;
  /** Coverage. Always supplied for rasters so Cesium never requests tiles outside the scene. */
  bounds: StageBoundingBox | null;
  minimumZoom: number | null;
  maximumZoom: number | null;
  /** Vector layers only. Rendered directly as primitives — no GeoJSON parsing step. */
  features: readonly StageFeature[];
}

export interface StageSceneLayersApi {
  /** Declarative sync. The stage diffs against what it already has; callers never add or remove by hand. */
  setLayers: (layers: readonly StageLayer[]) => void;
  setLayerVisibility: (layerId: string, isVisible: boolean) => void;
  setLayerOpacity: (layerId: string, opacity: number) => void;
  /** Switches every extrudable vector layer between draped and volumetric, with an animated growth. */
  setRenderMode: (renderMode: StageLayerRenderMode) => void;
  /**
   * Raises the named features and mutes everything else, including the basemap.
   * Null clears the spotlight and restores normal rendering.
   */
  setSpotlight: (featureIds: readonly string[] | null) => void;
  setFeatureClickHandler: (
    handler: ((featureId: string, layerId: string) => void) | null,
  ) => void;
  /** The area-of-interest outline drawn during and after the descent. Null removes it. */
  setAreaOfInterestOutline: (bounds: StageBoundingBox | null) => void;
  clear: () => void;
}

// ── Comparator ────────────────────────────────────────────────────────────────────────────────────

export interface StageComparatorApi {
  /** Assigns layers to the two halves. Passing null on both sides disables splitting entirely. */
  bind: (leftLayerId: string | null, rightLayerId: string | null) => void;
  /** 0 shows the right layer everywhere, 1 shows the left layer everywhere. */
  setPosition: (position: number) => void;
  getPosition: () => number;
  /** A commanded reveal — the sweep AERIS performs while it narrates a change. */
  sweep: (options?: { from?: number; to?: number; durationMs?: number }) => void;
  /** Ping-pong auto-play with an eased dissolve at each end. */
  setPlayback: (isPlaying: boolean) => void;
  isPlaying: () => boolean;
  /** Subscribes to position changes so a DOM handle can track a sweep it did not initiate. */
  subscribe: (listener: (position: number) => void) => () => void;
}

// ── Region drawing and measurement ────────────────────────────────────────────────────────────────

/**
 * How the operator defines a shape.
 *
 * Four modes because they answer different questions. A rectangle is fastest for "this block". A polygon
 * traces an administrative or physical boundary. Freehand follows a coastline or a river without fighting
 * vertex-by-vertex clicking. A circle asks "within N metres of here", which is how buffer questions are
 * actually posed.
 */
export type StageDrawMode = "rectangle" | "polygon" | "freehand" | "circle";

/** Measurement tools share the drawing machinery but commit a readout instead of a region. */
export type StageMeasureMode = "distance" | "area" | "bearing";

export type StageDrawTool = StageDrawMode | StageMeasureMode;

export interface StageDrawnRegion {
  id: string;
  mode: StageDrawMode;
  bounds: StageBoundingBox;
  ring: readonly StageGeoPoint[];
  /** Measured from the committed ring, not estimated — the backend crops to exactly this. */
  areaHectares: number;
  perimeterMeters: number;
  /** Where to anchor the follow-up prompt, in canvas pixels. */
  screenAnchor: { x: number; y: number };
}

/**
 * What the operator sees while a shape is still being drawn.
 *
 * Live area and perimeter are not a nicety: an analyst sizing an area of interest is deciding whether it
 * is the right scope, and discovering the size only after committing means drawing it twice.
 */
export interface StageDrawLiveState {
  tool: StageDrawTool | null;
  isDrawing: boolean;
  vertexCount: number;
  areaHectares: number;
  lengthMeters: number;
  bearingDegrees: number | null;
  /** Ground position under the pointer. Null when the pointer is off the globe. */
  cursor: StageGeoPoint | null;
}

export interface StageDrawApi {
  begin: (tool: StageDrawTool) => void;
  /** Closes the shape currently in progress. Polygons and paths need an explicit finish. */
  complete: () => void;
  /** Removes the last placed vertex. No-op for drag-defined shapes. */
  undoVertex: () => void;
  cancel: () => void;
  isDrawing: () => boolean;
  activeTool: () => StageDrawTool | null;
  /** Removes every committed region and measurement from the scene. */
  clearAll: () => void;
  removeRegion: (regionId: string) => void;
  subscribeRegions: (listener: (regions: readonly StageDrawnRegion[]) => void) => () => void;
  subscribeLive: (listener: (live: StageDrawLiveState) => void) => () => void;
}

// ── Appearance ────────────────────────────────────────────────────────────────────────────────────

export interface StageAppearanceApi {
  setMode: (mode: StageMode) => void;
  getMode: () => StageMode;
  /** Morphs between the globe, the flat map and the 2.5D middle ground. */
  setProjection: (projection: StageProjection) => void;
  getProjection: () => StageProjection;
  /** 1 is normal. Lower values recede the basemap so overlays dominate. */
  setBasemapBrightness: (brightness: number) => void;
  setMotionReduced: (isReduced: boolean) => void;
}

/** The complete imperative surface published once the viewer has painted its first frame. */
export interface GeoStageHandle {
  camera: StageCameraApi;
  globeLayers: StageGlobeLayersApi;
  sceneLayers: StageSceneLayersApi;
  comparator: StageComparatorApi;
  draw: StageDrawApi;
  appearance: StageAppearanceApi;
}
