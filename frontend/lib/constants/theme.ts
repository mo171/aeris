// lib/constants/theme.ts — the AERIS palette as numeric hex, for consumers that cannot read CSS variables.
//
// what  : Numeric colour values plus a WebGL-friendly mirror of the palette defined in app/globals.css.
// where : Used by the three.js globe (materials and shader uniforms take numbers, not CSS vars) and by
//         canvas rasterisation. DOM components must NOT import this — they use Tailwind tokens instead.
// how   : AERIS_COLOR_HEX holds strings for canvas 2D APIs; AERIS_COLOR_INT holds the same values as
//         numbers for three.js. globals.css remains the source of truth; if a colour changes there it
//         must be changed here in the same commit.

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

export const AERIS_COLOR_INT = {
  void: 0x06080e,
  black: 0x0a0d14,
  obsidian: 0x141824,
  slate: 0x1b2030,
  stroke: 0x2a3143,
  teal: 0x00e5ff,
  blue: 0x3b82f6,
  amber: 0xf59e0b,
  red: 0xef4444,
  green: 0x10b981,
  white: 0xf3f4f6,
  gray: 0x9ca3af,
  grayDim: 0x6b7280,
} as const;

export type AerisColorName = keyof typeof AERIS_COLOR_HEX;
