// lib/constants/overlays/color-ramps.ts — continuous colour ramps, as value→colour stop lists.
//
// what  : Every continuous ramp the system can draw, each one an ordered list of stops on a normalised
//         0–1 axis, plus whether it diverges and where its neutral point sits.
// where : Read by the overlay catalogue (which binds a ramp to a product), by the evidence vector layer
//         when it colours a feature by its measured value, and by the legend when it draws the bar.
// how   : A ramp here is DATA, not a CSS string. `RASTER_GRADING` in layers.ts adjusts an already-coloured
//         RGB tile — brightness, contrast, saturation — which cannot express "NDVI 0.62 is this green".
//         Colouring by a measured value needs the mapping itself, so this file holds the mapping and
//         `sampleRamp` is the single place it is evaluated. The legend bar and the geometry both read it,
//         which is what makes it impossible for a legend to describe a picture nobody is looking at.
//
//         Every sequential ramp runs monotonically in LIGHTNESS, so magnitude survives greyscale printing
//         and colour-blind vision. Rainbow ramps are excluded on purpose: they read as amateur GIS and
//         they invent boundaries that are not in the data.
//
//         Diverging ramps are a different instrument and are marked as such. Water gained and water lost
//         are opposite findings; a flood and a drought must never share a colour. `neutralPosition` is
//         where the ramp passes through "no change", and it is not always the midpoint — a domain of
//         -0.2..+0.8 has its zero at 0.2 of the axis, and putting the neutral colour anywhere else would
//         claim change where there is none.
//
//         Red is absent from every ramp, and that is deliberate rather than an oversight. layers.ts
//         reserves red for alerts so it never devalues; the density ramp therefore climbs to a hot
//         amber-white instead, which reads almost identically at a glance and keeps red meaning one thing.

import { AERIS_COLOR_HEX } from "../theme";

export const OVERLAY_RAMP_IDS = [
  "vegetation-sequential",
  "water-sequential",
  "built-up-sequential",
  "burn-severity",
  "density-heat",
  "backscatter-grayscale",
  "confidence-magma",
  "change-diverging",
  "water-change-diverging",
  "elevation-terrain",
] as const;

export type OverlayRampId = (typeof OVERLAY_RAMP_IDS)[number];

export interface RampStop {
  /** Position on the ramp axis, 0 to 1. Stops must be ordered and must span the full axis. */
  position: number;
  color: string;
}

export interface ColorRamp {
  id: OverlayRampId;
  label: string;
  stops: readonly RampStop[];
  /** True when the two ends mean opposite things rather than more and less of one thing. */
  isDiverging: boolean;
  /**
   * Where "nothing happened" sits on the axis, for diverging ramps only. Null for sequential ones,
   * which have no such point — the bottom of a vegetation ramp is not neutral, it is bare ground.
   */
  neutralPosition: number | null;
}

const { teal, blue, amber, green, slate, stroke, gray, grayDim, white } = AERIS_COLOR_HEX;

