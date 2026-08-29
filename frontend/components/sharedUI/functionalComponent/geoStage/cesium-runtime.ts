// components/sharedUI/functionalComponent/geoStage/cesium-runtime.ts — Cesium bootstrapping and imagery providers.
//
// what  : Points Cesium at its static assets, applies the Ion token when one exists, and builds the
//         imagery and terrain providers for both the Ion and the no-token paths.
// where : Used only by CesiumStage.tsx. No file outside this geoStage folder may import `cesium`.
// how   : window.CESIUM_BASE_URL must be set before a Viewer is constructed, or Cesium resolves its web
//         workers and glTF assets against the wrong origin and the globe fails with no useful error. It is
//         assigned at module scope here, which runs when this module is first imported — always before any
//         Viewer exists, because CesiumStage imports this file.
//
//         Two rendering paths, chosen by whether NEXT_PUBLIC_CESIUM_ION_TOKEN is present:
//           token   -> Ion world imagery + real elevation terrain. The intended experience.
//           no token-> dark raster basemap on a smooth ellipsoid. Real geography, flat.
//         The fallback exists so the application never boots to a black sphere, not as an equal option.

import {
  Cesium3DTileStyle,
  EllipsoidTerrainProvider,
  ImageryLayer,
  Ion,
  UrlTemplateImageryProvider,
  createOsmBuildingsAsync,
  createWorldTerrainAsync,
  type Cesium3DTileset,
  type TerrainProvider,
  type Viewer,
} from "cesium";

import { CESIUM_BASE_URL, GLOBE_APPEARANCE, GLOBE_BASEMAP } from "@/lib/constants/globe";
import { SCENE_RELIEF } from "@/lib/constants/investigation";
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

/**
 * Building massing for the close-range scene.
 *
 * This is the single largest visual return available to this surface. Terrain cannot make a city look
 * three-dimensional — relief across a four-kilometre urban area is tens of metres, well under one percent
 * of the view at the altitude that frames it — because in a city the vertical information is in the
 * buildings, not the ground. One tileset supplies it.
 *
 * Styled to a desaturated slate rather than left at the default white. Buildings are context, not the
 * finding: white massing out-contrasts every evidence colour on the scene and turns an analysis surface
 * into an architectural render.
 *
 * Returns null without an Ion token, which is a supported state — the scene stays flat rather than
 * failing.
 */
export async function createBuildingMassing(): Promise<Cesium3DTileset | null> {
  if (!hasIonAccess()) {
    return null;
  }

  try {
    const tileset = await createOsmBuildingsAsync();
    tileset.style = new Cesium3DTileStyle({
      color: `color("${SCENE_RELIEF.buildingColorCss}", ${SCENE_RELIEF.buildingAlpha})`,
    });
    return tileset;
  } catch (error) {
    console.warn("[AERIS] Building massing unavailable, the scene stays flat.", error);
    return null;
  }
}
