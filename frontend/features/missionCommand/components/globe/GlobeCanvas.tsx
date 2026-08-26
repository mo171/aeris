// features/missionCommand/components/globe/GlobeCanvas.tsx — the react-three-fiber canvas hosting the globe.
//
// what  : Creates the WebGL context, configures the renderer and raycaster, and mounts GlobeScene.
// where : Loaded lazily by GlobeViewport; never server-rendered.
// how   : Device pixel ratio is capped. Uncapped DPR on a high-density display quadruples the fragment
//         count for no perceptible gain and is the most common cause of a globe that runs at thirty frames
//         per second on exactly the laptops analysts use.
//
//         `frameloop` follows the reduced-motion preference: operators who ask for reduced motion get a
//         static globe that renders on demand instead of a continuous animation loop, which also stops the
//         idle page from consuming GPU time.
//
//         The raycaster's Points threshold is what makes markers clickable — points have no surface area,
//         so without a threshold nothing would ever be hit.

"use client";

import { Canvas } from "@react-three/fiber";

import { GLOBE_CAMERA, GLOBE_MAX_PIXEL_RATIO } from "@/lib/constants/globe";
import { AERIS_COLOR_HEX } from "@/lib/constants/theme";

import type { GlobeMarker } from "../../types/globe.types";
import { GlobeScene } from "./GlobeScene";

const MARKER_PICK_THRESHOLD = 0.022;

interface GlobeCanvasProps {
  isMotionReduced: boolean;
  onMarkerSelect?: (marker: GlobeMarker) => void;
  onReady?: () => void;
}

export function GlobeCanvas({
  isMotionReduced,
  onMarkerSelect,
  onReady,
}: GlobeCanvasProps) {
  return (
    <Canvas
      className="absolute inset-0"
      dpr={[1, GLOBE_MAX_PIXEL_RATIO]}
      frameloop={isMotionReduced ? "demand" : "always"}
      camera={{
        fov: GLOBE_CAMERA.fieldOfView,
        near: 0.05,
        far: 100,
        position: [0, 0.6, GLOBE_CAMERA.initialDistance],
      }}
      gl={{
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
      }}
      onCreated={({ gl, raycaster }) => {
        gl.setClearColor(AERIS_COLOR_HEX.void, 0);
        // Points have no surface area, so without a pick threshold a marker could never be hit.
        raycaster.params.Points.threshold = MARKER_PICK_THRESHOLD;
      }}
    >
      <GlobeScene
        isMotionReduced={isMotionReduced}
        onMarkerSelect={onMarkerSelect}
        onReady={onReady}
      />
    </Canvas>
  );
}
