// components/sharedUI/functionalComponent/geoStage/layers/scene-imagery-layer.ts — operator scene rasters on the globe.
//
// what  : Adds, grades, splits and cross-fades the XYZ raster layers that carry the operator's imagery —
//         T0, T1, SAR, index maps and change masks.
// where : Owned by CesiumStage.tsx, driven by the scene-layer descriptors the backend sends.
// how   : Layers are added and faded, never swapped. Removing one layer and adding another in the same
//         frame shows the black globe underneath for exactly one frame, which is the definition of a
//         glitchy transition; ramping `alpha` on the incoming layer while the outgoing one is still
//         present costs nothing and is invisible.
//
//         Every provider is given its rectangle and maximum level from the descriptor. Without them
//         Cesium requests tiles across the whole planet and collects 404s from a tiler that only holds
//         one scene — the most common first-day failure when wiring a real tile service.
//
//         Splitting is Cesium's own `splitDirection` plus `scene.splitPosition`. It is the reason this
//         project stayed on one engine: the before/after reveal is two properties here and a hand-rolled
//         clip mask anywhere else.

import {
  ImageryLayer,
  Rectangle,
  SplitDirection,
  UrlTemplateImageryProvider,
  type Scene,
} from "cesium";

import { LAYER_DEFAULT_MAX_ZOOM, RASTER_CROSS_FADE_MS, RASTER_GRADING } from "@/lib/constants/layers";

import type { StageComparatorSide, StageLayer } from "../geo-stage.types";



// A removed raster is kept on the globe and faded out over the same duration rather than dropped on the
// frame its replacement is added. Removing immediately drops straight through to the basemap for the
// length of the incoming fade — invisible when layers change once, impossible to miss when the operator
// is scrubbing, where every step would flash.

interface TrackedRaster {
  layer: ImageryLayer;
  descriptor: StageLayer;
  targetAlpha: number;
  fadeStartedAt: number;
  /** Set when the descriptor list stopped containing this layer. Removed once it has faded out. */
  retiringSince: number | null;
  /** Opacity at the moment retirement began, so the fade interpolates rather than compounding. */
  retiringFromAlpha: number;
}

export interface SceneImageryLayerSet {
  /** Declarative sync against a descriptor list. Returns the ids that were newly added. */
  sync: (layers: readonly StageLayer[]) => string[];
  setVisibility: (layerId: string, isVisible: boolean) => void;
  setOpacity: (layerId: string, opacity: number) => void;
  bindComparator: (leftLayerId: string | null, rightLayerId: string | null) => void;
  /** Multiplies every raster's alpha — used to recede the scene while an evidence spotlight is active. */
  setGlobalDim: (factor: number) => void;
  /** Overrides the cross-fade length. Scrubbing shortens it; deliberate layer changes keep the default. */
  setCrossFadeMs: (durationMs: number) => void;
  /** True when nothing is mid-fade and every visible raster has its provider ready. */
  isSettled: () => boolean;
  update: (nowMs: number) => void;
  clear: () => void;
  destroy: () => void;
}

