// features/missionCommand/components/globe/globe-geometry.ts — pure maths shared by every globe layer.
//
// what  : Latitude/longitude to Cartesian conversion, camera-position maths, great-circle arc sampling,
//         and the land-mask rasteriser that turns TopoJSON into a sampled point cloud.
// where : Used by the land dot layer, the marker layer, the arc layer and the camera controller.
// how   : Kept free of React and three.js scene objects so the geometry can be reasoned about and reused
//         without a renderer. The land sampling in particular is the expensive step, and isolating it here
//         is what lets it run once, off the render path, and be cached.
//
//         Land sampling works by rasterising the land polygons into an offscreen equirectangular canvas
//         and then testing candidate points against that bitmap. Testing points against polygons directly
//         is O(points × rings) and far too slow for tens of thousands of candidates; a bitmap lookup is
//         O(1) per point. d3-geo does the projection because it clips correctly at the antimeridian —
//         a hand-rolled projection smears Russia and Antarctica across the whole map.

import { geoEquirectangular, geoPath } from "d3-geo";
import type { GeoPermissibleObjects } from "d3-geo";

import { LAND_DOT_SAMPLING } from "@/lib/constants/globe";

const DEGREES_TO_RADIANS = Math.PI / 180;

export interface CartesianPoint {
  x: number;
  y: number;
  z: number;
}

/**
 * Converts geographic coordinates to a position on a sphere of the given radius.
 * The mapping matches three.js convention: +Y is north, and longitude 0 faces +Z.
 */
export function geographicToCartesian(
  latitude: number,
  longitude: number,
  radius: number,
): CartesianPoint {
  const polarAngle = (90 - latitude) * DEGREES_TO_RADIANS;
  const azimuthalAngle = (longitude + 180) * DEGREES_TO_RADIANS;

  return {
    x: -radius * Math.sin(polarAngle) * Math.cos(azimuthalAngle),
    y: radius * Math.cos(polarAngle),
    z: radius * Math.sin(polarAngle) * Math.sin(azimuthalAngle),
  };
}

/** Samples a quadratic arc that bulges away from the globe, used for satellite tracks. */
export function sampleArcPoints(
  origin: { latitude: number; longitude: number },
  destination: { latitude: number; longitude: number },
  radius: number,
  altitudeFactor: number,
  segmentCount: number,
): Float32Array {
  const start = geographicToCartesian(origin.latitude, origin.longitude, radius);
  const end = geographicToCartesian(destination.latitude, destination.longitude, radius);

  // The control point sits above the midpoint of the chord; how far above scales with the separation,
  // so short hops stay low and hemisphere-crossing tracks arc high.
  const midpoint = {
    x: (start.x + end.x) / 2,
    y: (start.y + end.y) / 2,
    z: (start.z + end.z) / 2,
  };
  const midpointLength = Math.hypot(midpoint.x, midpoint.y, midpoint.z) || 1;
  const separation = Math.hypot(end.x - start.x, end.y - start.y, end.z - start.z);
  const controlRadius = radius + altitudeFactor * separation;
  const control = {
    x: (midpoint.x / midpointLength) * controlRadius,
    y: (midpoint.y / midpointLength) * controlRadius,
    z: (midpoint.z / midpointLength) * controlRadius,
  };

  const positions = new Float32Array((segmentCount + 1) * 3);

  for (let index = 0; index <= segmentCount; index += 1) {
    const t = index / segmentCount;
    const inverse = 1 - t;
    const weightStart = inverse * inverse;
    const weightControl = 2 * inverse * t;
    const weightEnd = t * t;

    positions[index * 3] = weightStart * start.x + weightControl * control.x + weightEnd * end.x;
    positions[index * 3 + 1] = weightStart * start.y + weightControl * control.y + weightEnd * end.y;
    positions[index * 3 + 2] = weightStart * start.z + weightControl * control.z + weightEnd * end.z;
  }

  return positions;
}

/**
 * Rasterises land geometry and returns sphere-surface positions for every sampled land point.
 * Longitude samples per latitude band scale with cos(latitude), which keeps dot spacing roughly even
 * across the sphere instead of crowding at the poles.
 */
export function buildLandDotPositions(
  landGeometry: GeoPermissibleObjects,
  radius: number,
): Float32Array {
  const mask = rasteriseLandMask(landGeometry);
  if (!mask) {
    return new Float32Array(0);
  }

  const { spacingDegrees } = LAND_DOT_SAMPLING;
  const positions: number[] = [];

  for (let latitude = -85; latitude <= 85; latitude += spacingDegrees) {
    const latitudeRadians = latitude * DEGREES_TO_RADIANS;
    const longitudeSampleCount = Math.max(
      6,
      Math.round((360 / spacingDegrees) * Math.cos(latitudeRadians)),
    );

    for (let sample = 0; sample < longitudeSampleCount; sample += 1) {
      const longitude = -180 + (360 * sample) / longitudeSampleCount;

      if (!isLandAt(mask, latitude, longitude)) {
        continue;
      }

      const point = geographicToCartesian(latitude, longitude, radius);
      positions.push(point.x, point.y, point.z);
    }
  }

  return new Float32Array(positions);
}

interface LandMask {
  data: Uint8ClampedArray;
  width: number;
  height: number;
}

function rasteriseLandMask(landGeometry: GeoPermissibleObjects): LandMask | null {
  const { maskWidth, maskHeight } = LAND_DOT_SAMPLING;

  const canvas = document.createElement("canvas");
  canvas.width = maskWidth;
  canvas.height = maskHeight;

  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    return null;
  }

  const projection = geoEquirectangular()
    .translate([maskWidth / 2, maskHeight / 2])
    .scale(maskWidth / (2 * Math.PI));

  context.fillStyle = "#000000";
  context.fillRect(0, 0, maskWidth, maskHeight);
  context.fillStyle = "#ffffff";
  context.beginPath();
  geoPath(projection, context)(landGeometry);
  context.fill();

  return {
    data: context.getImageData(0, 0, maskWidth, maskHeight).data,
    width: maskWidth,
    height: maskHeight,
  };
}

function isLandAt(mask: LandMask, latitude: number, longitude: number): boolean {
  const x = Math.floor(((longitude + 180) / 360) * mask.width);
  const y = Math.floor(((90 - latitude) / 180) * mask.height);

  if (x < 0 || y < 0 || x >= mask.width || y >= mask.height) {
    return false;
  }

  // Any non-black red channel means the rasteriser painted land here.
  return mask.data[(y * mask.width + x) * 4] > 96;
}
