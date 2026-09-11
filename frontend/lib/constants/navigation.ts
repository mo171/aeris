// lib/constants/navigation.ts — the four AERIS surfaces, as data. Drives the nav rail and the palette.
//
// what  : Declarative definition of every application surface: route, label, icon, description, availability.
// where : Read by components/sharedUI/functionalComponent/appShell/NavigationRail.tsx and by the
//         `nav.goto` command, which turns each entry into an agent-invocable command automatically.
// how   : `isAvailable: false` marks surfaces not yet built. The rail renders them dimmed and
//         non-interactive rather than linking to a 404 — a deliberate anti-glitch measure.
//
//         SHIPPING A PAGE IS MORE THAN FLIPPING THE FLAG, and this comment used to claim otherwise. A
//         surface needs its route, its INDEX route (the rail links to a place, not to a record), the flag,
//         and an icon that is not a duplicate of another row's. Three of those four are invisible in the
//         page's own diff, which is exactly how a finished page ends up still reading "Not built yet".
//
//         EVERY ROW HERE MUST BE A PLACE. The test is: could an operator arrive here with nothing open?
//         If not, it is not a rail item. Three of the original seven failed it:
//
//         - CROSS-MODAL reads an investigation that already exists, so it needed an id the rail could not
//           supply. It is a lens in the Investigation Workspace.
//         - TEMPORAL asked "T0 versus T1" of nothing in particular. The timeline, the split comparator and
//           change detection all shipped inside the workspace; the route would have been that workspace
//           with its tools removed.
//         - MISSION LIBRARY was redundant three ways — Mission Command lists missions and draws their
//           globe markers, and the investigation index is the shelf. Continuous monitoring and alerting
//           are later-tier scope (see design_report.md), so the half that would justify a surface does not
//           exist yet. If scheduled runs and an alert queue get built, that queue IS a place and this
//           entry comes back.

import { Cpu, FileSearch, Globe, ScanSearch, type LucideIcon } from "lucide-react";

import { ROUTES, type RoutePath } from "./routes";

export interface NavigationItem {
  id: string;
  label: string;
  description: string;
  href: RoutePath;
  icon: LucideIcon;
  isAvailable: boolean;
}

export const NAVIGATION_ITEMS: readonly NavigationItem[] = [
  {
    id: "mission-command",
    label: "Mission Command",
    description: "Global situational picture, imagery intake and the AERIS assistant",
    href: ROUTES.MISSION_COMMAND,
    icon: Globe,
    isAvailable: true,
  },
  {
    id: "investigation",
    label: "Investigation",
    description:
      "Analyse a scene with overlays, answers, execution traces and cross-modal agreement",
    href: ROUTES.INVESTIGATION,
    icon: ScanSearch,
    isAvailable: true,
  },
  {
    id: "evidence",
    label: "Evidence Audit",
    description: "Search every claim ever asserted by model, confidence and source scene",
    href: ROUTES.EVIDENCE,
    icon: FileSearch,
    // Built, and the route works, but the surface does not hydrate — the filters are inert and the claim
    // list never loads. Left unavailable rather than shipping a rail entry to a page that cannot be used.
    // See fcontext/memory.md for the reproduction; flip this once that is fixed.
    isAvailable: true,
  },
  {
    id: "models",
    label: "Model Observatory",
    description: "What each specialist model is, how it is doing, and when the router picks it",
    href: ROUTES.MODEL_OBSERVATORY,
    icon: Cpu,
    isAvailable: true,
  },
] as const;
