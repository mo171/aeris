// components/sharedUI/functionalComponent/geoStage/layers/evidence-vector-layer.ts — clickable, extrudable evidence geometry.
//
// what  : Renders change polygons, detection boxes and point evidence; animates their arrival, switches
//         them between draped and volumetric, drives the spotlight, and resolves a pick back to a feature.
// where : Owned by CesiumStage.tsx. Every vector layer in the Investigation Workspace goes through here.
// how   : Geometry arrives as our own typed features rather than as GeoJSON. That is deliberate: the
//         numeric properties an analyst reasons about — magnitude, confidence, area — are first-class
//         typed fields instead of an untyped `properties` bag, and there is no parsing step between the
//         wire and the screen.
//
//         Draped and extruded are genuinely different primitives, not a property. Cesium's terrain
//         classification (`ClassificationType.TERRAIN`) draws a polygon onto the ground and cannot be
//         extruded; extrusion needs an absolute-height polygon which is not classified. So the volumetric
//         toggle rebuilds the geometry rather than flipping a flag, which is why `renderMode` lives in the
//         layer descriptor and not as a boolean on a primitive.
//
//         Animation runs through CallbackProperty reading a mutable per-feature state object. Cesium
//         evaluates those once per frame itself, so the update loop only advances numbers — it never
//         writes entity properties, which would mark the collection dirty and rebuild its buffers.
//
//         Scale note: entities with time-varying materials are the right tool for the tens-to-hundreds of
//         polygons a change-detection run produces. Past roughly a thousand this becomes the wrong
//         renderer, and that is precisely the threshold at which a deck.gl overlay earns its place.

import {
  CallbackProperty,
  Cartesian3,
  ClassificationType,
  Color,
  ColorMaterialProperty,
  CustomDataSource,
  Entity,
  HeightReference,
  PolygonHierarchy,
  type Viewer,
} from "cesium";

import { LAYER_RENDERING, VECTOR_PALETTE } from "@/lib/constants/layers";

import type { StageFeature, StageLayer, StageLayerRenderMode } from "../geo-stage.types";

/** Mutable visual state per feature. Read by CallbackProperty every frame; written by update(). */
interface FeatureVisualState {
  /** 0–1 arrival progress. Drives opacity so evidence blooms in rather than appearing. */
  reveal: number;
  revealStartMs: number;
  /** 0–1 extrusion progress. 0 is flat, 1 is full magnitude height. */
  extrusion: number;
  isSpotlit: boolean;
  isMuted: boolean;
}

interface TrackedFeature {
  feature: StageFeature;
  state: FeatureVisualState;
  entities: Entity[];
}

interface TrackedLayer {
  descriptor: StageLayer;
  dataSource: CustomDataSource;
  features: Map<string, TrackedFeature>;
}

export interface EvidenceVectorLayerSet {
  sync: (layers: readonly StageLayer[], renderMode: StageLayerRenderMode) => void;
  setVisibility: (layerId: string, isVisible: boolean) => void;
  setOpacity: (layerId: string, opacity: number) => void;
  setRenderMode: (renderMode: StageLayerRenderMode) => void;
  setSpotlight: (featureIds: readonly string[] | null) => void;
  resolvePick: (picked: unknown) => { featureId: string; layerId: string } | null;
  findFeature: (featureId: string) => { feature: StageFeature; layerId: string } | null;
  update: (nowMs: number) => void;
  clear: () => void;
}

