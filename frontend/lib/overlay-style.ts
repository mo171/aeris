// lib/overlay-style.ts — turns a measured value into the colour and the words that describe it.
//
// what  : Resolves one feature's fill, outline and human-readable reading from its layer's overlay
//         encoding — continuous ramp lookup, categorical class colour, or graduated bin.
// where : Called per feature per frame by the Cesium evidence vector layer, and once per layer by the
//         legend and the feature inspector.
// how   : ONE resolver, three branches, shared by the renderer and everything that describes it. That
//         sharing is the point: a legend that computes its swatch separately from the geometry can drift
//         from it, and a picture whose key is wrong is worse than a picture with no key.
//
//         Pure and framework-free, so the geoStage folder stays the only place that imports cesium and
//         this stays testable without a viewer. It takes a minimal shape rather than StageLayer so lib/
//         does not depend on the stage contract.
//
//         Diverging ramps are normalised piecewise around their neutral point rather than linearly across
//         the domain. On a −1..+1 change surface both are the same; on an observed range of −0.2..+0.8 a
//         linear map would put zero at 20% of the ramp and paint genuinely unchanged ground in the colour
//         of loss. Anchoring zero to the neutral stop is what keeps "no change" looking like no change.
//
//         Everything degrades rather than throws. An unknown overlay id, an absent value, a class the
//         palette does not carry — each falls back to something visible and honestly labelled, because a
//         feature that silently vanishes is a finding the operator never gets to question.

import {
  BIN_SCHEMES,
  COLOR_RAMPS,
  binIndexForValue,
  binRampPosition,
  findOverlay,
  formatOverlayValue,
  interpretIndexValue,
  mixHexColors,
  resolveOverlayClass,
  sampleRamp,
  type OverlayDefinition,
} from "./constants/overlays";
import { AERIS_COLOR_HEX } from "./constants/theme";

export interface OverlayStyleInput {
  overlayId: string | null;
  /** Observed range for this scene. Falls back to the catalogue's theoretical domain when null. */
  valueDomain: { minimum: number; maximum: number } | null;
  value: number | null;
  classId: string | null;
}

export interface OverlayStyle {
  fill: string;
  outline: string;
  /** What this feature reads as — "0.62 · dense healthy vegetation", "Industrial", "Moderate". */
  readout: string;
  /** The class or band name alone, for grouping and for the inspector's chip. */
  categoryLabel: string | null;
}

/**
 * Style for one feature, or null when the layer has no catalogued overlay.
 *
 * Null is a real answer, not a failure: scene imagery and reference tiles are not products and have no
 * encoding. The caller keeps its existing palette in that case.
 */
export function resolveOverlayStyle(input: OverlayStyleInput): OverlayStyle | null {
  const overlay = findOverlay(input.overlayId);
  if (!overlay) {
    return null;
  }

  switch (overlay.encoding.kind) {
    case "categorical": {
      const overlayClass = resolveOverlayClass(overlay.encoding.paletteId, input.classId);
      return {
        fill: overlayClass.color,
        outline: lighten(overlayClass.color),
        readout: overlayClass.label,
        categoryLabel: overlayClass.label,
      };
    }

    case "graduated": {
      const scheme = BIN_SCHEMES[overlay.encoding.schemeId];
      if (input.value === null) {
        return neutralStyle("Not measured");
      }

      const index = binIndexForValue(scheme.id, input.value);
      const fill = sampleRamp(scheme.rampId, binRampPosition(scheme.id, index));
      const bin = scheme.bins[index];
      const formatted = formatOverlayValue(input.value, overlay.encoding.unitId);

      return {
        fill,
        outline: lighten(fill),
        readout: `${formatted} · ${bin.label.toLowerCase()}`,
        categoryLabel: bin.label,
      };
    }

    case "continuous": {
      if (input.value === null) {
        return neutralStyle("Not measured");
      }

      const domain = input.valueDomain ?? overlay.encoding.domain;
      const position = normalisePosition(input.value, domain, overlay.encoding.rampId);
      const fill = sampleRamp(overlay.encoding.rampId, position);

      return {
        fill,
        outline: lighten(fill),
        readout: describeContinuous(overlay, input.value),
        categoryLabel: bandLabelForValue(overlay, input.value),
      };
    }
  }
}

/**
 * Where a value sits on its ramp, 0–1.
 *
 * Sequential ramps map linearly across the domain. Diverging ramps map each side independently so zero
 * lands exactly on the neutral stop — see the file header for why that matters.
 */
export function normalisePosition(
  value: number,
  domain: { minimum: number; maximum: number },
  rampId: keyof typeof COLOR_RAMPS,
): number {
  const ramp = COLOR_RAMPS[rampId];
  const span = domain.maximum - domain.minimum;

  if (!ramp.isDiverging || ramp.neutralPosition === null) {
    return span === 0 ? 0 : clamp01((value - domain.minimum) / span);
  }

  const neutral = ramp.neutralPosition;
  if (value >= 0) {
    return domain.maximum <= 0 ? neutral : clamp01(neutral + (value / domain.maximum) * (1 - neutral));
  }
  return domain.minimum >= 0 ? neutral : clamp01(neutral * (1 - value / domain.minimum));
}

/** The value with its unit, plus the interpretation band it falls in where the product has one. */
function describeContinuous(overlay: OverlayDefinition, value: number): string {
  const unitId = overlay.encoding.kind === "continuous" ? overlay.encoding.unitId : "index";
  const formatted = formatOverlayValue(value, unitId);
  const band = bandLabelForValue(overlay, value);
  return band ? `${formatted} · ${band.toLowerCase()}` : formatted;
}

/** Interpretation band name for index products — "dense healthy vegetation" — or null for the rest. */
function bandLabelForValue(overlay: OverlayDefinition, value: number): string | null {
  if (!overlay.spectralIndexId) {
    return null;
  }
  return interpretIndexValue(overlay.spectralIndexId, value)?.label ?? null;
}

function neutralStyle(readout: string): OverlayStyle {
  return {
    fill: AERIS_COLOR_HEX.grayDim,
    outline: AERIS_COLOR_HEX.gray,
    readout,
    categoryLabel: null,
  };
}

/** Outlines are derived from fills rather than authored, so a new class can never arrive without one. */
function lighten(hex: string): string {
  return mixHexColors(hex, AERIS_COLOR_HEX.white, 0.35);
}

function clamp01(value: number): number {
  return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
}
