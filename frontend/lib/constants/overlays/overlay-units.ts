// lib/constants/overlays/overlay-units.ts — what a measured value is measured IN, and how to print it.
//
// what  : The unit vocabulary an overlay's values can carry — index, percentage, metres, hectares,
//         decibels, counts and per-square-kilometre densities — with the symbol and the precision each
//         one is read at.
// where : Referenced by every continuous and graduated entry in the overlay catalogue; used by the
//         legend's ramp scale, the feature inspector's value readout, and the answer panel.
// how   : A number without its unit is not a measurement. "0.62" is meaningless; "NDVI 0.62" is a
//         reading. Keeping units here rather than formatting inline means one product cannot print
//         "−12dB" while another prints "-12 db" for the same quantity.
//
//         PRECISION IS PART OF THE UNIT, and getting it wrong is a claim. An index quoted to four decimal
//         places asserts a precision the sensor does not have; a height quoted to the metre when the
//         source is a crowd-sourced estimate does the same. The digits here are the digits the underlying
//         measurement can actually support.
//
//         Formatting is deliberately local rather than reaching for lib/formatters.ts. Those helpers
//         serve UI copy — relative times, byte sizes, coordinates — and are free to change wording;
//         a value on a legend axis has to stay stable and tabular, so the two must not be coupled.

export const OVERLAY_UNIT_IDS = [
  "index",
  "percentage",
  "meters",
  "hectares",
  "decibels",
  "count",
  "per-square-kilometer",
  "ratio",
] as const;

export type OverlayUnitId = (typeof OVERLAY_UNIT_IDS)[number];

export interface OverlayUnit {
  id: OverlayUnitId;
  /** Printed immediately after the number. Empty where the quantity is dimensionless. */
  symbol: string;
  /** Spoken form, for the legend heading and for the agent's description of a layer. */
  label: string;
  fractionDigits: number;
  /** True when the stored value is a 0–1 ratio that must be multiplied to be printed. */
  isRatioScaled: boolean;
}

export const OVERLAY_UNITS: Readonly<Record<OverlayUnitId, OverlayUnit>> = {
  index: { id: "index", symbol: "", label: "index value", fractionDigits: 2, isRatioScaled: false },
  percentage: { id: "percentage", symbol: "%", label: "percent", fractionDigits: 1, isRatioScaled: true },
  meters: { id: "meters", symbol: " m", label: "metres", fractionDigits: 0, isRatioScaled: false },
  hectares: { id: "hectares", symbol: " ha", label: "hectares", fractionDigits: 1, isRatioScaled: false },
  decibels: { id: "decibels", symbol: " dB", label: "decibels", fractionDigits: 1, isRatioScaled: false },
  count: { id: "count", symbol: "", label: "count", fractionDigits: 0, isRatioScaled: false },
  "per-square-kilometer": {
    id: "per-square-kilometer",
    symbol: " /km²",
    label: "per square kilometre",
    fractionDigits: 1,
    isRatioScaled: false,
  },
  ratio: { id: "ratio", symbol: "", label: "ratio", fractionDigits: 2, isRatioScaled: false },
};

/** A value with its unit, at the precision that unit supports. Null renders as an explicit dash. */
export function formatOverlayValue(value: number | null, unitId: OverlayUnitId): string {
  if (value === null || !Number.isFinite(value)) {
    return "—";
  }

  const unit = OVERLAY_UNITS[unitId];
  const scaled = unit.isRatioScaled ? value * 100 : value;
  return `${scaled.toFixed(unit.fractionDigits)}${unit.symbol}`;
}
