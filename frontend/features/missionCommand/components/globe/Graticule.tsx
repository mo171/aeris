// features/missionCommand/components/globe/Graticule.tsx — the latitude/longitude reference grid.
//
// what  : Draws parallels and meridians as a single line-segment mesh just above the ocean surface.
// where : Rendered by GlobeScene beneath the markers.
// how   : All lines live in one geometry rather than one mesh per parallel — twenty-four separate meshes
//         would be twenty-four draw calls for what is visually one object. The grid reads as a technical
//         instrument rather than decoration, which is what tells an operator this is a measurement
//         surface and not a marketing globe.

"use client";

import { useMemo } from "react";
import { Color } from "three";

import { GLOBE_APPEARANCE, GLOBE_RADIUS } from "@/lib/constants/globe";

import { geographicToCartesian } from "./globe-geometry";

const LINE_SEGMENT_RESOLUTION_DEGREES = 3;
const GRATICULE_RADIUS = GLOBE_RADIUS * 1.0015;

export function Graticule() {
  const positions = useMemo(() => buildGraticulePositions(), []);
  const color = useMemo(() => new Color(GLOBE_APPEARANCE.graticuleColor), []);

  return (
    <lineSegments renderOrder={2} frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <lineBasicMaterial
        color={color}
        transparent
        opacity={GLOBE_APPEARANCE.graticuleOpacity}
        depthWrite={false}
        toneMapped={false}
      />
    </lineSegments>
  );
}

function buildGraticulePositions(): Float32Array {
  const { graticuleStepDegrees } = GLOBE_APPEARANCE;
  const vertices: number[] = [];

  const pushSegment = (
    fromLatitude: number,
    fromLongitude: number,
    toLatitude: number,
    toLongitude: number,
  ) => {
    const start = geographicToCartesian(fromLatitude, fromLongitude, GRATICULE_RADIUS);
    const end = geographicToCartesian(toLatitude, toLongitude, GRATICULE_RADIUS);
    vertices.push(start.x, start.y, start.z, end.x, end.y, end.z);
  };

  // Meridians run pole to pole.
  for (let longitude = -180; longitude < 180; longitude += graticuleStepDegrees) {
    for (
      let latitude = -90;
      latitude < 90;
      latitude += LINE_SEGMENT_RESOLUTION_DEGREES
    ) {
      pushSegment(latitude, longitude, latitude + LINE_SEGMENT_RESOLUTION_DEGREES, longitude);
    }
  }

  // Parallels ring the globe; the poles themselves are skipped because a parallel there is a point.
  for (
    let latitude = -90 + graticuleStepDegrees;
    latitude < 90;
    latitude += graticuleStepDegrees
  ) {
    for (
      let longitude = -180;
      longitude < 180;
      longitude += LINE_SEGMENT_RESOLUTION_DEGREES
    ) {
      pushSegment(latitude, longitude, latitude, longitude + LINE_SEGMENT_RESOLUTION_DEGREES);
    }
  }

  return new Float32Array(vertices);
}
