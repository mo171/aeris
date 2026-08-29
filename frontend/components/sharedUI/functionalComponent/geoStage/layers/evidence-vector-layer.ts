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
  StripeMaterialProperty,
  StripeOrientation,
  type Viewer,
} from "cesium";

import {
  MAGNITUDE_SHADING,
  LAYER_RENDERING,
  MASK_HATCH_REPEAT,
  VECTOR_PALETTE,
} from "@/lib/constants/layers";
import { findOverlay } from "@/lib/constants/overlays";
import { resolveOverlayStyle } from "@/lib/overlay-style";

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
  /**
   * What draped evidence classifies onto.
   *
   * Terrain alone is right while the ground IS the terrain. Photorealistic 3D Tiles replace the ground
   * with a textured mesh and the globe is hidden underneath, so terrain-only classification would leave
   * every change mask with nothing to paint on — the evidence would simply vanish in that mode.
   */
  setClassificationTarget: (target: "terrain" | "both") => void;
  /**
   * Graduates fill colour by feature magnitude.
   *
   * Turned on whenever the scene cannot express magnitude as height — a flat projection, or draped mode —
   * so the attribute moves channel rather than disappearing.
   */
  setMagnitudeShading: (isEnabled: boolean) => void;
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
  let activeClassification: ClassificationType = ClassificationType.TERRAIN;
  let shadeByMagnitude = false;

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

  /**
   * The colours one feature draws in.
   *
   * The overlay catalogue answers first, so a value or a class decides the colour; the layer's own ramp is
   * the fallback for anything not catalogued — scene imagery, a product this build has not learned about.
   * Resolved once per feature at build time rather than per frame: values do not change while a layer is
   * on screen, and sampling a ramp inside a render callback would cost the frame budget for nothing.
   */
  function resolveFeaturePalette(descriptor: StageLayer, feature: StageFeature) {
    const fallback = VECTOR_PALETTE[descriptor.colorRampId];
    const style = resolveOverlayStyle({
      overlayId: descriptor.overlayId,
      valueDomain: descriptor.valueDomain,
      value: feature.value,
      classId: feature.classId,
    });

    return {
      fill: Color.fromCssColorString(style?.fill ?? fallback.fill),
      outline: Color.fromCssColorString(style?.outline ?? fallback.outline),
      highlight: Color.fromCssColorString(fallback.highlight),
      // Masks hatch rather than fill so they can never be mistaken at a glance for a coloured finding.
      // Stripes are Cesium's own material, so this costs no texture generation and survives every mode.
      isHatched: findOverlay(descriptor.overlayId)?.rendersAsHatch ?? false,
    };
  }

  /** Where a feature's value sits inside its layer's domain, 0–1. Used for extrusion height. */
  function normalisedFeatureValue(descriptor: StageLayer, feature: StageFeature): number {
    const overlay = findOverlay(descriptor.overlayId);
    const domain =
      descriptor.valueDomain ??
      (overlay?.encoding.kind === "continuous" ? overlay.encoding.domain : null);

    if (!domain || feature.value === null) {
      return feature.magnitude;
    }

    const span = domain.maximum - domain.minimum;
    if (span === 0) {
      return 0;
    }
    return Math.min(1, Math.max(0, (feature.value - domain.minimum) / span));
  }

  function buildPolygonEntities(
    tracked: TrackedFeature,
    layerId: string,
    descriptor: StageLayer,
    ring: readonly { latitude: number; longitude: number }[],
  ): Entity[] {
    const palette = resolveFeaturePalette(descriptor, tracked.feature);
    const fillColor = palette.fill;
    const outlineColor = palette.outline;
    const highlightColor = palette.highlight;

    const positions = ring.map((point) =>
      Cartesian3.fromDegrees(point.longitude, point.latitude),
    );
    const hierarchy = new PolygonHierarchy(positions);

    const resolveFillColor = () => {
      const base = tracked.state.isSpotlit ? highlightColor : fillColor;
      const alpha = resolveAlpha(tracked, layerId, LAYER_RENDERING.polygonFillAlphaRatio);

      if (!shadeByMagnitude || tracked.state.isSpotlit) {
        return base.withAlpha(alpha);
      }

      // Read straight from the feature, so the colour and the number in the inspector cannot disagree.
      const magnitude = tracked.feature.magnitude;
      const weight =
        MAGNITUDE_SHADING.minimumWeight +
        (MAGNITUDE_SHADING.maximumWeight - MAGNITUDE_SHADING.minimumWeight) * magnitude;
      const shaded =
        magnitude > MAGNITUDE_SHADING.brightenAboveMagnitude
          ? base.brighten(MAGNITUDE_SHADING.brightenAmount, new Color())
          : base;

      return shaded.withAlpha(alpha * weight);
    };

    // Cesium requires a MaterialProperty here, not a bare Property. Wrapping the callback in
    // ColorMaterialProperty is what lets the colour animate without rebuilding the entity every frame.
    // A hatched mask swaps that for stripes over transparency: the imagery stays readable underneath,
    // which is the whole point of saying "you cannot trust this" rather than painting over it.
    const fillMaterial = palette.isHatched
      ? new StripeMaterialProperty({
          evenColor: new CallbackProperty(() => resolveFillColor(), false),
          oddColor: new CallbackProperty(() => Color.TRANSPARENT, false),
          repeat: MASK_HATCH_REPEAT,
          orientation: StripeOrientation.VERTICAL,
        })
      : new ColorMaterialProperty(
          new CallbackProperty(() => resolveFillColor(), false),
        );

    if (activeRenderMode === "extruded") {
      // A heat-map surface is extruded by its MEASURED value, not by significance. That is what builds
      // the relief the reference imagery shows — peaks over the concentrations — and it means the height
      // an operator reads is the same number the inspector quotes. Everything else extrudes by magnitude,
      // which ranks findings rather than measuring them.
      const heightWeight =
        descriptor.kind === "heatmap-surface" && tracked.feature.value !== null
          ? normalisedFeatureValue(descriptor, tracked.feature)
          : tracked.feature.magnitude;

      const fullHeight = Math.max(
        LAYER_RENDERING.extrusionMinimumMeters,
        heightWeight * LAYER_RENDERING.extrusionMetersAtFullMagnitude,
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
          classificationType: activeClassification,
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
    const palette = resolveFeaturePalette(descriptor, tracked.feature);
    const outlineColor = palette.outline;
    const highlightColor = palette.highlight;

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
    const palette = resolveFeaturePalette(descriptor, tracked.feature);
    const fillColor = palette.fill;
    const highlightColor = palette.highlight;

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

  function setMagnitudeShading(isEnabled: boolean): void {
    // No rebuild: the fill is a CallbackProperty, so it picks this up on the next frame.
    shadeByMagnitude = isEnabled;
  }

  function setClassificationTarget(target: "terrain" | "both"): void {
    const next = target === "both" ? ClassificationType.BOTH : ClassificationType.TERRAIN;
    if (next === activeClassification) {
      return;
    }
    activeClassification = next;

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
    setClassificationTarget,
    setMagnitudeShading,
    setSpotlight,
    resolvePick,
    findFeature,
    update,
    clear,
  };
}
