// features/missionCommand/components/globe/EarthSphere.tsx — the opaque ocean body of the globe.
//
// what  : A solid sphere at the globe radius, shaded with a subtle depth gradient toward the limb.
// where : The base layer of GlobeScene; every other layer sits fractionally above it.
// how   : This sphere is opaque and writes to the depth buffer, which is what occludes the land dots,
//         graticule and markers on the far side of the planet. That is deliberate and load-bearing: doing
//         back-face culling per layer would mean three separate implementations of the same idea, and the
//         depth buffer does it correctly for free.

"use client";

import { useMemo } from "react";
import { BackSide, Color, FrontSide } from "three";

import { GLOBE_APPEARANCE, GLOBE_RADIUS } from "@/lib/constants/globe";

const OCEAN_VERTEX_SHADER = /* glsl */ `
  varying vec3 vNormalDirection;
  varying vec3 vViewDirection;

  void main() {
    vec4 worldPosition = modelMatrix * vec4(position, 1.0);
    vNormalDirection = normalize(mat3(modelMatrix) * normal);
    vViewDirection = normalize(cameraPosition - worldPosition.xyz);
    gl_Position = projectionMatrix * viewMatrix * worldPosition;
  }
`;

const OCEAN_FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uCoreColor;
  uniform vec3 uLimbColor;
  varying vec3 vNormalDirection;
  varying vec3 vViewDirection;

  void main() {
    // Facing the camera dead-on gives 1, grazing the limb gives 0.
    float facing = max(dot(vNormalDirection, vViewDirection), 0.0);
    float limbBlend = pow(1.0 - facing, 2.4);
    vec3 surfaceColor = mix(uCoreColor, uLimbColor, limbBlend * 0.85);
    gl_FragColor = vec4(surfaceColor, 1.0);
  }
`;

export function EarthSphere() {
  const uniforms = useMemo(
    () => ({
      uCoreColor: { value: new Color(GLOBE_APPEARANCE.oceanColor) },
      uLimbColor: { value: new Color(GLOBE_APPEARANCE.rimColor) },
    }),
    [],
  );

  return (
    <mesh renderOrder={0}>
      <sphereGeometry args={[GLOBE_RADIUS, 96, 96]} />
      <shaderMaterial
        uniforms={uniforms}
        vertexShader={OCEAN_VERTEX_SHADER}
        fragmentShader={OCEAN_FRAGMENT_SHADER}
        side={FrontSide}
        toneMapped={false}
      />
    </mesh>
  );
}

const ATMOSPHERE_VERTEX_SHADER = /* glsl */ `
  varying vec3 vNormalDirection;
  varying vec3 vViewDirection;

  void main() {
    vec4 worldPosition = modelMatrix * vec4(position, 1.0);
    vNormalDirection = normalize(mat3(modelMatrix) * normal);
    vViewDirection = normalize(cameraPosition - worldPosition.xyz);
    gl_Position = projectionMatrix * viewMatrix * worldPosition;
  }
`;

const ATMOSPHERE_FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColor;
  uniform float uIntensity;
  varying vec3 vNormalDirection;
  varying vec3 vViewDirection;

  void main() {
    // Rendered on the back faces of an enlarged shell, so the normal points away from the camera and the
    // glow concentrates around the silhouette — the classic atmospheric rim.
    float rim = pow(1.0 - abs(dot(vNormalDirection, vViewDirection)), 3.2);
    gl_FragColor = vec4(uColor, rim * uIntensity);
  }
`;

export function AtmosphereGlow() {
  const uniforms = useMemo(
    () => ({
      uColor: { value: new Color(GLOBE_APPEARANCE.atmosphereColor) },
      uIntensity: { value: GLOBE_APPEARANCE.atmosphereIntensity },
    }),
    [],
  );

  return (
    <mesh renderOrder={4}>
      <sphereGeometry args={[GLOBE_RADIUS * GLOBE_APPEARANCE.atmosphereScale, 64, 64]} />
      <shaderMaterial
        uniforms={uniforms}
        vertexShader={ATMOSPHERE_VERTEX_SHADER}
        fragmentShader={ATMOSPHERE_FRAGMENT_SHADER}
        side={BackSide}
        transparent
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}
