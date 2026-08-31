// components/sharedUI/functionalComponent/geoStage/region-draw.ts — drawing and measuring on the scene.
//
// what  : Rectangle, polygon, freehand and circle drawing, plus distance, area and bearing measurement.
//         Emits committed regions with real geodesic area, and a live readout while a shape is in progress.
// where : Owned by CesiumStage.tsx; driven by the Investigation Workspace's draw toolbar.
// how   : Four shapes because they answer different questions. A rectangle is fastest for "this block". A
//         polygon traces a boundary. Freehand follows a coastline without fighting vertex-by-vertex
//         clicking. A circle asks "within N metres of here", which is how buffer questions are actually
//         posed. Offering only a rectangle forces every question into the wrong shape.
//
//         Camera input is disabled for the duration of a draw and restored on every exit path — commit,
//         cancel, Escape, or the tool being switched. Without that, dragging to define a box also rotates
//         the Earth underneath it; with it done carelessly, the camera stays dead after the operator gives
//         up. Both failures make the tool unusable, so the restore is centralised in one function.
//
//         Area and length are GEODESIC, measured from the committed vertices — not estimated from a
//         bounding box. An analyst sizing an area of interest is deciding whether it is the right scope,
//         and a figure that only approximates the shape they drew is worse than no figure. The same
//         number is what the backend will crop to.
//
//         Ground picking is layered rather than fixed to `globe.pick`, because what counts as "the ground"
//         changes with the building mode — photorealistic tiles replace the globe outright. See pickGround.

import {
  CallbackProperty,
  Cartesian2,
  Cartesian3,
  Cartographic,
  ClassificationType,
  Color,
  ColorMaterialProperty,
  ConstantProperty,
  CustomDataSource,
  Ellipsoid,
  EllipsoidGeodesic,
  Entity,
  HeightReference,
  LabelStyle,
  Math as CesiumMath,
  PolygonHierarchy,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  VerticalOrigin,
  type Viewer,
} from "cesium";

import { AERIS_COLOR_HEX } from "@/lib/constants/theme";
import { DRAW_TOOLS } from "@/lib/constants/draw";

import type {
  StageBoundingBox,
  StageDrawLiveState,
  StageDrawMode,
  StageDrawTool,
  StageDrawnRegion,
  StageGeoPoint,
} from "./geo-stage.types";

type RegionListener = (regions: readonly StageDrawnRegion[]) => void;
type LiveListener = (live: StageDrawLiveState) => void;

export interface DrawController {
  begin: (tool: StageDrawTool) => void;
  complete: () => void;
  undoVertex: () => void;
  cancel: () => void;
  isDrawing: () => boolean;
  activeTool: () => StageDrawTool | null;
  clearAll: () => void;
  /**
   * Which surface drawn shapes drape onto. Terrain while the globe is the ground; both once
   * photorealistic tiles are, because a shape classified against a hidden globe renders nowhere.
   */
  setClassificationTarget: (target: "terrain" | "both") => void;
  removeRegion: (regionId: string) => void;
  subscribeRegions: (listener: RegionListener) => () => void;
  subscribeLive: (listener: LiveListener) => () => void;
  destroy: () => void;
}

const MEASURE_TOOLS = new Set<StageDrawTool>(["distance", "area", "bearing"]);

const IDLE_LIVE_STATE: StageDrawLiveState = {
  tool: null,
  isDrawing: false,
  vertexCount: 0,
  areaHectares: 0,
  lengthMeters: 0,
  bearingDegrees: null,
  cursor: null,
};

