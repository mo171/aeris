// lib/constants/routes.ts — every in-app URL, in one registry. No route string is ever written inline.
//
// what  : Canonical route paths for the seven AERIS application surfaces.
// where : Consumed by lib/constants/navigation.ts, the command bus `nav.goto` command, and any <Link>.
// how   : Only Mission Command exists today; the rest are declared now so navigation, command ids and
//         analytics never have to be renamed when those pages land.

export const ROUTES = {
  MISSION_COMMAND: "/",
  INVESTIGATION: "/investigation",
  CROSS_MODAL: "/cross-modal",
  TEMPORAL: "/temporal",
  EVIDENCE: "/evidence",
  MODEL_OBSERVATORY: "/models",
  MISSION_LIBRARY: "/missions",
} as const;

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES];
