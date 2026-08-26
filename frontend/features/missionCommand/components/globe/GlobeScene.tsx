// features/missionCommand/components/globe/GlobeScene.tsx — assembles every layer of the 3D Earth.
//
// what  : Composes the camera rig, ocean sphere, land dots, graticule, markers, satellite arcs and
//         atmospheric glow into one scene.
// where : Rendered inside the react-three-fiber Canvas in GlobeCanvas.
// how   : Layer order is explicit through renderOrder rather than left to declaration order, because the
//         transparent layers must be drawn after the opaque sphere has filled the depth buffer. Each layer
//         is independently null-safe: markers, arcs and land dots all render nothing until their data
//         arrives, so the globe appears as soon as the sphere is ready and fills in progressively rather
//         than blocking on the slowest feed.

"use client";

import { useMemo } from "react";

import { useGlobeLayers } from "../../hooks/use-globe-layers";
import { useLandDots } from "../../hooks/use-land-dots";
import type { GlobeMarker } from "../../types/globe.types";

import { AtmosphereGlow, EarthSphere } from "./EarthSphere";
import { EarthLandDots } from "./EarthLandDots";
import { GlobeCameraRig } from "./GlobeCameraRig";
import { Graticule } from "./Graticule";
import { MissionMarkerLayer } from "./MissionMarkerLayer";
import { SatelliteArcLayer } from "./SatelliteArcLayer";

interface GlobeSceneProps {
  isMotionReduced: boolean;
  onMarkerSelect?: (marker: GlobeMarker) => void;
  onReady?: () => void;
}

export function GlobeScene({
  isMotionReduced,
  onMarkerSelect,
  onReady,
}: GlobeSceneProps) {
  const { positions: landDotPositions } = useLandDots();
  const { markers, satelliteTracks } = useGlobeLayers();

  // A gentle axial tilt makes the planet read as a body in space rather than a spinning UI element.
  const sceneRotation = useMemo<[number, number, number]>(() => [0, 0, -0.41], []);

  return (
    <>
      <GlobeCameraRig isMotionReduced={isMotionReduced} onReady={onReady} />

      <ambientLight intensity={0.4} />

      <group rotation={sceneRotation}>
        <EarthSphere />
        {landDotPositions ? <EarthLandDots positions={landDotPositions} /> : null}
        <Graticule />
        <MissionMarkerLayer markers={markers} onMarkerSelect={onMarkerSelect} />
        <SatelliteArcLayer tracks={satelliteTracks} />
        <AtmosphereGlow />
      </group>
    </>
  );
}
