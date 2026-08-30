// lib/constants/navigation.ts — the six AERIS surfaces, as data. Drives the nav rail and the palette.
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
//         EVERY ROW HERE MUST BE A PLACE. Cross-modal was listed as a surface and was not one — it reads
//         an investigation that already exists, so it needed an id the rail could not supply, and the
//         index route papering over that was a symptom rather than a fix. It now lives in the
//         Investigation Workspace as a lens, and the test this file applies is: could an operator arrive
//         here with nothing open? If not, it is not a rail item.

import {
  Cpu,
  FileSearch,
  GitCompareArrows,
  Globe,
  Radar,
  ScanSearch,
  type LucideIcon,
} from "lucide-react";

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
    id: "temporal",
    label: "Temporal Explorer",
    description: "Bi-temporal change maps, timeline scrubber and before/after comparison",
    href: ROUTES.TEMPORAL,
    icon: GitCompareArrows,
    isAvailable: false,
  },
  {
    id: "evidence",
    label: "Evidence Explorer",
    description: "Trace every claim to its region, mask, model and confidence",
    href: ROUTES.EVIDENCE,
    icon: FileSearch,
    isAvailable: false,
  },
  {
    id: "models",
    label: "Model Observatory",
    description: "Registry of specialist models, versions and selection rationale",
    href: ROUTES.MODEL_OBSERVATORY,
    icon: Cpu,
    isAvailable: false,
  },
  {
    id: "missions",
    label: "Mission Library",
    description: "Saved investigations and continuous monitoring missions",
    href: ROUTES.MISSION_LIBRARY,
    icon: Radar,
    isAvailable: false,
  },
] as const;
