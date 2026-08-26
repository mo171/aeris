// features/missionCommand/components/globe/satellite-arc-layer.ts — the ambient data streams over the globe.
//
// what  : Draws each satellite track as a faint geodesic arc with a bright pulse travelling along it.
// where : Owned by CesiumGlobe.tsx.
// how   : The path is sampled from an EllipsoidGeodesic rather than interpolated linearly, so it follows
//         the real shortest path over the Earth — the curve a satellite pass actually traces. A straight
//         line between two distant points would cut through the planet and read as obviously fake.
//
//         The apex scales with ground distance at a ratio that puts a hemisphere-crossing pass around
//         800 km up, roughly true low-Earth-orbit altitude, so the arcs sit just above the atmosphere
//         instead of forming decorative rings around the planet.
//
//         Motion comes from a custom Cesium material rather than from JavaScript. Cesium's stock
//         PolylineGlow is static — it has no notion of position along the line over time — so the pulse is
//         written as a shader over `materialInput.st.s`, the 0→1 coordinate running along each polyline.
//         The only per-frame work is writing one float uniform per arc; the travelling comet itself is
//         computed on the GPU.
//
//         Each arc carries its own phase offset so the pulses do not fire in unison, which would read as
//         a rendering artefact rather than as independent passes.

import {
  Cartesian3,
  Cartographic,
  Color,
  Ellipsoid,
  EllipsoidGeodesic,
  Material,
  PolylineCollection,
  type Polyline,
  type Scene,
} from "cesium";

import { GLOBE_SATELLITE_ARCS } from "@/lib/constants/globe";

/**
 * Fragment shader for one arc.
 *
 * `materialInput.st.s` runs 0 at the origin to 1 at the destination. The head sweeps that range on a
 * repeating cycle; everything just behind it gets an exponential falloff, producing a comet. Endpoint
 * fades stop the line terminating abruptly against the surface.
 */
const ARC_PULSE_SHADER = /* glsl */ `
  czm_material czm_getMaterial(czm_materialInput materialInput) {
    czm_material material = czm_getDefaultMaterial(materialInput);

    float alongArc = materialInput.st.s;
    float head = fract(pulseTime * pulseSpeed + pulsePhase);
    float distanceBehindHead = head - alongArc;

    // Only trail behind the head, never ahead of it.
    float trail = distanceBehindHead >= 0.0 ? exp(-distanceBehindHead * trailFalloff) : 0.0;

    float endpointFade = smoothstep(0.0, 0.06, alongArc) * smoothstep(1.0, 0.94, alongArc);

    material.diffuse = mix(trailColor.rgb, headColor.rgb, trail);
    material.alpha = endpointFade * (restAlpha + trail * pulseAlpha);
    return material;
  }
`;

export interface SatelliteArcLayer {
  setTracks: (tracks: readonly SatelliteArcInput[]) => void;
  /** Advances every arc's pulse. Called once per frame by the viewer's render loop. */
  update: (elapsedSeconds: number) => void;
  destroy: () => void;
}

export interface SatelliteArcInput {
  id: string;
  origin: { latitude: number; longitude: number };
  destination: { latitude: number; longitude: number };
  /** 0–1 offset so arcs pulse independently. */
  phase: number;
}

export function createSatelliteArcLayer(scene: Scene): SatelliteArcLayer {
  const collection = scene.primitives.add(new PolylineCollection());
  let animatedMaterials: Material[] = [];

  function setTracks(tracks: readonly SatelliteArcInput[]): void {
    collection.removeAll();
    animatedMaterials = [];

    for (const track of tracks.slice(0, GLOBE_SATELLITE_ARCS.maxVisibleArcs)) {
      const positions = buildGeodesicArc(track.origin, track.destination);
      if (positions.length === 0) {
        continue;
      }

      const material = createArcPulseMaterial(track.phase);

      collection.add({
        positions,
        width: GLOBE_SATELLITE_ARCS.widthPixels,
        material,
      }) as Polyline;

      animatedMaterials.push(material);
    }
  }

  function update(elapsedSeconds: number): void {
    for (const material of animatedMaterials) {
      material.uniforms.pulseTime = elapsedSeconds;
    }
  }

  function destroy(): void {
    animatedMaterials = [];
    if (!collection.isDestroyed()) {
      scene.primitives.remove(collection);
    }
  }

  return { setTracks, update, destroy };
}

function createArcPulseMaterial(phase: number): Material {
  return new Material({
    // Cesium caches the compiled shader against this type name, so every arc shares one program while
    // keeping its own uniform values.
    fabric: {
      type: "AerisSatelliteArcPulse",
      uniforms: {
        trailColor: Color.fromCssColorString(GLOBE_SATELLITE_ARCS.trailColor),
        headColor: Color.fromCssColorString(GLOBE_SATELLITE_ARCS.headColor),
        pulseTime: 0,
        pulseSpeed: GLOBE_SATELLITE_ARCS.pulseSpeed,
        pulsePhase: phase,
        trailFalloff: GLOBE_SATELLITE_ARCS.trailFalloff,
        restAlpha: GLOBE_SATELLITE_ARCS.restAlpha,
        pulseAlpha: GLOBE_SATELLITE_ARCS.pulseAlpha,
      },
      source: ARC_PULSE_SHADER,
    },
    translucent: true,
  });
}

function buildGeodesicArc(
  origin: { latitude: number; longitude: number },
  destination: { latitude: number; longitude: number },
): Cartesian3[] {
  const start = Cartographic.fromDegrees(origin.longitude, origin.latitude);
  const end = Cartographic.fromDegrees(destination.longitude, destination.latitude);

  // Coincident endpoints make the geodesic undefined; skip rather than emit a degenerate line.
  if (start.longitude === end.longitude && start.latitude === end.latitude) {
    return [];
  }

  const geodesic = new EllipsoidGeodesic(start, end, Ellipsoid.WGS84);
  const apexHeight = geodesic.surfaceDistance * GLOBE_SATELLITE_ARCS.apexHeightRatio;
  const positions: Cartesian3[] = [];

  for (let index = 0; index <= GLOBE_SATELLITE_ARCS.sampleCount; index += 1) {
    const fraction = index / GLOBE_SATELLITE_ARCS.sampleCount;
    const sample = geodesic.interpolateUsingFraction(fraction);
    // A sine profile puts the apex at the midpoint and returns cleanly to the surface at both ends.
    const height = apexHeight * Math.sin(Math.PI * fraction);

    positions.push(Cartesian3.fromRadians(sample.longitude, sample.latitude, height));
  }

  return positions;
}
