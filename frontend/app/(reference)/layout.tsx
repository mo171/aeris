// app/(reference)/layout.tsx — the route group for surfaces that do not render the Earth.
//
// what  : Wraps the Model Observatory and the Evidence Audit in the application shell, with no Cesium stage
//         underneath them.
// where : Applies to "/models" and "/evidence". Route groups do not appear in the URL, so no path changes.
// how   : The counterpart to (geospatial), and the reason that group's comment says to scope it
//         deliberately: a WebGL context costs memory and a boot, and neither of these surfaces draws a map.
//         They read the model catalogue and the claim corpus, both of which are tables.
//
//         A surface belongs here when it answers a question ABOUT the system rather than about a place. If
//         one later needs to show geometry, it should deep-link into the workspace that already has a
//         viewer rather than mounting a second one.

import type { ReactNode } from "react";

import { AppShell } from "@/components/sharedUI/functionalComponent/appShell/AppShell";

export default function ReferenceLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