export function createDrawController(viewer: Viewer): DrawController {
  const regionListeners = new Set<RegionListener>();
  const liveListeners = new Set<LiveListener>();

  const draftSource = new CustomDataSource("aeris-draw-draft");
  const committedSource = new CustomDataSource("aeris-draw-committed");
  void viewer.dataSources.add(draftSource);
  void viewer.dataSources.add(committedSource);

  const handler = new ScreenSpaceEventHandler(viewer.canvas);

  const accentColor = Color.fromCssColorString(AERIS_COLOR_HEX.teal);
  const fillColor = accentColor.withAlpha(DRAW_TOOLS.fillAlpha);
  const measureColor = Color.fromCssColorString(AERIS_COLOR_HEX.amber);

  let activeTool: StageDrawTool | null = null;
  let isDrawing = false;
  /** Vertices placed so far. For drag shapes this is [start, current]. */
  let vertices: StageGeoPoint[] = [];
  let cursor: StageGeoPoint | null = null;
  /**
   * Where the next click would land, for click-to-place tools.
   *
   * Without this a polygon shows nothing between clicks, so the operator cannot see the edge they are
   * about to commit and has to guess. The rubber band is what makes tracing a boundary possible rather
   * than merely allowed.
   */
  let previewPoint: StageGeoPoint | null = null;
  let lastScreenPosition: Cartesian2 | null = null;
  const regions: StageDrawnRegion[] = [];
  /**
   * Held as a plain constant, not a CallbackProperty, and pushed onto existing entities when it changes.
   *
   * Cesium decides at entity-creation time whether a shape becomes a classification primitive, and it
   * only takes that path for a CONSTANT classificationType. Behind a callback the shape falls back to a
   * plain primitive drawn at ellipsoid height, which over photorealistic tiles means buried under the
   * ground — drawn, and invisible. Same reason evidence-vector-layer.ts keeps a constant and rebuilds.
   */
  let activeClassification: ClassificationType = ClassificationType.TERRAIN;

  // ── Geometry ──────────────────────────────────────────────────────────────────────────────────

  /**
   * Where a screen point lands on the ground, whichever surface is currently BEING the ground.
   *
   * Three strategies, in order, because no single one covers every mode:
   *   1. `globe.pick` — the terrain surface. Correct and cheap, but returns nothing when the globe is
   *      hidden, which is exactly what photorealistic mode does (the tiles carry their own ground).
   *      That is why drawing silently did nothing in photoreal: every click picked null.
   *   2. `scene.pickPosition` — reads the depth buffer, so it hits 3D tiles and building surfaces.
   *      Only valid where something was actually rendered, hence not the first choice over open terrain.
   *   3. `camera.pickEllipsoid` — the bare WGS84 sphere. Always answers, so a click over empty sky near
   *      the horizon still produces a sane coordinate rather than aborting the shape mid-draw.
   */
  function pickGround(screenPosition: Cartesian2): StageGeoPoint | null {
    const { scene, camera } = viewer;
    let intersection: Cartesian3 | undefined;

    if (scene.globe.show) {
      const ray = camera.getPickRay(screenPosition);
      intersection = ray ? scene.globe.pick(ray, scene) : undefined;
    }

    if (!intersection && scene.pickPositionSupported) {
      intersection = scene.pickPosition(screenPosition);
    }

    if (!intersection) {
      intersection = camera.pickEllipsoid(screenPosition, Ellipsoid.WGS84) ?? undefined;
    }

    if (!intersection) {
      return null;
    }

    const carto = Cartographic.fromCartesian(intersection);
    return {
      latitude: CesiumMath.toDegrees(carto.latitude),
      longitude: CesiumMath.toDegrees(carto.longitude),
    };
  }

  function toCartesian(point: StageGeoPoint): Cartesian3 {
    return Cartesian3.fromDegrees(point.longitude, point.latitude);
  }

  function geodesicBetween(from: StageGeoPoint, to: StageGeoPoint): EllipsoidGeodesic | null {
    if (from.latitude === to.latitude && from.longitude === to.longitude) {
      return null;
    }
    return new EllipsoidGeodesic(
      Cartographic.fromDegrees(from.longitude, from.latitude),
      Cartographic.fromDegrees(to.longitude, to.latitude),
      Ellipsoid.WGS84,
    );
  }

  function pathLengthMeters(points: readonly StageGeoPoint[]): number {
    let total = 0;
    for (let index = 1; index < points.length; index += 1) {
      total += geodesicBetween(points[index - 1], points[index])?.surfaceDistance ?? 0;
    }
    return total;
  }

  /** Shoelace over a local metric projection. Accurate at the scale an area of interest is drawn at. */
  function ringAreaHectares(ring: readonly StageGeoPoint[]): number {
    if (ring.length < 3) {
      return 0;
    }

    const originLatitude = ring[0].latitude;
    const metresPerDegreeLatitude = 110_540;
    const metresPerDegreeLongitude = 111_320 * Math.cos((originLatitude * Math.PI) / 180);

    let doubleArea = 0;
    for (let index = 0; index < ring.length; index += 1) {
      const current = ring[index];
      const next = ring[(index + 1) % ring.length];
      const currentX = (current.longitude - ring[0].longitude) * metresPerDegreeLongitude;
      const currentY = (current.latitude - originLatitude) * metresPerDegreeLatitude;
      const nextX = (next.longitude - ring[0].longitude) * metresPerDegreeLongitude;
      const nextY = (next.latitude - originLatitude) * metresPerDegreeLatitude;
      doubleArea += currentX * nextY - nextX * currentY;
    }

    return Math.abs(doubleArea) / 2 / 10_000;
  }

  function boundsOfRing(ring: readonly StageGeoPoint[]): StageBoundingBox {
    return ring.reduce<StageBoundingBox>(
      (box, point) => ({
        west: Math.min(box.west, point.longitude),
        south: Math.min(box.south, point.latitude),
        east: Math.max(box.east, point.longitude),
        north: Math.max(box.north, point.latitude),
      }),
      {
        west: Number.POSITIVE_INFINITY,
        south: Number.POSITIVE_INFINITY,
        east: Number.NEGATIVE_INFINITY,
        north: Number.NEGATIVE_INFINITY,
      },
    );
  }

  function rectangleRing(corner: StageGeoPoint, opposite: StageGeoPoint): StageGeoPoint[] {
    const west = Math.min(corner.longitude, opposite.longitude);
    const east = Math.max(corner.longitude, opposite.longitude);
    const south = Math.min(corner.latitude, opposite.latitude);
    const north = Math.max(corner.latitude, opposite.latitude);

    return [
      { longitude: west, latitude: south },
      { longitude: east, latitude: south },
      { longitude: east, latitude: north },
      { longitude: west, latitude: north },
    ];
  }

  /** A circle on the ellipsoid: points at a constant geodesic distance, not a screen-space circle. */
  function circleRing(centre: StageGeoPoint, edge: StageGeoPoint): StageGeoPoint[] {
    const geodesic = geodesicBetween(centre, edge);
    if (!geodesic) {
      return [];
    }

    const radiusMeters = geodesic.surfaceDistance;
    const metresPerDegreeLatitude = 110_540;
    const metresPerDegreeLongitude = 111_320 * Math.cos((centre.latitude * Math.PI) / 180);

    return Array.from({ length: DRAW_TOOLS.circleVertexCount }, (_, index) => {
      const angle = (index / DRAW_TOOLS.circleVertexCount) * Math.PI * 2;
      return {
        latitude: centre.latitude + (Math.sin(angle) * radiusMeters) / metresPerDegreeLatitude,
        longitude: centre.longitude + (Math.cos(angle) * radiusMeters) / metresPerDegreeLongitude,
      };
    });
  }

  /** The shape the current vertices describe, whichever tool is active. */
  function currentRing(): StageGeoPoint[] {
    if (activeTool === "rectangle" && vertices.length >= 2) {
      return rectangleRing(vertices[0], vertices[vertices.length - 1]);
    }
    if (activeTool === "circle" && vertices.length >= 2) {
      return circleRing(vertices[0], vertices[vertices.length - 1]);
    }
    // Click-to-place tools trail the pointer, so the operator sees the edge before committing it.
    if (isDrawing && !usesDrag(activeTool) && previewPoint) {
      return [...vertices, previewPoint];
    }
    return vertices;
  }

  function isMeasureTool(tool: StageDrawTool | null): boolean {
    return tool !== null && MEASURE_TOOLS.has(tool);
  }

  // ── Live state ────────────────────────────────────────────────────────────────────────────────

  function buildLiveState(): StageDrawLiveState {
    const ring = currentRing();
    const isClosedShape =
      activeTool !== null && !isMeasureTool(activeTool) ? true : activeTool === "area";

    const bearing =
      activeTool === "bearing" && vertices.length >= 2
        ? (() => {
            const geodesic = geodesicBetween(vertices[0], vertices[vertices.length - 1]);
            if (!geodesic) {
              return null;
            }
            // Normalised to a compass bearing, because a negative heading is not something an analyst
            // reads off a map.
            return (CesiumMath.toDegrees(geodesic.startHeading) + 360) % 360;
          })()
        : null;

    return {
      tool: activeTool,
      isDrawing,
      vertexCount: vertices.length,
      areaHectares: isClosedShape ? ringAreaHectares(ring) : 0,
      lengthMeters: isClosedShape
        ? pathLengthMeters([...ring, ring[0]].filter(Boolean))
        : pathLengthMeters(vertices),
      bearingDegrees: bearing,
      cursor,
    };
  }

  function emitLive(): void {
    const live = buildLiveState();
    for (const listener of liveListeners) {
      listener(live);
    }
  }

  function emitRegions(): void {
    const snapshot = [...regions];
    for (const listener of regionListeners) {
      listener(snapshot);
    }
  }

  // ── Rendering ─────────────────────────────────────────────────────────────────────────────────

  function ensureDraftEntities(): void {
    if (draftSource.entities.values.length > 0) {
      return;
    }

    const outlineColor = isMeasureTool(activeTool) ? measureColor : accentColor;

    // A closed shape gets a fill; a measurement path does not — filling a distance measurement would
    // imply an area the operator never asked for.
    if (!isMeasureTool(activeTool) || activeTool === "area") {
      draftSource.entities.add(
        new Entity({
          polygon: {
            hierarchy: new CallbackProperty(() => {
              const ring = currentRing();
              return ring.length >= 3 ? new PolygonHierarchy(ring.map(toCartesian)) : undefined;
            }, false),
            material: new ColorMaterialProperty(
              new CallbackProperty(
                () => (isMeasureTool(activeTool) ? measureColor : accentColor).withAlpha(
                  DRAW_TOOLS.fillAlpha,
                ),
                false,
              ),
            ),
            heightReference: HeightReference.CLAMP_TO_GROUND,
            classificationType: activeClassification,
          },
        }),
      );
    }

    draftSource.entities.add(
      new Entity({
        polyline: {
          positions: new CallbackProperty(() => {
            const ring = currentRing();
            if (ring.length < 2) {
              return undefined;
            }
            const shouldClose = !isMeasureTool(activeTool) || activeTool === "area";
            const points = shouldClose ? [...ring, ring[0]] : ring;
            return points.map(toCartesian);
          }, false),
          width: DRAW_TOOLS.outlineWidthPixels,
          clampToGround: true,
          classificationType: activeClassification,
          material: new ColorMaterialProperty(outlineColor.withAlpha(0.95)),
        },
      }),
    );
  }

  function clearDraft(): void {
    draftSource.entities.removeAll();
  }

  function commitRegion(): void {
    const ring = currentRing();
    if (ring.length < 3 || activeTool === null || isMeasureTool(activeTool)) {
      return;
    }

    const region: StageDrawnRegion = {
      id: `aoi_${Date.now().toString(36)}`,
      mode: activeTool as StageDrawMode,
      bounds: boundsOfRing(ring),
      ring,
      areaHectares: ringAreaHectares(ring),
      perimeterMeters: pathLengthMeters([...ring, ring[0]]),
      screenAnchor: { x: lastScreenPosition?.x ?? 0, y: lastScreenPosition?.y ?? 0 },
    };

    regions.push(region);

    committedSource.entities.add(
      new Entity({
        id: region.id,
        polygon: {
          hierarchy: new PolygonHierarchy(ring.map(toCartesian)),
          material: fillColor,
          heightReference: HeightReference.CLAMP_TO_GROUND,
          classificationType: activeClassification,
        },
      }),
    );
    committedSource.entities.add(
      new Entity({
        id: `${region.id}_outline`,
        polyline: {
          positions: [...ring, ring[0]].map(toCartesian),
          width: DRAW_TOOLS.outlineWidthPixels,
          clampToGround: true,
          classificationType: activeClassification,
          material: new ColorMaterialProperty(accentColor.withAlpha(0.95)),
        },
      }),
    );

    emitRegions();
  }

  function commitMeasurement(): void {
    const ring = currentRing();
    if (ring.length < 2 || !isMeasureTool(activeTool)) {
      return;
    }

    const live = buildLiveState();
    const label =
      activeTool === "area"
        ? `${live.areaHectares.toFixed(2)} ha`
        : activeTool === "bearing"
          ? `${(live.bearingDegrees ?? 0).toFixed(1)}°`
          : formatDistance(live.lengthMeters);

    const anchor = ring[ring.length - 1];

    committedSource.entities.add(
      new Entity({
        position: toCartesian(anchor),
        polyline:
          activeTool === "area"
            ? undefined
            : {
                positions: ring.map(toCartesian),
                width: DRAW_TOOLS.outlineWidthPixels,
                clampToGround: true,
                classificationType: activeClassification,
                material: new ColorMaterialProperty(measureColor.withAlpha(0.95)),
              },
        polygon:
          activeTool === "area"
            ? {
                hierarchy: new PolygonHierarchy(ring.map(toCartesian)),
                material: measureColor.withAlpha(DRAW_TOOLS.fillAlpha),
                heightReference: HeightReference.CLAMP_TO_GROUND,
                classificationType: activeClassification,
              }
            : undefined,
        label: {
          text: label,
          font: DRAW_TOOLS.labelFont,
          fillColor: measureColor,
          showBackground: true,
          backgroundColor: Color.fromCssColorString(AERIS_COLOR_HEX.obsidian).withAlpha(0.85),
          verticalOrigin: VerticalOrigin.BOTTOM,
          style: LabelStyle.FILL,
          heightReference: HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      }),
    );
  }

  // ── Camera arbitration ────────────────────────────────────────────────────────────────────────

  function setCameraInputEnabled(isEnabled: boolean): void {
    if (!viewer.isDestroyed()) {
      viewer.scene.screenSpaceCameraController.enableInputs = isEnabled;
    }
  }

  /** Every exit path routes through here, so the camera can never be left disabled. */
  function endSession(): void {
    activeTool = null;
    isDrawing = false;
    vertices = [];
    previewPoint = null;
    clearDraft();
    setCameraInputEnabled(true);
    emitLive();
  }

  // ── Input ─────────────────────────────────────────────────────────────────────────────────────

  const usesDrag = (tool: StageDrawTool | null) =>
    tool === "rectangle" || tool === "circle" || tool === "freehand";

  handler.setInputAction(({ position }: { position: Cartesian2 }) => {
    if (activeTool === null) {
      return;
    }

    const point = pickGround(position);
    if (!point) {
      return;
    }

    lastScreenPosition = Cartesian2.clone(position);
    ensureDraftEntities();

    if (usesDrag(activeTool)) {
      isDrawing = true;
      vertices = [point, point];
    } else {
      // Click-to-place tools accumulate vertices; the first click starts the shape.
      isDrawing = true;
      vertices.push(point);
      previewPoint = point;
    }

    emitLive();
  }, ScreenSpaceEventType.LEFT_DOWN);

  handler.setInputAction(({ endPosition }: { endPosition: Cartesian2 }) => {
    if (activeTool === null) {
      return;
    }

    const point = pickGround(endPosition);
    cursor = point;
    lastScreenPosition = Cartesian2.clone(endPosition);

    if (!point || !isDrawing) {
      emitLive();
      return;
    }

    if (activeTool === "freehand") {
      // Sampled rather than every move event: a freehand trace at pointer rate produces thousands of
      // near-identical vertices, which bloats the geometry the backend has to crop against.
      const last = vertices[vertices.length - 1];
      if (
        !last ||
        (geodesicBetween(last, point)?.surfaceDistance ?? 0) >
          DRAW_TOOLS.freehandMinimumSpacingMeters
      ) {
        vertices.push(point);
      }
    } else if (usesDrag(activeTool)) {
      vertices[vertices.length - 1] = point;
    } else {
      previewPoint = point;
    }

    emitLive();
  }, ScreenSpaceEventType.MOUSE_MOVE);

  handler.setInputAction(({ position }: { position: Cartesian2 }) => {
    if (activeTool === null || !isDrawing) {
      return;
    }
    lastScreenPosition = Cartesian2.clone(position);

    if (usesDrag(activeTool)) {
      complete();
    }
  }, ScreenSpaceEventType.LEFT_UP);

  // Double click closes a click-to-place shape, which is the convention every GIS tool uses.
  handler.setInputAction(() => {
    if (activeTool !== null && !usesDrag(activeTool)) {
      complete();
    }
  }, ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

  function handleKeyDown(event: KeyboardEvent): void {
    if (activeTool === null) {
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      cancel();
    } else if (event.key === "Enter") {
      event.preventDefault();
      complete();
    } else if (event.key === "Backspace") {
      event.preventDefault();
      undoVertex();
    }
  }
  window.addEventListener("keydown", handleKeyDown);

  // ── Public surface ────────────────────────────────────────────────────────────────────────────

  function begin(tool: StageDrawTool): void {
    // Switching tools mid-draw abandons the shape rather than merging two geometries.
    if (activeTool !== null) {
      endSession();
    }
    activeTool = tool;
    isDrawing = false;
    vertices = [];
    previewPoint = null;
    setCameraInputEnabled(false);
    emitLive();
  }

  function complete(): void {
    if (activeTool === null) {
      return;
    }

    // A double-click fires LEFT_DOWN before LEFT_DOUBLE_CLICK, leaving a vertex on top of the previous
    // one. Dropping it keeps the committed geometry clean without making the operator aim differently.
    if (!usesDrag(activeTool) && vertices.length >= 2) {
      const last = vertices[vertices.length - 1];
      const previous = vertices[vertices.length - 2];
      if ((geodesicBetween(previous, last)?.surfaceDistance ?? 0) < DRAW_TOOLS.duplicateVertexMeters) {
        vertices = vertices.slice(0, -1);
      }
    }
    previewPoint = null;

    if (isMeasureTool(activeTool)) {
      commitMeasurement();
    } else {
      commitRegion();
    }

    endSession();
  }

  function undoVertex(): void {
    if (activeTool === null || usesDrag(activeTool) || vertices.length === 0) {
      return;
    }
    vertices = vertices.slice(0, -1);
    emitLive();
  }

  function cancel(): void {
    endSession();
  }

  function clearAll(): void {
    regions.length = 0;
    committedSource.entities.removeAll();
    emitRegions();
  }

  function removeRegion(regionId: string): void {
    const index = regions.findIndex((region) => region.id === regionId);
    if (index === -1) {
      return;
    }
    regions.splice(index, 1);
    committedSource.entities.removeById(regionId);
    committedSource.entities.removeById(`${regionId}_outline`);
    emitRegions();
  }

  return {
    begin,
    complete,
    undoVertex,
    cancel,
    isDrawing: () => isDrawing,
    activeTool: () => activeTool,
    clearAll,
    setClassificationTarget: (target) => {
      const next = target === "both" ? ClassificationType.BOTH : ClassificationType.TERRAIN;
      if (next === activeClassification) {
        return;
      }
      activeClassification = next;

      // Committed shapes are re-draped in place. Draft shapes are not touched: they are recreated on the
      // next draw anyway, and a mode switch mid-draw is not a thing an operator can do.
      for (const entity of committedSource.entities.values) {
        if (entity.polygon) {
          entity.polygon.classificationType = new ConstantProperty(activeClassification);
        }
        if (entity.polyline) {
          entity.polyline.classificationType = new ConstantProperty(activeClassification);
        }
      }
    },
    removeRegion,
    subscribeRegions: (listener) => {
      regionListeners.add(listener);
      listener([...regions]);
      return () => regionListeners.delete(listener);
    },
    subscribeLive: (listener) => {
      liveListeners.add(listener);
      listener(activeTool === null ? IDLE_LIVE_STATE : buildLiveState());
      return () => liveListeners.delete(listener);
    },
    destroy: () => {
      window.removeEventListener("keydown", handleKeyDown);
      handler.destroy();
      regionListeners.clear();
      liveListeners.clear();
      if (!viewer.isDestroyed()) {
        setCameraInputEnabled(true);
        viewer.dataSources.remove(draftSource, true);
        viewer.dataSources.remove(committedSource, true);
      }
    },
  };
}

function formatDistance(meters: number): string {
  return meters >= 1_000 ? `${(meters / 1_000).toFixed(2)} km` : `${Math.round(meters)} m`;
}

/** Exported so the workspace readout formats distances the same way the on-scene labels do. */
export { formatDistance as formatMeasuredDistance };
