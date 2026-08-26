// lib/constants/motion.ts — the motion scale, mirrored from globals.css for JS-driven animation.
//
// what  : Durations (seconds), easing curves and the shell boot choreography used by framer-motion.
// where : Imported by app shell components, panel transitions and the globe reveal.
// how   : CSS transitions read --motion-* / --ease-* from globals.css; framer-motion cannot read CSS
//         variables for timing, so the same scale is expressed here in seconds. If you change one, change
//         both — these two files are the complete definition of AERIS motion.

/** Seconds. Mirrors --motion-* in globals.css. */
export const MOTION_DURATION = {
  instant: 0.09,
  fast: 0.14,
  base: 0.24,
  slow: 0.42,
  cinematic: 0.9,
} as const;

/** Cubic-bezier control points. Mirrors --ease-* in globals.css. */
export const MOTION_EASING = {
  expo: [0.16, 1, 0.3, 1],
  quart: [0.76, 0, 0.24, 1],
  standard: [0.4, 0, 0.2, 1],
} as const;

/**
 * Boot reveal choreography — the staged entrance the operator sees once per session.
 * Deliberately sequential rather than a scatter of independent delays: the interface assembles
 * top-down (header, rail, panels, globe) so it reads as a system coming online.
 */
export const BOOT_SEQUENCE_DELAY = {
  header: 0,
  navigationRail: 0.08,
  dataPanel: 0.16,
  assistantPanel: 0.22,
  globe: 0.3,
} as const;

/** Shared framer-motion variants for panel and list entrances. */
export const PANEL_REVEAL_VARIANTS = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 },
} as const;
