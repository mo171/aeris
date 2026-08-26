// features/missionCommand/components/globe/cesium-runtime.ts — Cesium bootstrapping and imagery providers.
//
// what  : Points Cesium at its static assets, applies the Ion token when one exists, and builds the
//         imagery and terrain providers for both the Ion and the no-token paths.
// where : Used only by CesiumGlobe.tsx. Nothing else in the application may import `cesium`.
// how   : window.CESIUM_BASE_URL must be set before a Viewer is constructed, or Cesium resolves its web
//         workers and glTF assets against the wrong origin and the globe fails with no useful error. It is
//         assigned at module scope here, which runs when this module is first imported — always before any
//         Viewer exists, because CesiumGlobe imports this file.
//
//         Two rendering paths, chosen by whether NEXT_PUBLIC_CESIUM_ION_TOKEN is present:
//           token   -> Ion world imagery + real elevation terrain. The intended experience.
//           no token-> dark raster basemap on a smooth ellipsoid. Real geography, flat.
//         The fallback exists so the application never boots to a black sphere, not as an equal option.

import {
  EllipsoidTerrainProvider,
  ImageryLayer,
  Ion,
  UrlTemplateImageryProvider,
  createWorldTerrainAsync,
  type TerrainProvider,
  type Viewer,
} from "cesium";

import { CESIUM_BASE_URL, GLOBE_APPEARANCE, GLOBE_BASEMAP } from "@/lib/constants/globe";
import { env } from "@/lib/env";

declare global {
  interface Window {
    CESIUM_BASE_URL?: string;
  }
}

if (typeof window !== "undefined") {
  window.CESIUM_BASE_URL = CESIUM_BASE_URL;
}

const ionAccessToken = env.NEXT_PUBLIC_CESIUM_ION_TOKEN.trim();

if (ionAccessToken.length > 0) {
  Ion.defaultAccessToken = ionAccessToken;
}

export function hasIonAccess(): boolean {
  return ionAccessToken.length > 0;
}

/**
 * The imagery layer the viewer starts with. Always synchronous, so the globe has something to draw on the
 * very first frame — Ion imagery is swapped in afterwards if a token is available.
 */
export function createFallbackImageryLayer(): ImageryLayer {
  const layer = new ImageryLayer(
    new UrlTemplateImageryProvider({
      url: GLOBE_BASEMAP.fallbackTileUrl,
      credit: GLOBE_BASEMAP.fallbackAttribution,
      maximumLevel: GLOBE_BASEMAP.fallbackMaximumLevel,
    }),
  );

  applyAerisImageryGrading(layer);
  return layer;
}

/**
 * Tones the basemap down so AERIS markers and analysis overlays remain the brightest things on screen.
 * An un-graded basemap competes with the evidence drawn on top of it, which is the wrong visual priority
 * for an analysis surface.
 */
export function applyAerisImageryGrading(layer: ImageryLayer): void {
  layer.brightness = GLOBE_APPEARANCE.imageryBrightness;
  layer.contrast = GLOBE_APPEARANCE.imageryContrast;
  layer.saturation = GLOBE_APPEARANCE.imagerySaturation;
  layer.gamma = GLOBE_APPEARANCE.imageryGamma;
}

/**
 * Upgrades a running viewer to Ion world imagery and real elevation terrain.
 * Deliberately fire-and-forget and failure-tolerant: if Ion is unreachable or the token is rejected, the
 * operator keeps a working flat globe rather than losing the whole command centre to a network error.
 */
export async function upgradeToIonImageryAndTerrain(viewer: Viewer): Promise<void> {
  if (!hasIonAccess() || viewer.isDestroyed()) {
    return;
  }

  try {
    const worldImagery = ImageryLayer.fromWorldImagery({});
    applyAerisImageryGrading(worldImagery);

    if (viewer.isDestroyed()) {
      return;
    }

    viewer.imageryLayers.removeAll();
    viewer.imageryLayers.add(worldImagery);
  } catch (error) {
    console.warn("[AERIS] Ion world imagery unavailable, keeping the fallback basemap.", error);
  }

  try {
    // Vertex normals are what let the sun light the terrain; without them relief stays flat-shaded.
    const terrain: TerrainProvider = await createWorldTerrainAsync({
      requestVertexNormals: true,
      requestWaterMask: false,
    });

    if (!viewer.isDestroyed()) {
      viewer.terrainProvider = terrain;
    }
  } catch (error) {
    console.warn("[AERIS] Ion world terrain unavailable, staying on the ellipsoid.", error);
  }
}

export function createEllipsoidTerrain(): TerrainProvider {
  return new EllipsoidTerrainProvider();
}