export const COLOR_RAMPS: Readonly<Record<OverlayRampId, ColorRamp>> = {
  "vegetation-sequential": {
    id: "vegetation-sequential",
    label: "Vegetation density",
    isDiverging: false,
    neutralPosition: null,
    stops: [
      { position: 0, color: slate },
      { position: 0.35, color: "#3E4A38" },
      { position: 0.7, color: "#4F8B52" },
      { position: 1, color: green },
    ],
  },
  "water-sequential": {
    id: "water-sequential",
    label: "Water presence",
    isDiverging: false,
    neutralPosition: null,
    stops: [
      { position: 0, color: slate },
      { position: 0.45, color: "#1E3A5F" },
      { position: 1, color: blue },
    ],
  },
  "built-up-sequential": {
    id: "built-up-sequential",
    label: "Built-up density",
    isDiverging: false,
    neutralPosition: null,
    stops: [
      { position: 0, color: slate },
      { position: 0.5, color: "#7A6134" },
      { position: 1, color: amber },
    ],
  },
  "burn-severity": {
    id: "burn-severity",
    label: "Burn severity",
    isDiverging: false,
    neutralPosition: null,
    stops: [
      { position: 0, color: slate },
      { position: 0.4, color: "#6B4A1F" },
      { position: 0.75, color: amber },
      { position: 1, color: "#FFE9B0" },
    ],
  },
  "density-heat": {
    id: "density-heat",
    label: "Concentration",
    isDiverging: false,
    neutralPosition: null,
    stops: [
      { position: 0, color: "#1A2E4A" },
      { position: 0.35, color: blue },
      { position: 0.68, color: amber },
      { position: 1, color: "#FFF0C2" },
    ],
  },
  "backscatter-grayscale": {
    id: "backscatter-grayscale",
    label: "Radar backscatter",
    isDiverging: false,
    neutralPosition: null,
    stops: [
      { position: 0, color: "#0F131C" },
      { position: 0.5, color: grayDim },
      { position: 1, color: white },
    ],
  },
  "confidence-magma": {
    id: "confidence-magma",
    label: "Model confidence",
    isDiverging: false,
    neutralPosition: null,
    stops: [
      { position: 0, color: "#231B3A" },
      { position: 0.5, color: "#3D5BA9" },
      { position: 1, color: teal },
    ],
  },
  "change-diverging": {
    id: "change-diverging",
    label: "Change",
    isDiverging: true,
    neutralPosition: 0.5,
    stops: [
      { position: 0, color: amber },
      { position: 0.42, color: "#5C4A2E" },
      { position: 0.5, color: stroke },
      { position: 0.58, color: "#1F5A66" },
      { position: 1, color: teal },
    ],
  },
  "water-change-diverging": {
    id: "water-change-diverging",
    label: "Water change",
    isDiverging: true,
    neutralPosition: 0.5,
    stops: [
      { position: 0, color: amber },
      { position: 0.44, color: "#5C4A2E" },
      { position: 0.5, color: stroke },
      { position: 0.56, color: "#204A78" },
      { position: 1, color: blue },
    ],
  },
  "elevation-terrain": {
    id: "elevation-terrain",
    label: "Height",
    isDiverging: false,
    neutralPosition: null,
    stops: [
      { position: 0, color: stroke },
      { position: 0.5, color: gray },
      { position: 1, color: white },
    ],
  },
};

/**
 * Colour at a normalised position on a ramp, interpolated in sRGB between the surrounding stops.
 *
 * sRGB rather than a perceptual space on purpose: the stops are already hand-placed to run evenly in
 * lightness, so a perceptual interpolation would fight choices already made, and this runs per feature
 * per frame in a Cesium callback where a colour-space conversion is not free.
 *
 * Out-of-range positions clamp rather than throw. A value outside its declared domain is a data problem
 * worth surfacing in the readout, never a reason to stop drawing the scene.
 */
export function sampleRamp(rampId: OverlayRampId, position: number): string {
  const { stops } = COLOR_RAMPS[rampId];
  const clamped = Math.min(1, Math.max(0, Number.isFinite(position) ? position : 0));

  let lower = stops[0];
  let upper = stops[stops.length - 1];

  for (let index = 0; index < stops.length - 1; index += 1) {
    if (clamped >= stops[index].position && clamped <= stops[index + 1].position) {
      lower = stops[index];
      upper = stops[index + 1];
      break;
    }
  }

  const span = upper.position - lower.position;
  const localPosition = span === 0 ? 0 : (clamped - lower.position) / span;
  return mixHexColors(lower.color, upper.color, localPosition);
}

/** A CSS `linear-gradient` for the legend bar, built from the same stops the geometry samples. */
export function rampToCssGradient(rampId: OverlayRampId, angleDegrees = 90): string {
  const stops = COLOR_RAMPS[rampId].stops
    .map((stop) => `${stop.color} ${(stop.position * 100).toFixed(1)}%`)
    .join(", ");
  return `linear-gradient(${angleDegrees}deg, ${stops})`;
}

/** Blends two hex colours. Exported because outlines are derived from fills rather than authored twice. */
export function mixHexColors(fromHex: string, toHex: string, weight: number): string {
  const from = parseHexColor(fromHex);
  const to = parseHexColor(toHex);
  const channel = (start: number, end: number) => Math.round(start + (end - start) * weight);

  return `#${[
    channel(from.red, to.red),
    channel(from.green, to.green),
    channel(from.blue, to.blue),
  ]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("")}`;
}

function parseHexColor(hex: string): { red: number; green: number; blue: number } {
  const normalised = hex.replace("#", "");
  return {
    red: Number.parseInt(normalised.slice(0, 2), 16),
    green: Number.parseInt(normalised.slice(2, 4), 16),
    blue: Number.parseInt(normalised.slice(4, 6), 16),
  };
}
