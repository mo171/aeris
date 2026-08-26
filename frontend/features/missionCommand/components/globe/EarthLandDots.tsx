// features/missionCommand/components/globe/EarthLandDots.tsx — the continents, drawn as a glowing point cloud.
//
// what  : Renders every sampled land position as a soft circular point, fading toward the limb.
// where : The second layer of GlobeScene, sitting fractionally above the ocean sphere.
// how   : One draw call for roughly twenty thousand points. Points are used rather than instanced meshes
//         because a point has no geometry to transform — the GPU rasterises a screen-space quad from a
//         single vertex, which is an order of magnitude cheaper at this count.
//
//         Circles are cut out of the point quad in the fragment shader using gl_PointCoord rather than
//         sampled from a sprite texture: no texture upload, no filtering artefacts, and the edge stays
//         crisp at every zoom level.

"use client";

import { useMemo } from "react";
import { AdditiveBlending, Color } from "three";

import { GLOBE_APPEARANCE, LAND_DOT_SAMPLING } from "@/lib/constants/globe";

const LAND_DOT_VERTEX_SHADER = /* glsl */ `
  uniform float uSize;
  uniform float uPixelRatio;
  varying float vFacing;

  void main() {
    vec4 worldPosition = modelMatrix * vec4(position, 1.0);
    vec4 viewPosition = viewMatrix * worldPosition;

    vec3 surfaceNormal = normalize(mat3(modelMatrix) * position);
    vec3 viewDirection = normalize(cameraPosition - worldPosition.xyz);
    vFacing = dot(surfaceNormal, viewDirection);

    gl_Position = projectionMatrix * viewPosition;
    // Perspective size attenuation: dots shrink with distance the way real surface features would.
    gl_PointSize = uSize * uPixelRatio * (1.0 / max(-viewPosition.z, 0.0001));
  }
`;

const LAND_DOT_FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  varying float vFacing;

  void main() {
    vec2 offsetFromCentre = gl_PointCoord - vec2(0.5);
    float squaredDistance = dot(offsetFromCentre, offsetFromCentre);
    if (squaredDistance > 0.25) {
      discard;
    }

    float circleEdge = smoothstep(0.25, 0.04, squaredDistance);
    // Dots near the silhouette fade out, which stops the coastline from looking like a hard cut-out.
    float limbFade = smoothstep(0.0, 0.42, vFacing);
    gl_FragColor = vec4(uColor, uOpacity * circleEdge * limbFade);
  }
`;

interface EarthLandDotsProps {
  positions: Float32Array;
}

export function EarthLandDots({ positions }: EarthLandDotsProps) {
  const uniforms = useMemo(
    () => ({
      uColor: { value: new Color(GLOBE_APPEARANCE.landDotColor) },
      uOpacity: { value: GLOBE_APPEARANCE.landDotOpacity },
      uSize: { value: LAND_DOT_SAMPLING.dotSize * 900 },
      uPixelRatio: { value: typeof window === "undefined" ? 1 : Math.min(window.devicePixelRatio, 2) },
    }),
    [],
  );

  const pointCount = positions.length / 3;

  if (pointCount === 0) {
    return null;
  }

  return (
    <points renderOrder={1} frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <shaderMaterial
        uniforms={uniforms}
        vertexShader={LAND_DOT_VERTEX_SHADER}
        fragmentShader={LAND_DOT_FRAGMENT_SHADER}
        transparent
        depthWrite={false}
        blending={AdditiveBlending}
        toneMapped={false}
      />
    </points>
  );
}
