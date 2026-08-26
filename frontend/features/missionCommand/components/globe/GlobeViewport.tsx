// features/missionCommand/components/globe/GlobeViewport.tsx — the globe's boundary with the rest of the app.
//
// what  : Lazily loads the WebGL canvas, checks that the browser can render it, shows the loading and
//         unavailable states, and overlays the globe's own controls.
// where : Rendered by MissionCommandScreen as the centre canvas.
// how   : The 3D bundle is the largest asset on this page, so it is code-split behind next/dynamic with
//         server rendering disabled — three.js touches browser globals at import time and would fail
//         during SSR. The loading placeholder occupies the identical box, so nothing around it reflows
//         when the canvas mounts.
//
//         WebGL support is probed rather than assumed. A browser without a WebGL context must show an
//         explanation and leave the rest of the command centre fully usable, not a black rectangle or a
//         crashed React tree.
//
//         The camera handle is not passed down through props — GlobeCameraRig publishes it into the
//         feature store when it mounts, which is what lets non-React callers (the command bus, and later
//         the agent) reach the camera at all.

"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

import { usePrefersReducedMotion } from "@/hooks/use-prefers-reduced-motion";
import { useWebGlSupport } from "@/hooks/use-webgl-support";
import { cn } from "@/lib/utils";

import type { GlobeMarker } from "../../types/globe.types";
import { GlobeControls } from "./GlobeControls";
import { GlobeLoadingState, GlobeUnavailableState } from "./GlobeLoadingState";

const GlobeCanvas = dynamic(
  () => import("./GlobeCanvas").then((module) => module.GlobeCanvas),
  { ssr: false, loading: () => <GlobeLoadingState /> },
);

interface GlobeViewportProps {
  onMarkerSelect?: (marker: GlobeMarker) => void;
  className?: string;
}

export function GlobeViewport({ onMarkerSelect, className }: GlobeViewportProps) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const webGlSupport = useWebGlSupport();
  const [isGlobeReady, setIsGlobeReady] = useState(false);

  return (
    <div className={cn("absolute inset-0 overflow-hidden", className)}>
      {webGlSupport === "unknown" ? <GlobeLoadingState /> : null}
      {webGlSupport === "unsupported" ? <GlobeUnavailableState /> : null}

      {webGlSupport === "supported" ? (
        <>
          <div
            className={cn(
              "absolute inset-0 transition-opacity duration-cinematic ease-expo",
              isGlobeReady ? "opacity-100" : "opacity-0",
            )}
          >
            <GlobeCanvas
              isMotionReduced={prefersReducedMotion}
              onMarkerSelect={onMarkerSelect}
              onReady={() => setIsGlobeReady(true)}
            />
          </div>

          {!isGlobeReady ? <GlobeLoadingState /> : null}

          <GlobeControls
            className={cn(
              "transition-opacity duration-slow ease-expo",
              isGlobeReady ? "opacity-100" : "pointer-events-none opacity-0",
            )}
          />
        </>
      ) : null}
    </div>
  );
}
