// lib/constants/layers.ts — how every analysis overlay is coloured, ordered and sized on the scene.
//
// what  : Colour ramps for raster and vector evidence, draw-order bands, extrusion scaling and the
//         opacity defaults each layer kind starts at.
// where : Read by the geoStage layer renderers and by the investigation feature's layer stack UI.
// how   : Layers arrive from the backend as descriptors carrying a ramp id, never a colour. That keeps
//         palette decisions in the frontend where the design system lives, and means re-theming the
//         application never requires a backend change.
//
//         Ramps are perceptually ordered on purpose. Rainbow ramps are colour-blind hostile and read as
//         amateur GIS; every continuous ramp here runs monotonically in lightness so magnitude is legible
//         even in greyscale. Diverging ramps use teal for gain and amber for loss, matching the rest of
//         the interface — red stays reserved for alerts so it never devalues.

import { AERIS_COLOR_HEX } from "./theme";

export const COLOR_RAMP_IDS = [
  "true-color",
  "sar-grayscale",
  "change-diverging",
  "index-vegetation",
  "confidence-magma",
  "detection-teal",
  "mask-amber",
  "artefact-neutral",
] as const;

export type ColorRampId = (typeof COLOR_RAMP_IDS)[number];

/**
 * Raster display grading, applied to an ImageryLayer.
 * Scene imagery defaults to no grading at all: it is the subject of the page, and the operator must see
 * what the sensor saw. Only derived products are graded.
 */
/**
 * How long a raster takes to cross-fade when it is replaced, in milliseconds.
 *
 * Two speeds because the same transition serves two very different gestures. A deliberate layer change
 * happens once and can afford to be smooth; scrubbing a timeline replaces the imagery on every step, and
 * a fade tuned for the first reads as lag when it happens ten times inside one drag.
 */
export const RASTER_CROSS_FADE_MS = {
  settled: 420,
  scrubbing: 160,
} as const;

export const RASTER_GRADING: Readonly<
  Record<ColorRampId, { brightness: number; contrast: number; saturation: number; gamma: number }>
> = {
  "true-color": { brightness: 1, contrast: 1.04, saturation: 1.06, gamma: 1 },
  "sar-grayscale": { brightness: 1.12, contrast: 1.35, saturation: 0, gamma: 0.9 },
  "change-diverging": { brightness: 1.1, contrast: 1.2, saturation: 1.4, gamma: 1 },
  "index-vegetation": { brightness: 1.05, contrast: 1.15, saturation: 1.3, gamma: 1 },
  "confidence-magma": { brightness: 1, contrast: 1.2, saturation: 1.2, gamma: 1 },
  "detection-teal": { brightness: 1, contrast: 1, saturation: 1, gamma: 1 },
  "mask-amber": { brightness: 1, contrast: 1, saturation: 1, gamma: 1 },
  "artefact-neutral": { brightness: 0.95, contrast: 1.1, saturation: 0.4, gamma: 1 },
};

/** Vector fill and outline colours, as CSS strings resolved to Cesium colours by the renderer. */
export const VECTOR_PALETTE: Readonly<
  Record<ColorRampId, { fill: string; outline: string; highlight: string }>
> = {
  "true-color": { fill: AERIS_COLOR_HEX.teal, outline: AERIS_COLOR_HEX.teal, highlight: AERIS_COLOR_HEX.white },
  "sar-grayscale": { fill: AERIS_COLOR_HEX.grayDim, outline: AERIS_COLOR_HEX.white, highlight: AERIS_COLOR_HEX.white },
  "change-diverging": { fill: AERIS_COLOR_HEX.amber, outline: AERIS_COLOR_HEX.amber, highlight: AERIS_COLOR_HEX.white },
  "index-vegetation": { fill: AERIS_COLOR_HEX.teal, outline: AERIS_COLOR_HEX.teal, highlight: AERIS_COLOR_HEX.white },
  "confidence-magma": { fill: AERIS_COLOR_HEX.blue, outline: AERIS_COLOR_HEX.blue, highlight: AERIS_COLOR_HEX.white },
  "detection-teal": { fill: AERIS_COLOR_HEX.teal, outline: AERIS_COLOR_HEX.teal, highlight: AERIS_COLOR_HEX.white },
  "mask-amber": { fill: AERIS_COLOR_HEX.amber, outline: AERIS_COLOR_HEX.amber, highlight: AERIS_COLOR_HEX.white },
  "artefact-neutral": { fill: AERIS_COLOR_HEX.blue, outline: AERIS_COLOR_HEX.blue, highlight: AERIS_COLOR_HEX.white },
};

export const LAYER_RENDERING = {
  /** Starting opacity per layer kind. The operator can override any of them from the layer stack. */
  defaultOpacity: {
    "raster-tiles": 1,
    "raster-mask": 0.72,
    "polygon-vector": 0.55,
    "point-vector": 0.9,
    "bbox-vector": 0.9,
  },

  /** Fill alpha relative to the layer's opacity, so an outline stays readable over bright imagery. */
  polygonFillAlphaRatio: 0.55,
  polygonOutlineWidthPixels: 2,
  bboxOutlineWidthPixels: 2,

  /**
   * Metres of extrusion at magnitude 1.0. A change polygon is extruded by its magnitude so a skyline
   * forms over the areas that changed most — the most direct way to make a change felt rather than read.
   */
  extrusionMetersAtFullMagnitude: 2_400,
  extrusionMinimumMeters: 120,
  /** How long the extrusion grows from flat when volumetric mode is switched on. */
  extrusionGrowthMs: 900,

  /** Evidence polygons are lifted very slightly so terrain z-fighting never speckles their edges. */
  vectorHeightOffsetMeters: 12,

  /** Staggered arrival, largest magnitude first, so the eye is led to the most significant change. */
  bloomStaggerMs: 45,
  bloomMaximumTotalMs: 1_200,

  /** Basemap brightness multiplier while an evidence spotlight is active. */
  spotlightDimBrightness: 0.32,
  /** Scene-raster alpha multiplier while a spotlight is active. Softer than the basemap: the operator
   *  must still recognise the place their evidence sits in. */
  spotlightSceneDimRatio: 0.55,
  spotlightRestoreMs: 260,
  /** Alpha applied to evidence that is NOT part of the spotlit claim. */
  spotlightMutedAlphaRatio: 0.12,
} as const;

/** Zoom ceiling applied when a descriptor does not declare one. Prevents unbounded tile requests. */
export const LAYER_DEFAULT_MAX_ZOOM = 18;
