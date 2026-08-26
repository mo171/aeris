// lib/constants/theme.ts — the AERIS palette as CSS colour strings, for consumers that cannot read CSS vars.
//
// what  : The AERIS palette mirrored as hex strings.
// where : Used by the CesiumJS globe. Cesium builds colours with Color.fromCssColorString(), so hex
//         strings are exactly what it needs. DOM components must NOT import this — they use Tailwind
//         tokens, which read the same values from app/globals.css.
// how   : app/globals.css remains the source of truth. If a colour changes there it must change here in
//         the same commit, because nothing enforces the link automatically.

export const AERIS_COLOR_HEX = {
  void: "#06080E",
  black: "#0A0D14",
  obsidian: "#141824",
  slate: "#1B2030",
  stroke: "#2A3143",
  teal: "#00E5FF",
  blue: "#3B82F6",
  amber: "#F59E0B",
  red: "#EF4444",
  green: "#10B981",
  white: "#F3F4F6",
  gray: "#9CA3AF",
  grayDim: "#6B7280",
} as const;

export type AerisColorName = keyof typeof AERIS_COLOR_HEX;
