// features/missionCommand/components/globe/MissionMarkerLayer.tsx — mission and AOI markers on the globe.
//
// what  : Renders every marker as a pulsing point coloured by mission status, and reports clicks upward.
// where : Rendered by GlobeScene; fed by use-globe-layers.ts.
// how   : The entire marker feed is one point cloud with one draw call, and the pulse is computed in the
//         vertex shader from a time uniform and a per-marker phase attribute. Nothing about the animation
//         touches the CPU per frame — a JavaScript loop updating thousands of transforms every frame is
//         the single most common way a globe like this drops below sixty frames per second.
//
//         Phase is derived from the marker index so neighbouring markers do not pulse in lockstep; a
//         synchronised pulse reads as a rendering artefact rather than as live activity.

"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { AdditiveBlending, Color, type ShaderMaterial } from "three";

import { GLOBE_MARKERS, GLOBE_RADIUS } from "@/lib/constants/globe";
import type { GlobeMarker } from "@/features/missionCommand/types/globe.types";

import { geographicToCartesian } from "./globe-geometry";

const MARKER_RADIUS = GLOBE_RADIUS * 1.008;

const MARKER_VERTEX_SHADER = /* glsl */ `
  uniform float uTime;
  uniform float uPixelRatio;
  uniform float uBaseSize;
  uniform float uPulseSpeed;

  attribute vec3 aColor;
  attribute float aMagnitude;
  attribute float aPhase;

  varying vec3 vColor;
  varying float vFacing;
  varying float vPulse;

  void main() {
    vec4 worldPosition = modelMatrix * vec4(position, 1.0);
    vec4 viewPosition = viewMatrix * worldPosition;

    vec3 surfaceNormal = normalize(mat3(modelMatrix) * position);
    vec3 viewDirection = normalize(cameraPosition - worldPosition.xyz);
    vFacing = dot(surfaceNormal, viewDirection);

    vColor = aColor;
    vPulse = 0.5 + 0.5 * sin(uTime * uPulseSpeed + aPhase * 6.2831853);

    float magnitudeScale = 0.55 + aMagnitude * 0.75;
    float pulseScale = 1.0 + vPulse * 0.35;

    gl_Position = projectionMatrix * viewPosition;
    gl_PointSize = uBaseSize * magnitudeScale * pulseScale * uPixelRatio
      * (1.0 / max(-viewPosition.z, 0.0001));
  }
`;

const MARKER_FRAGMENT_SHADER = /* glsl */ `
  varying vec3 vColor;
  varying float vFacing;
  varying float vPulse;

  void main() {
    if (vFacing < 0.02) {
      discard;
    }

    vec2 offsetFromCentre = gl_PointCoord - vec2(0.5);
    float distanceFromCentre = length(offsetFromCentre);
    if (distanceFromCentre > 0.5) {
      discard;
    }

    // A bright core with a soft halo, so a marker still reads at one or two pixels across.
    float core = smoothstep(0.16, 0.02, distanceFromCentre);
    float halo = smoothstep(0.5, 0.14, distanceFromCentre) * (0.28 + vPulse * 0.3);
    float limbFade = smoothstep(0.0, 0.3, vFacing);

    float alpha = clamp(core + halo, 0.0, 1.0) * limbFade;
    gl_FragColor = vec4(vColor, alpha);
  }
`;

interface MissionMarkerLayerProps {
  markers: readonly GlobeMarker[];
  onMarkerSelect?: (marker: GlobeMarker) => void;
}

export function MissionMarkerLayer({ markers, onMarkerSelect }: MissionMarkerLayerProps) {
  const materialRef = useRef<ShaderMaterial | null>(null);

  const renderedMarkers = useMemo(() => {
    if (markers.length <= GLOBE_MARKERS.maxRenderedMarkers) {
      return markers;
    }
    return [...markers]
      .sort((left, right) => right.magnitude - left.magnitude)
      .slice(0, GLOBE_MARKERS.maxRenderedMarkers);
  }, [markers]);

  const attributes = useMemo(() => buildMarkerAttributes(renderedMarkers), [renderedMarkers]);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uPixelRatio: { value: typeof window === "undefined" ? 1 : Math.min(window.devicePixelRatio, 2) },
      uBaseSize: { value: GLOBE_MARKERS.baseSize },
      uPulseSpeed: { value: GLOBE_MARKERS.pulseSpeed },
    }),
    [],
  );

  useFrame((state) => {
    if (materialRef.current) {
      materialRef.current.uniforms.uTime.value = state.clock.elapsedTime;
    }
  });

  if (renderedMarkers.length === 0) {
    return null;
  }

  return (
    <points
      renderOrder={3}
      frustumCulled={false}
      onPointerDown={(event) => {
        if (!onMarkerSelect || event.index === undefined) {
          return;
        }
        event.stopPropagation();
        const marker = renderedMarkers[event.index];
        if (marker) {
          onMarkerSelect(marker);
        }
      }}
    >
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[attributes.positions, 3]} />
        <bufferAttribute attach="attributes-aColor" args={[attributes.colors, 3]} />
        <bufferAttribute attach="attributes-aMagnitude" args={[attributes.magnitudes, 1]} />
        <bufferAttribute attach="attributes-aPhase" args={[attributes.phases, 1]} />
      </bufferGeometry>
      <shaderMaterial
        ref={materialRef}
        uniforms={uniforms}
        vertexShader={MARKER_VERTEX_SHADER}
        fragmentShader={MARKER_FRAGMENT_SHADER}
        transparent
        depthWrite={false}
        blending={AdditiveBlending}
        toneMapped={false}
      />
    </points>
  );
}

function buildMarkerAttributes(markers: readonly GlobeMarker[]) {
  const positions = new Float32Array(markers.length * 3);
  const colors = new Float32Array(markers.length * 3);
  const magnitudes = new Float32Array(markers.length);
  const phases = new Float32Array(markers.length);

  const colorCache = new Map<string, Color>();

  markers.forEach((marker, index) => {
    const point = geographicToCartesian(
      marker.position.latitude,
      marker.position.longitude,
      MARKER_RADIUS,
    );
    positions[index * 3] = point.x;
    positions[index * 3 + 1] = point.y;
    positions[index * 3 + 2] = point.z;

    let color = colorCache.get(marker.status);
    if (!color) {
      color = new Color(GLOBE_MARKERS.statusColor[marker.status]);
      colorCache.set(marker.status, color);
    }
    colors[index * 3] = color.r;
    colors[index * 3 + 1] = color.g;
    colors[index * 3 + 2] = color.b;

    magnitudes[index] = marker.magnitude;
    // Golden-ratio stride spreads phases evenly without a random number generator.
    phases[index] = (index * 0.618033988749895) % 1;
  });

  return { positions, colors, magnitudes, phases };
}
