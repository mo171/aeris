// lib/constants/overlays/bin-schemes.ts — graduated breaks: continuous values cut into ordered bands.
//
// what  : The break schemes a graduated overlay uses — change intensity, building height, cloud
//         thickness, detection density — each break carrying its upper bound, its label and what that
//         band means.
// where : Bound to a product by the overlay catalogue; resolved per feature by the evidence vector layer
//         and drawn as a stepped bar with break labels by the legend.
// how   : This is the third encoding, and it exists because a continuous ramp answers "how much" while a
//         bin answers "which band" — and an operator acting on a finding almost always needs the second.
//         "18.4% change" is a measurement; "moderate change" is a decision. Rendering only the ramp makes
//         every reader draw their own thresholds, and they will not draw the same ones.
//
//         Breaks are AUTHORED, not computed. Quantile or Jenks breaks derived from the current scene look
//         scientific and are actively harmful here: the same physical change would land in a different
//         band depending on what else happened to be in frame, so two investigations of the same place
//         could not be compared. Fixed breaks mean a band means the same thing every time.
//
//         Where a threshold comes from published practice it is cited in the band's `meaning`, because a
//         number an analyst cannot trace is a number they are right to distrust.

import type { OverlayRampId } from "./color-ramps";

export const BIN_SCHEME_IDS = [
  "change-intensity",
  "building-height",
  "cloud-thickness",
  "detection-density",
  "burn-severity-bands",
] as const;

export type BinSchemeId = (typeof BIN_SCHEME_IDS)[number];

export interface Bin {
  /** Upper bound of the band, inclusive. The last bin uses Infinity, which is the open top. */
  upperBound: number;
  label: string;
  /** What falling in this band implies. Shown in the legend and quoted by the answer panel. */
  meaning: string;
}

export interface BinScheme {
  id: BinSchemeId;
  label: string;
  /** Colour comes from sampling this ramp at each bin's midpoint, so bins and ramps never diverge. */
  rampId: OverlayRampId;
  bins: readonly Bin[];
}

export const BIN_SCHEMES: Readonly<Record<BinSchemeId, BinScheme>> = {
  "change-intensity": {
    id: "change-intensity",
    label: "Change intensity",
    rampId: "built-up-sequential",
    bins: [
      { upperBound: 0.05, label: "Negligible", meaning: "Within the noise a co-registered pair produces on its own." },
      { upperBound: 0.15, label: "Slight", meaning: "Detectable but small — often seasonal or a single structure." },
      { upperBound: 0.3, label: "Moderate", meaning: "A real alteration to the surface worth naming in an answer." },
      { upperBound: 0.5, label: "Substantial", meaning: "Most of the region changed character between the two dates." },
      { upperBound: Number.POSITIVE_INFINITY, label: "Severe", meaning: "Near-total transformation of the ground." },
    ],
  },

  "building-height": {
    id: "building-height",
    label: "Building height",
    rampId: "elevation-terrain",
    bins: [
      { upperBound: 8, label: "Low-rise", meaning: "Up to roughly two storeys — housing, sheds, small retail." },
      { upperBound: 20, label: "Mid-rise", meaning: "Three to six storeys. The dominant band in most cities." },
      { upperBound: 50, label: "High-rise", meaning: "Seven to about fifteen storeys." },
      { upperBound: 150, label: "Tower", meaning: "Above fifteen storeys — casts shadow that affects optical analysis." },
      { upperBound: Number.POSITIVE_INFINITY, label: "Supertall", meaning: "Above 150 m. Rare, and a landmark for orientation." },
    ],
  },

  "cloud-thickness": {
    id: "cloud-thickness",
    label: "Obscuration",
    rampId: "backscatter-grayscale",
    bins: [
      { upperBound: 0.2, label: "Clear", meaning: "Surface fully readable." },
      { upperBound: 0.5, label: "Thin cirrus", meaning: "Reflectance is biased but the surface is still recoverable." },
      { upperBound: 0.8, label: "Cloud", meaning: "Surface not observed. Any claim here rests on the other date alone." },
      { upperBound: Number.POSITIVE_INFINITY, label: "Cloud & shadow", meaning: "Obscured, and the shadow corrupts neighbouring pixels too." },
    ],
  },

  "detection-density": {
    id: "detection-density",
    label: "Detection density",
    rampId: "density-heat",
    bins: [
      { upperBound: 0.15, label: "Sparse", meaning: "Isolated detections; likely individual events." },
      { upperBound: 0.4, label: "Scattered", meaning: "Loosely grouped — a corridor or a fringe." },
      { upperBound: 0.7, label: "Clustered", meaning: "A coherent concentration worth treating as one site." },
      { upperBound: Number.POSITIVE_INFINITY, label: "Dense core", meaning: "The centre of the activity in this area of interest." },
    ],
  },

  "burn-severity-bands": {
    id: "burn-severity-bands",
    label: "Burn severity",
    rampId: "burn-severity",
    bins: [
      { upperBound: 0.1, label: "Unburned", meaning: "ΔNBR below the unburned threshold in common practice." },
      { upperBound: 0.27, label: "Low severity", meaning: "Surface fuel consumed; canopy largely intact." },
      { upperBound: 0.66, label: "Moderate severity", meaning: "Partial canopy loss with surviving structure." },
      { upperBound: Number.POSITIVE_INFINITY, label: "High severity", meaning: "Canopy consumed. Recovery is measured in years." },
    ],
  },
};

/** Index of the bin a value falls in. Values above every bound land in the open top bin. */
export function binIndexForValue(schemeId: BinSchemeId, value: number): number {
  const { bins } = BIN_SCHEMES[schemeId];
  const index = bins.findIndex((bin) => value <= bin.upperBound);
  return index === -1 ? bins.length - 1 : index;
}

/**
 * Where a bin sits on its ramp, 0–1, taken at the band's midpoint.
 *
 * The midpoint rather than the edge so no band is drawn in a colour that belongs to its neighbour, and
 * so the first and last bands are not stuck at the extreme ends of the ramp where they cannot be told
 * apart from an out-of-range value.
 */
export function binRampPosition(schemeId: BinSchemeId, binIndex: number): number {
  const { bins } = BIN_SCHEMES[schemeId];
  return bins.length <= 1 ? 0.5 : (binIndex + 0.5) / bins.length;
}
