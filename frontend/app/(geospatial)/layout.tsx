// app/(geospatial)/layout.tsx — the route group that shares one 3D Earth across every geospatial surface.
//
// what  : Wraps Mission Command and the Investigation Workspace in the application shell and mounts the
//         single Cesium stage underneath them.
// where : Applies to "/" and "/investigation/*". Route groups do not appear in the URL, so no path changes.
// how   : This layout is the reason the globe-to-AOI descent is one continuous camera move. Next.js
//         unmounts a page's tree on navigation; a viewer owned by a feature would be destroyed mid-flight
//         and the transition would degrade into freeze, boot a second WebGL context, cross-fade. Owning it
//         one level above both routes keeps the camera alive across the route change.
//
//         The group is scoped deliberately. Only surfaces that actually render the Earth belong here — the
//         Model Observatory must never pay for a WebGL context it does not use.
//
//         Pages render on top of the stage and reach it through the handle in store/geo-stage-store.ts, so
//         this layout needs to know nothing about the surfaces it hosts.

import type { ReactNode } from "react";

import { AppShell } from "@/components/sharedUI/functionalComponent/appShell/AppShell";
import { GeoStage } from "@/components/sharedUI/functionalComponent/geoStage/GeoStage";

export default function GeospatialLayout({ children }: { children: ReactNode }) {
  return (
    <AppShell>
      <GeoStage />
      {children}
    </AppShell>
  );
}