export function createEvidenceVectorLayerSet(viewer: Viewer): EvidenceVectorLayerSet {
  const layers = new Map<string, TrackedLayer>();
  const entityToFeature = new WeakMap<object, { featureId: string; layerId: string }>();
  let activeRenderMode: StageLayerRenderMode = "draped";

  function layerOpacity(layerId: string): number {
    return layers.get(layerId)?.descriptor.opacity ?? 1;
  }

  /**
   * Effective alpha for one feature: arrival progress, then the layer's opacity, then the spotlight.
   * Muted evidence never disappears entirely — an operator must still see that something is there,
   * just not be drawn to it.
   */
  function resolveAlpha(tracked: TrackedFeature, layerId: string, baseRatio: number): number {
    const { state } = tracked;
    const spotlightFactor = state.isMuted ? LAYER_RENDERING.spotlightMutedAlphaRatio : 1;
    return state.reveal * layerOpacity(layerId) * baseRatio * spotlightFactor;
  }

  function buildPolygonEntities(
    tracked: TrackedFeature,
    layerId: string,
    descriptor: StageLayer,
    ring: readonly { latitude: number; longitude: number }[],
  ): Entity[] {
    const palette = VECTOR_PALETTE[descriptor.colorRampId];
    const fillColor = Color.fromCssColorString(palette.fill);
    const outlineColor = Color.fromCssColorString(palette.outline);
    const highlightColor = Color.fromCssColorString(palette.highlight);

    const positions = ring.map((point) =>
      Cartesian3.fromDegrees(point.longitude, point.latitude),
    );
    const hierarchy = new PolygonHierarchy(positions);

    // Cesium requires a MaterialProperty here, not a bare Property. Wrapping the callback in
    // ColorMaterialProperty is what lets the colour animate without rebuilding the entity every frame.
    const fillMaterial = new ColorMaterialProperty(
      new CallbackProperty(() => {
        const base = tracked.state.isSpotlit ? highlightColor : fillColor;
        return base.withAlpha(
          resolveAlpha(tracked, layerId, LAYER_RENDERING.polygonFillAlphaRatio),
        );
      }, false),
    );

    if (activeRenderMode === "extruded") {
      const fullHeight = Math.max(
        LAYER_RENDERING.extrusionMinimumMeters,
        tracked.feature.magnitude * LAYER_RENDERING.extrusionMetersAtFullMagnitude,
      );

      return [
        new Entity({
          polygon: {
            hierarchy,
            height: LAYER_RENDERING.vectorHeightOffsetMeters,
            extrudedHeight: new CallbackProperty(
              () => LAYER_RENDERING.vectorHeightOffsetMeters + fullHeight * tracked.state.extrusion,
              false,
            ),
            material: fillMaterial,
            outline: true,
            outlineColor: new CallbackProperty(
              () => outlineColor.withAlpha(resolveAlpha(tracked, layerId, 1)),
              false,
            ),
            outlineWidth: LAYER_RENDERING.polygonOutlineWidthPixels,
          },
        }),
      ];
    }

    // Draped: a classified fill plus a ground-clamped outline. Ground primitives cannot draw their own
    // outline, so the boundary is a separate clamped polyline — without it, adjacent change regions
    // merge into one indistinct blob.
    return [
      new Entity({
        polygon: {
          hierarchy,
          material: fillMaterial,
          classificationType: ClassificationType.TERRAIN,
        },
      }),
      new Entity({
        polyline: {
          positions: [...positions, positions[0]],
          width: LAYER_RENDERING.polygonOutlineWidthPixels,
          clampToGround: true,
          material: new ColorMaterialProperty(
            new CallbackProperty(
              () =>
                (tracked.state.isSpotlit ? highlightColor : outlineColor).withAlpha(
                  resolveAlpha(tracked, layerId, 1),
                ),
              false,
            ),
          ),
        },
      }),
    ];
  }

  function buildBoundingBoxEntity(
    tracked: TrackedFeature,
    layerId: string,
    descriptor: StageLayer,
    bounds: { west: number; south: number; east: number; north: number },
  ): Entity[] {
    const palette = VECTOR_PALETTE[descriptor.colorRampId];
    const outlineColor = Color.fromCssColorString(palette.outline);
    const highlightColor = Color.fromCssColorString(palette.highlight);

    const corners = [
      { longitude: bounds.west, latitude: bounds.south },
      { longitude: bounds.east, latitude: bounds.south },
      { longitude: bounds.east, latitude: bounds.north },
      { longitude: bounds.west, latitude: bounds.north },
      { longitude: bounds.west, latitude: bounds.south },
    ];

    return [
      new Entity({
        polyline: {
          positions: corners.map((corner) =>
            Cartesian3.fromDegrees(corner.longitude, corner.latitude),
          ),
          width: LAYER_RENDERING.bboxOutlineWidthPixels,
          clampToGround: true,
          material: new ColorMaterialProperty(
            new CallbackProperty(
              () =>
                (tracked.state.isSpotlit ? highlightColor : outlineColor).withAlpha(
                  resolveAlpha(tracked, layerId, 1),
                ),
              false,
            ),
          ),
        },
      }),
    ];
  }

  function buildPointEntity(
    tracked: TrackedFeature,
    layerId: string,
    descriptor: StageLayer,
    position: { latitude: number; longitude: number },
  ): Entity[] {
    const palette = VECTOR_PALETTE[descriptor.colorRampId];
    const fillColor = Color.fromCssColorString(palette.fill);
    const highlightColor = Color.fromCssColorString(palette.highlight);

    return [
      new Entity({
        position: Cartesian3.fromDegrees(position.longitude, position.latitude),
        point: {
          pixelSize: 8 + tracked.feature.magnitude * 6,
          heightReference: HeightReference.CLAMP_TO_GROUND,
          color: new CallbackProperty(
            () =>
              (tracked.state.isSpotlit ? highlightColor : fillColor).withAlpha(
                resolveAlpha(tracked, layerId, 1),
              ),
            false,
          ),
          outlineColor: Color.fromCssColorString("#0A0D14"),
          outlineWidth: 1.5,
        },
      }),
    ];
  }

  function buildFeature(
    layerId: string,
    descriptor: StageLayer,
    feature: StageFeature,
    revealStartMs: number,
  ): TrackedFeature {
    const tracked: TrackedFeature = {
      feature,
      state: {
        reveal: 0,
        revealStartMs,
        extrusion: activeRenderMode === "extruded" ? 0 : 0,
        isSpotlit: false,
        isMuted: false,
      },
      entities: [],
    };

    switch (feature.geometry.type) {
      case "polygon":
        tracked.entities = buildPolygonEntities(tracked, layerId, descriptor, feature.geometry.ring);
        break;
      case "bbox":
        tracked.entities = buildBoundingBoxEntity(
          tracked,
          layerId,
          descriptor,
          feature.geometry.bounds,
        );
        break;
      case "point":
        tracked.entities = buildPointEntity(
          tracked,
          layerId,
          descriptor,
          feature.geometry.position,
        );
        break;
    }

    for (const entity of tracked.entities) {
      entityToFeature.set(entity, { featureId: feature.id, layerId });
    }

    return tracked;
  }

  function populateLayer(trackedLayer: TrackedLayer, descriptor: StageLayer): void {
    trackedLayer.dataSource.entities.removeAll();
    trackedLayer.features.clear();

    // Largest magnitude first, so the bloom leads the eye to the most significant change without
    // needing a label or an arrow to point at it.
    const ordered = [...descriptor.features].sort((left, right) => right.magnitude - left.magnitude);
    const stagger = Math.min(
      LAYER_RENDERING.bloomStaggerMs,
      ordered.length > 0 ? LAYER_RENDERING.bloomMaximumTotalMs / ordered.length : 0,
    );
    const now = performance.now();

    ordered.forEach((feature, index) => {
      const tracked = buildFeature(descriptor.id, descriptor, feature, now + index * stagger);
      for (const entity of tracked.entities) {
        trackedLayer.dataSource.entities.add(entity);
      }
      trackedLayer.features.set(feature.id, tracked);
    });
  }

  function sync(incoming: readonly StageLayer[], renderMode: StageLayerRenderMode): void {
    const renderModeChanged = renderMode !== activeRenderMode;
    activeRenderMode = renderMode;

    const vectorLayers = incoming.filter(
      (layer) =>
        layer.kind === "polygon-vector" ||
        layer.kind === "point-vector" ||
        layer.kind === "bbox-vector",
    );
    const incomingIds = new Set(vectorLayers.map((layer) => layer.id));

    for (const [layerId, trackedLayer] of layers) {
      if (!incomingIds.has(layerId)) {
        viewer.dataSources.remove(trackedLayer.dataSource, true);
        layers.delete(layerId);
      }
    }

    for (const descriptor of vectorLayers) {
      const existing = layers.get(descriptor.id);

      if (!existing) {
        const dataSource = new CustomDataSource(descriptor.id);
        void viewer.dataSources.add(dataSource);
        const trackedLayer: TrackedLayer = { descriptor, dataSource, features: new Map() };
        layers.set(descriptor.id, trackedLayer);
        populateLayer(trackedLayer, descriptor);
        dataSource.show = descriptor.isVisible;
        continue;
      }

      const featuresChanged =
        existing.descriptor.features !== descriptor.features ||
        existing.descriptor.colorRampId !== descriptor.colorRampId;

      existing.descriptor = descriptor;
      existing.dataSource.show = descriptor.isVisible;

      if (featuresChanged || renderModeChanged) {
        populateLayer(existing, descriptor);
      }
    }
  }

  function setVisibility(layerId: string, isVisible: boolean): void {
    const trackedLayer = layers.get(layerId);
    if (trackedLayer) {
      trackedLayer.descriptor = { ...trackedLayer.descriptor, isVisible };
      trackedLayer.dataSource.show = isVisible;
    }
  }

  function setOpacity(layerId: string, opacity: number): void {
    const trackedLayer = layers.get(layerId);
    if (trackedLayer) {
      trackedLayer.descriptor = { ...trackedLayer.descriptor, opacity };
    }
  }

  function setRenderMode(renderMode: StageLayerRenderMode): void {
    if (renderMode === activeRenderMode) {
      return;
    }
    activeRenderMode = renderMode;

    for (const trackedLayer of layers.values()) {
      populateLayer(trackedLayer, trackedLayer.descriptor);
    }
  }

  function setSpotlight(featureIds: readonly string[] | null): void {
    const spotlit = featureIds === null ? null : new Set(featureIds);

    for (const trackedLayer of layers.values()) {
      for (const [featureId, tracked] of trackedLayer.features) {
        tracked.state.isSpotlit = spotlit !== null && spotlit.has(featureId);
        tracked.state.isMuted = spotlit !== null && !spotlit.has(featureId);
      }
    }
  }

  function resolvePick(picked: unknown): { featureId: string; layerId: string } | null {
    if (!picked || typeof picked !== "object") {
      return null;
    }

    // Entity picks arrive wrapped: scene.pick returns an object whose `id` is the Entity itself.
    const candidate = picked as { id?: unknown };
    const entity = candidate.id ?? picked;
    if (!entity || typeof entity !== "object") {
      return null;
    }

    return entityToFeature.get(entity as object) ?? null;
  }

  function findFeature(featureId: string): { feature: StageFeature; layerId: string } | null {
    for (const [layerId, trackedLayer] of layers) {
      const tracked = trackedLayer.features.get(featureId);
      if (tracked) {
        return { feature: tracked.feature, layerId };
      }
    }
    return null;
  }

  function update(nowMs: number): void {
    for (const trackedLayer of layers.values()) {
      for (const tracked of trackedLayer.features.values()) {
        const { state } = tracked;

        if (state.reveal < 1) {
          const elapsed = nowMs - state.revealStartMs;
          state.reveal =
            elapsed <= 0 ? 0 : Math.min(1, elapsed / LAYER_RENDERING.extrusionGrowthMs);
        }

        const extrusionTarget = activeRenderMode === "extruded" ? state.reveal : 0;
        if (state.extrusion !== extrusionTarget) {
          // Ease toward the target so switching volumetric mode grows the skyline rather than snapping it.
          state.extrusion += (extrusionTarget - state.extrusion) * 0.08;
          if (Math.abs(extrusionTarget - state.extrusion) < 0.002) {
            state.extrusion = extrusionTarget;
          }
        }
      }
    }
  }

  function clear(): void {
    for (const trackedLayer of layers.values()) {
      viewer.dataSources.remove(trackedLayer.dataSource, true);
    }
    layers.clear();
  }

  return {
    sync,
    setVisibility,
    setOpacity,
    setRenderMode,
    setSpotlight,
    resolvePick,
    findFeature,
    update,
    clear,
  };
}
