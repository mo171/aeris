// lib/constants/app.ts — product-level copy and identity strings. No user-visible string is hardcoded in JSX.
//
// what  : Application name, taglines, shell copy and boot-sequence lines.
// where : Used by app/layout.tsx metadata, the app shell header, and the assistant greeting.
// how   : Copy changes are a product decision, not a component change — centralising it means marketing
//         or wording revisions never require touching component files.

export const APP = {
  name: "AERIS",
  fullName: "Agentic Earth Reasoning & Intelligence System",
  shortDescription:
    "Interrogate satellite imagery in natural language. Every answer grounded in spatial evidence.",
  version: "0.1.0-phase1",
} as const;

export const SHELL_COPY = {
  commandBarPlaceholder: "Search coordinates, places, missions or type a command",
  commandBarHint: "Ctrl K",
  systemStatusNominal: "All systems nominal",
  systemStatusDegraded: "Degraded capability",
  systemStatusOffline: "Link lost",
} as const;

/** Terminal lines played once during the shell boot reveal. Purely presentational. */
export const BOOT_SEQUENCE_LINES = [
  "Establishing uplink",
  "Loading model registry",
  "Synchronising mission index",
  "AERIS online",
] as const;
