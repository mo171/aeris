// lib/constants/navigation.ts — the seven AERIS surfaces, as data. Drives the nav rail and the palette.
//
// what  : Declarative definition of every application surface: route, label, icon, description, availability.
// where : Read by components/sharedUI/functionalComponent/appShell/NavigationRail.tsx and by the
//         `nav.goto` command, which turns each entry into an agent-invocable command automatically.
// how   : `isAvailable: false` marks surfaces not yet built. The rail renders them dimmed and
//         non-interactive rather than linking to a 404 — a deliberate anti-glitch measure. Flipping the
//         flag is the only change needed when a page ships.

import {
  Cpu,
  FileSearch,
  GitCompareArrows,
  Globe,
  Layers2,
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
    description: "Analyse a scene with overlays, answers and execution traces",
    href: ROUTES.INVESTIGATION,
    icon: ScanSearch,
    isAvailable: true,
  },
  {
    id: "cross-modal",
    label: "Cross-Modal Lab",
    description: "Optical and SAR side by side with joint reasoning",
    href: ROUTES.CROSS_MODAL,
    icon: Layers2,
    isAvailable: false,
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
