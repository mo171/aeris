// components/sharedUI/functionalComponent/geoStage/layers/mission-marker-layer.ts — mission markers on the shared globe.
//
// what  : Builds and maintains a single PointPrimitiveCollection of mission/AOI markers, applies
//         distance-based level of detail, pulses the alert ones, and resolves a pick back to its marker.
// where : Owned by CesiumStage.tsx. Imperative on purpose — this is scene-graph work, not rendering.
// how   : One PointPrimitiveCollection rather than thousands of Cesium Entities. An Entity carries a full
//         time-dynamic property machinery that costs far more than the point it draws; a primitive
//         collection uploads everything as one batch and renders in one draw call.
//
//         Level of detail is the important part. Drawing every marker at every altitude turns the orbital
//         view into confetti and communicates nothing, so each marker declares the camera range within
//         which it is worth showing — status first, magnitude as a modifier. From space you see alerts and
//         active investigations; the routine monitoring feed reveals itself as you descend. Cesium
//         evaluates the condition on the GPU, so the hidden markers are free.
//
//         Only alert markers pulse. Cesium rebuilds the collection's buffer when primitive properties
//         change, so animating every point every frame would be expensive — and a pulse that applies to
//         everything stops carrying information anyway.

import {
  Cartesian3,
  Color,
  DistanceDisplayCondition,
  NearFarScalar,
  PointPrimitiveCollection,
  type PointPrimitive,
  type Scene,
} from "cesium";

import { GLOBE_MARKERS } from "@/lib/constants/globe";

import type { StageMarker } from "../geo-stage.types";

/** Markers float slightly above the surface so terrain never swallows them at close range. */
const MARKER_HEIGHT_METERS = 4_000;

export interface MissionMarkerLayer {
  setMarkers: (markers: readonly StageMarker[]) => void;
  /** Advances the alert pulse. Called once per frame by the viewer's render loop. */
  update: (elapsedSeconds: number) => void;
  /** Resolves whatever Cesium's scene.pick returned into one of our markers, or null. */
  resolvePick: (picked: unknown) => StageMarker | null;
  destroy: () => void;
}

export function createMissionMarkerLayer(scene: Scene): MissionMarkerLayer {
  const collection = scene.primitives.add(new PointPrimitiveCollection());
  const markerByPrimitive = new WeakMap<object, StageMarker>();
  let pulsingPrimitives: { primitive: PointPrimitive; baseSize: number }[] = [];

  // Shared instances: Cesium reads these per frame, and allocating one per marker would waste memory
  // proportional to the feed size for values that never differ.
  const scaleByDistance = new NearFarScalar(
    GLOBE_MARKERS.scaleByDistance.nearMeters,
    GLOBE_MARKERS.scaleByDistance.nearScale,
    GLOBE_MARKERS.scaleByDistance.farMeters,
    GLOBE_MARKERS.scaleByDistance.farScale,
  );
  const translucencyByDistance = new NearFarScalar(
    GLOBE_MARKERS.translucencyByDistance.nearMeters,
    GLOBE_MARKERS.translucencyByDistance.nearAlpha,
    GLOBE_MARKERS.translucencyByDistance.farMeters,
    GLOBE_MARKERS.translucencyByDistance.farAlpha,
  );

  const colorCache = new Map<string, Color>();
  const resolveColor = (cssColor: string): Color => {
    let color = colorCache.get(cssColor);
    if (!color) {
      color = Color.fromCssColorString(cssColor);
      colorCache.set(cssColor, color);
    }
    return color;
  };

  const outlineColor = Color.fromCssColorString(GLOBE_MARKERS.outlineColor);

  function setMarkers(markers: readonly StageMarker[]): void {
    collection.removeAll();
    pulsingPrimitives = [];

    // Bound what reaches the GPU. When the cap bites, the highest-magnitude markers are the ones kept —
    // dropping the least significant is the only defensible way to truncate an evidence feed.
    const rendered =
      markers.length <= GLOBE_MARKERS.maxRenderedMarkers
        ? markers
        : [...markers]
            .sort((left, right) => right.magnitude - left.magnitude)
            .slice(0, GLOBE_MARKERS.maxRenderedMarkers);

    for (const marker of rendered) {
      const pixelSize =
        GLOBE_MARKERS.basePixelSize + marker.magnitude * GLOBE_MARKERS.magnitudePixelRange;

      const primitive = collection.add({
        position: Cartesian3.fromDegrees(
          marker.position.longitude,
          marker.position.latitude,
          MARKER_HEIGHT_METERS,
        ),
        color: resolveColor(GLOBE_MARKERS.statusColor[marker.status]),
        pixelSize,
        outlineColor,
        outlineWidth: GLOBE_MARKERS.outlineWidth,
        scaleByDistance,
        translucencyByDistance,
        distanceDisplayCondition: buildVisibilityRange(marker),
      }) as PointPrimitive;

      markerByPrimitive.set(primitive, marker);

      if (marker.status === "alert") {
        pulsingPrimitives.push({ primitive, baseSize: pixelSize });
      }
    }
  }

  function update(elapsedSeconds: number): void {
    if (pulsingPrimitives.length === 0) {
      return;
    }

    const phase = Math.sin(elapsedSeconds * GLOBE_MARKERS.pulseSpeed) * 0.5 + 0.5;
    const growth = phase * GLOBE_MARKERS.pulsePixelAmplitude;

    for (const { primitive, baseSize } of pulsingPrimitives) {
      primitive.pixelSize = baseSize + growth;
    }
  }

  function resolvePick(picked: unknown): StageMarker | null {
    if (!picked || typeof picked !== "object") {
      return null;
    }

    // Cesium returns either the primitive itself or a wrapper carrying it, depending on the primitive
    // type. Check both rather than depending on which one this version happens to hand back.
    const direct = markerByPrimitive.get(picked as object);
    if (direct) {
      return direct;
    }

    const candidate = picked as { primitive?: unknown };
    if (candidate.primitive && typeof candidate.primitive === "object") {
      return markerByPrimitive.get(candidate.primitive as object) ?? null;
    }

    return null;
  }

  function destroy(): void {
    pulsingPrimitives = [];
    if (!collection.isDestroyed()) {
      scene.primitives.remove(collection);
    }
  }

  return { setMarkers, update, resolvePick, destroy };
}

/**
 * The camera range within which a marker is worth drawing.
 *
 * Near is always zero — a marker should never disappear because the operator got close to it. Far is
 * driven by status, then stretched or compressed by magnitude, so a significant monitoring site survives
 * further out than a routine one without ever outranking an alert.
 */
function buildVisibilityRange(marker: StageMarker): DistanceDisplayCondition {
  const statusRange = GLOBE_MARKERS.visibilityRangeMeters[marker.status];
  const magnitudeFactor =
    GLOBE_MARKERS.magnitudeRangeFloor + marker.magnitude * GLOBE_MARKERS.magnitudeRangeSpan;

  return new DistanceDisplayCondition(0, statusRange * magnitudeFactor);
}
