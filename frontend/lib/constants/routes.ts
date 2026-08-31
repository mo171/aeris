// lib/constants/routes.ts — every in-app URL, in one registry. No route string is ever written inline.
//
// what  : Canonical route paths for the four AERIS application surfaces.
// where : Consumed by lib/constants/navigation.ts, the command bus `nav.goto` command, and any <Link>.
// how   : Only Mission Command exists today; the rest are declared now so navigation, command ids and
//         analytics never have to be renamed when those pages land.

export const ROUTES = {
  MISSION_COMMAND: "/",
  INVESTIGATION: "/investigation",
  EVIDENCE: "/evidence",
  MODEL_OBSERVATORY: "/models",
} as const;

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES];

/**
 * Resource paths, built rather than concatenated at call sites.
 *
 * Kept out of ROUTES itself so `RoutePath` stays a union of literal strings — the navigation rail and the
 * `nav.goto` command both depend on that, and widening it to include `string` would silently remove the
 * compile-time guarantee that every navigation target is a surface that exists.
 */
export const buildRoute = {
  investigationDetail: (investigationId: string) =>
    `${ROUTES.INVESTIGATION}/${investigationId}` as const,
  evidenceAudit: (search: string) =>
    `${ROUTES.EVIDENCE}?search=${encodeURIComponent(search)}` as const,
} as const;

/*
 * THERE IS NO CROSS-MODAL ROUTE, deliberately.
 *
 * It had one — /cross-modal/<investigationId> — and the route itself was the mistake. A cross-modal
 * verdict reads an EXISTING investigation: same evidence graph, same scenes, same area of interest, only a
 * different reading of them. Giving that reading its own URL made the operator leave the workspace, and
 * with it the assistant, the timeline and the draw tools — at exactly the moment a disagreement between
 * two sensors gave them something to ask, re-pair, or scope a question to.
 *
 * It is now a lens inside the Investigation Workspace, reachable from the Toolbox, the command palette and
 * the header. A rail names PLACES; cross-modal was never one.
 *
 * /temporal and /missions were removed for the same reason — see lib/constants/navigation.ts, which holds
 * the test and what each one failed on.
 */
