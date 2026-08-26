// features/missionCommand/components/globe/SatelliteArcLayer.tsx — the ambient data streams over the globe.
//
// what  : Draws each satellite track as an arc with a bright pulse travelling along it.
// where : Rendered by GlobeScene above the markers.
// how   : Every arc is merged into one line-segment geometry with per-vertex progress and phase
//         attributes, so the whole ambient layer is a single draw call and the travelling head is a
//         windowed function of a time uniform. Rendering one line object per track would multiply draw
//         calls by the size of the feed for no visual gain.
//
//         This is the design report's idle-state wow factor. It is intentionally low contrast: it must
//         suggest a living system without competing with the mission markers, which carry actual meaning.

"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { AdditiveBlending, Color, type ShaderMaterial } from "three";

import { GLOBE_RADIUS, GLOBE_SATELLITE_ARCS } from "@/lib/constants/globe";
import type { SatelliteTrack } from "@/features/missionCommand/types/globe.types";

import { sampleArcPoints } from "./globe-geometry";

const ARC_VERTEX_SHADER = /* glsl */ `
  attribute float aProgress;
  attribute float aPhase;

  varying float vProgress;
  varying float vPhase;

  void main() {
    vProgress = aProgress;
    vPhase = aPhase;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const ARC_FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uTrailColor;
  uniform vec3 uHeadColor;
  uniform float uTime;
  uniform float uSpeed;

  varying float vProgress;
  varying float vPhase;

  void main() {
    // The head sweeps from 0 to 1 along the arc and wraps; each arc is offset by its own phase.
    float head = fract(uTime * uSpeed + vPhase);
    float distanceBehindHead = head - vProgress;
    // Only trail behind the head, never ahead of it.
    float trail = distanceBehindHead >= 0.0 ? exp(-distanceBehindHead * 14.0) : 0.0;

    // Arcs fade in and out at their endpoints so they never terminate abruptly on the surface.
    float endpointFade = smoothstep(0.0, 0.09, vProgress) * smoothstep(1.0, 0.91, vProgress);

    vec3 color = mix(uTrailColor, uHeadColor, trail);
    float alpha = endpointFade * (0.1 + trail * 0.9);
    gl_FragColor = vec4(color, alpha);
  }
`;

interface SatelliteArcLayerProps {
  tracks: readonly SatelliteTrack[];
}

export function SatelliteArcLayer({ tracks }: SatelliteArcLayerProps) {
  const materialRef = useRef<ShaderMaterial | null>(null);

  const visibleTracks = useMemo(
    () => tracks.slice(0, GLOBE_SATELLITE_ARCS.maxVisibleArcs),
    [tracks],
  );

  const attributes = useMemo(() => buildArcAttributes(visibleTracks), [visibleTracks]);

  const uniforms = useMemo(
    () => ({
      uTrailColor: { value: new Color(GLOBE_SATELLITE_ARCS.color) },
      uHeadColor: { value: new Color(GLOBE_SATELLITE_ARCS.headColor) },
      uTime: { value: 0 },
      uSpeed: { value: GLOBE_SATELLITE_ARCS.travelSpeed },
    }),
    [],
  );

  useFrame((state) => {
    if (materialRef.current) {
      materialRef.current.uniforms.uTime.value = state.clock.elapsedTime;
    }
  });

  if (attributes.positions.length === 0) {
    return null;
  }

  return (
    <lineSegments renderOrder={5} frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[attributes.positions, 3]} />
        <bufferAttribute attach="attributes-aProgress" args={[attributes.progress, 1]} />
        <bufferAttribute attach="attributes-aPhase" args={[attributes.phases, 1]} />
      </bufferGeometry>
      <shaderMaterial
        ref={materialRef}
        uniforms={uniforms}
        vertexShader={ARC_VERTEX_SHADER}
        fragmentShader={ARC_FRAGMENT_SHADER}
        transparent
        depthWrite={false}
        blending={AdditiveBlending}
        toneMapped={false}
      />
    </lineSegments>
  );
}

function buildArcAttributes(tracks: readonly SatelliteTrack[]) {
  const { segmentCount, altitudeFactor } = GLOBE_SATELLITE_ARCS;
  const positions: number[] = [];
  const progress: number[] = [];
  const phases: number[] = [];

  for (const track of tracks) {
    const arcPoints = sampleArcPoints(
      track.origin,
      track.destination,
      GLOBE_RADIUS,
      altitudeFactor,
      segmentCount,
    );

    // Expand the sampled polyline into discrete segments for lineSegments rendering.
    for (let index = 0; index < segmentCount; index += 1) {
      const startOffset = index * 3;
      const endOffset = (index + 1) * 3;

      positions.push(
        arcPoints[startOffset],
        arcPoints[startOffset + 1],
        arcPoints[startOffset + 2],
        arcPoints[endOffset],
        arcPoints[endOffset + 1],
        arcPoints[endOffset + 2],
      );
      progress.push(index / segmentCount, (index + 1) / segmentCount);
      phases.push(track.phase, track.phase);
    }
  }

  return {
    positions: new Float32Array(positions),
    progress: new Float32Array(progress),
    phases: new Float32Array(phases),
  };
}