export function createSceneImageryLayerSet(scene: Scene): SceneImageryLayerSet {
  const tracked = new Map<string, TrackedRaster>();
  let globalDim = 1;
  let crossFadeMs: number = RASTER_CROSS_FADE_MS.settled;

  function resolveAlpha(entry: TrackedRaster): number {
    if (entry.retiringSince !== null) {
      return 0;
    }
    return entry.descriptor.isVisible ? entry.targetAlpha * globalDim : 0;
  }

  function applyGrading(layer: ImageryLayer, descriptor: StageLayer): void {
    const grading = RASTER_GRADING[descriptor.colorRampId];
    layer.brightness = grading.brightness;
    layer.contrast = grading.contrast;
    layer.saturation = grading.saturation;
    layer.gamma = grading.gamma;
  }

  function buildLayer(descriptor: StageLayer): ImageryLayer | null {
    if (!descriptor.tileUrlTemplate) {
      return null;
    }

    const rectangle = descriptor.bounds
      ? Rectangle.fromDegrees(
          descriptor.bounds.west,
          descriptor.bounds.south,
          descriptor.bounds.east,
          descriptor.bounds.north,
        )
      : undefined;

    const layer = new ImageryLayer(
      new UrlTemplateImageryProvider({
        url: descriptor.tileUrlTemplate,
        rectangle,
        minimumLevel: descriptor.minimumZoom ?? 0,
        maximumLevel: descriptor.maximumZoom ?? LAYER_DEFAULT_MAX_ZOOM,
        credit: descriptor.attribution ?? undefined,
      }),
    );

    applyGrading(layer, descriptor);
    // Starts invisible so the fade below is the only thing that reveals it.
    layer.alpha = 0;
    return layer;
  }

  function sync(layers: readonly StageLayer[]): string[] {
    const rasterLayers = layers.filter(
      (layer) => layer.kind === "raster-tiles" || layer.kind === "raster-mask",
    );
    const incomingIds = new Set(rasterLayers.map((layer) => layer.id));
    const addedIds: string[] = [];
    const now = performance.now();

    for (const [layerId, entry] of tracked) {
      if (!incomingIds.has(layerId) && entry.retiringSince === null) {
        // Marked, not removed. update() takes it off the globe once it has faded out.
        entry.retiringSince = now;
        entry.retiringFromAlpha = entry.layer.alpha;
      }
    }

    // Descriptor order is draw order: later entries sit above earlier ones.
    for (const descriptor of rasterLayers) {
      const existing = tracked.get(descriptor.id);

      if (existing) {
        existing.descriptor = descriptor;
        existing.targetAlpha = descriptor.opacity;
        applyGrading(existing.layer, descriptor);
        if (existing.retiringSince !== null) {
          // Scrubbed away and back again before the fade finished. The tiles are still resident, so it
          // returns to full opacity immediately rather than fading in over imagery already on screen.
          existing.retiringSince = null;
          existing.fadeStartedAt = 0;
        }
        continue;
      }

      const layer = buildLayer(descriptor);
      if (!layer) {
        continue;
      }

      scene.imageryLayers.add(layer);
      tracked.set(descriptor.id, {
        layer,
        descriptor,
        targetAlpha: descriptor.opacity,
        fadeStartedAt: now,
        retiringSince: null,
        retiringFromAlpha: 0,
      });
      addedIds.push(descriptor.id);
    }

    return addedIds;
  }

  function setVisibility(layerId: string, isVisible: boolean): void {
    const entry = tracked.get(layerId);
    if (entry) {
      entry.descriptor = { ...entry.descriptor, isVisible };
    }
  }

  function setOpacity(layerId: string, opacity: number): void {
    const entry = tracked.get(layerId);
    if (entry) {
      entry.targetAlpha = opacity;
      entry.descriptor = { ...entry.descriptor, opacity };
      // An opacity drag must respond immediately rather than easing behind the cursor.
      entry.fadeStartedAt = 0;
    }
  }

  function assignSide(layerId: string | null, side: StageComparatorSide): void {
    if (!layerId) {
      return;
    }
    const entry = tracked.get(layerId);
    if (!entry) {
      return;
    }
    entry.layer.splitDirection =
      side === "left" ? SplitDirection.LEFT : side === "right" ? SplitDirection.RIGHT : SplitDirection.NONE;
  }

  function bindComparator(leftLayerId: string | null, rightLayerId: string | null): void {
    for (const entry of tracked.values()) {
      // A retiring layer keeps the side it was bound to. Releasing it to NONE would spread the outgoing
      // date across the whole scene for the length of its fade — visible on every scrub step.
      if (entry.retiringSince === null) {
        entry.layer.splitDirection = SplitDirection.NONE;
      }
    }
    assignSide(leftLayerId, "left");
    assignSide(rightLayerId, "right");
  }

  function setGlobalDim(factor: number): void {
    globalDim = factor;
  }

  function setCrossFadeMs(durationMs: number): void {
    crossFadeMs = Math.max(1, durationMs);
  }

  /**
   * Whether the imagery has finished arriving.
   *
   * Play-through waits on this instead of a fixed clock. A dwell shorter than the tile fetch means the
   * fastest speed shows the least — the archive advances past frames the operator never actually sees,
   * which is the opposite of what a faster setting is for.
   */
  function isSettled(): boolean {
    for (const entry of tracked.values()) {
      if (entry.retiringSince !== null) {
        return false;
      }
      if (!entry.layer.ready) {
        return false;
      }
      if (Math.abs(entry.layer.alpha - resolveAlpha(entry)) > 0.02) {
        return false;
      }
    }
    return true;
  }

  function update(nowMs: number): void {
    for (const [layerId, entry] of tracked) {
      if (entry.retiringSince !== null) {
        const retiredFor = nowMs - entry.retiringSince;
        if (retiredFor >= crossFadeMs) {
          if (!scene.imageryLayers.isDestroyed()) {
            scene.imageryLayers.remove(entry.layer, true);
          }
          tracked.delete(layerId);
          continue;
        }

        entry.layer.alpha = entry.retiringFromAlpha * (1 - retiredFor / crossFadeMs);
        continue;
      }

      const target = resolveAlpha(entry);
      const elapsed = nowMs - entry.fadeStartedAt;

      if (elapsed >= crossFadeMs) {
        entry.layer.alpha = target;
        continue;
      }

      const progress = Math.max(0, elapsed / crossFadeMs);
      // Ease-out so the reveal decelerates into place rather than stopping dead.
      entry.layer.alpha = target * (1 - Math.pow(1 - progress, 3));
    }
  }

  function clear(): void {
    for (const entry of tracked.values()) {
      if (!scene.imageryLayers.isDestroyed()) {
        scene.imageryLayers.remove(entry.layer, true);
      }
    }
    tracked.clear();
    globalDim = 1;
  }

  return {
    sync,
    setVisibility,
    setOpacity,
    bindComparator,
    setGlobalDim,
    setCrossFadeMs,
    isSettled,
    update,
    clear,
    destroy: clear,
  };
}
