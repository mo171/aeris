// components/sharedUI/functionalComponent/geoStage/GeoStage.tsx — the 3D stage's boundary with the rest of the app.
//
// what  : Lazily loads the WebGL bundle, checks the browser can render it, shows the boot and unavailable
//         states, and holds the canvas behind every page in the geospatial route group.
// where : Rendered once by app/(geospatial)/layout.tsx, underneath {children}.
// how   : Cesium is by far the largest asset in the application, so it is code-split behind next/dynamic
//         with server rendering disabled — it touches browser globals at import time and would fail during
//         SSR. The placeholder occupies the identical box so nothing around it reflows when the viewer
//         takes over.
//
//         WebGL support is probed, never assumed. A browser without a context must show an explanation and
//         leave the rest of the application fully usable, not a black rectangle or a crashed React tree.
//
//         No props and no callbacks: pages reach the stage through the handle it publishes into
//         store/geo-stage-store.ts. That is what lets the agent and the command bus drive the Earth from
//         outside React entirely, and it is why the stage can live in a layout that knows nothing about
//         the surfaces rendered on top of it.

"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

import { usePrefersReducedMotion } from "@/hooks/use-prefers-reduced-motion";
import { useWebGlSupport } from "@/hooks/use-webgl-support";
import { cn } from "@/lib/utils";

import { StageLoadingState, StageUnavailableState } from "./StageLoadingState";

const CesiumStage = dynamic(
  () => import("./CesiumStage").then((module) => module.CesiumStage),
  { ssr: false, loading: () => <StageLoadingState /> },
);

export function GeoStage() {
  const prefersReducedMotion = usePrefersReducedMotion();
  const webGlSupport = useWebGlSupport();
  const [hasPainted, setHasPainted] = useState(false);

  return (
    <div className="absolute inset-0 overflow-hidden">
      {webGlSupport === "unknown" ? <StageLoadingState /> : null}
      {webGlSupport === "unsupported" ? <StageUnavailableState /> : null}

      {webGlSupport === "supported" ? (
        <>
          <div
            className={cn(
              "absolute inset-0 transition-opacity duration-cinematic ease-expo",
              hasPainted ? "opacity-100" : "opacity-0",
            )}
          >
            <CesiumStage
              isMotionReduced={prefersReducedMotion}
              onReady={() => setHasPainted(true)}
            />
          </div>

          {!hasPainted ? <StageLoadingState /> : null}
        </>
      ) : null}
    </div>
  );
}
