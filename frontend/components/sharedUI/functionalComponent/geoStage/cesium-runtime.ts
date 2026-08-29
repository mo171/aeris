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
  Cesium3DTileset,
  Cesium3DTileStyle,
  createGooglePhotorealistic3DTileset,
  EllipsoidTerrainProvider,
  ImageryLayer,
  Ion,
  UrlTemplateImageryProvider,
  createOsmBuildingsAsync,
  createWorldTerrainAsync,
  type TerrainProvider,
  type Viewer,
} from "cesium";

import { CESIUM_BASE_URL, GLOBE_APPEARANCE, GLOBE_BASEMAP } from "@/lib/constants/globe";
import { SCENE_RELIEF } from "@/lib/constants/investigation";
import {
  BUILDING_HEIGHT_SCHEME,
  OSM_BUILDING_PROPERTIES,
  OSM_BUILDING_TAG_CLASSES,
  binRampPosition,
  classForBuildingTag,
  sampleRamp,
  type BuildingStyleId,
} from "@/lib/constants/overlays";
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
const googleMapsApiKey = env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY.trim();

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
    tileset.style = buildBuildingTileStyle("uniform");
    return tileset;
  } catch (error) {
    console.warn("[AERIS] Building massing unavailable, the scene stays flat.", error);
    return null;
  }
}

/**
 * The style expression that colours the massing by one of its own attributes.
 *
 * Built from the overlay catalogue rather than written out here, so the buildings on the scene and the
 * swatches in the legend are the same palette by construction — a hand-written expression would be a
 * second copy of the colours, free to drift from the first.
 *
 * Conditions evaluate top to bottom and the last entry is an unconditional fallback, which is what keeps
 * an unmapped OSM tag or a missing height visible rather than transparent. A building that vanishes
 * because nobody typed its tag into a list is worse than one drawn in the unspecified tone.
 */
export function buildBuildingTileStyle(styleId: BuildingStyleId): Cesium3DTileStyle {
  const alpha = SCENE_RELIEF.buildingAlpha;
  // Bracket form, not `${name}`. Cesium's estimated-height property contains a '#', which the shorthand
  // cannot parse — it fails silently and every building falls through to the last condition.
  const typeProperty = `\${feature['${OSM_BUILDING_PROPERTIES.type}']}`;
  const heightProperty = `\${feature['${OSM_BUILDING_PROPERTIES.estimatedHeight}']}`;

  if (styleId === "type") {
    const conditions: [string, string][] = Object.entries(OSM_BUILDING_TAG_CLASSES).map(
      ([, tags]) => {
        const { color } = classForBuildingTag(tags[0]);
        const membership = tags.map((tag) => `${typeProperty} === '${tag}'`).join(" || ");
        return [membership, `color("${color}", ${alpha})`];
      },
    );

    const unspecified = classForBuildingTag(null);
    conditions.push(["true", `color("${unspecified.color}", ${alpha})`]);
    return new Cesium3DTileStyle({ color: { conditions } });
  }

  if (styleId === "height") {
    const bandColor = (index: number) =>
      sampleRamp(
        BUILDING_HEIGHT_SCHEME.rampId,
        binRampPosition(BUILDING_HEIGHT_SCHEME.id, index),
      );

    const conditions: [string, string][] = BUILDING_HEIGHT_SCHEME.bins
      .filter((bin) => Number.isFinite(bin.upperBound))
      .map((bin, index) => [
        `${heightProperty} <= ${bin.upperBound}`,
        `color("${bandColor(index)}", ${alpha})`,
      ]);

    // The open top band, and with it any footprint whose height is missing — which still has to draw.
    conditions.push([
      "true",
      `color("${bandColor(BUILDING_HEIGHT_SCHEME.bins.length - 1)}", ${alpha})`,
    ]);
    return new Cesium3DTileStyle({ color: { conditions } });
  }

  return new Cesium3DTileStyle({
    color: `color("${SCENE_RELIEF.buildingColorCss}", ${alpha})`,
  });
}


/**
 * Google Photorealistic 3D Tiles — textured photogrammetry of the real city.
 *
 * NOT a replacement for building massing, and not an analysis surface. The trade, stated honestly:
 *
 *   MASSING (createBuildingMassing, above) is free, is grey untextured boxes, and sits ON TOP of the
 *   operator's imagery — so the comparator, the change mask and every raster stay visible underneath.
 *   It is the analysis default and stays the default. NOTHING about it changed when this was added.
 *
 *   PHOTOREALISTIC is metered per tile, is beautiful, and REPLACES the ground. It carries its own terrain
 *   and texture, so Cesium's guidance is to hide the globe beneath it — which means the operator's T0/T1
 *   rasters and the before/after split have nothing left to draw on. Draped vector evidence survives only
 *   because the layer set is switched to classify onto 3D tiles as well as terrain.
 *
 * Reached through `createGooglePhotorealistic3DTileset`, the documented API, which needs a Google Maps
 * key with the Map Tiles API enabled.
 *
 * The other route is Cesium Ion asset 2275207 via `Cesium3DTileset.fromIonAssetId`, which would reuse the
 * existing Ion token and need no second key. It is recorded here because it is the obvious thing to reach
 * for — and because it does NOT work as of Cesium 1.144: the asset is an external one, and the promise
 * neither resolves nor rejects, issuing no request at all. Measured, not assumed. Do not spend an
 * afternoon rediscovering it.
 */
const PHOTOREALISTIC_ION_ASSET_ID = 2275207;

/** Whether the photorealistic mode can be offered at all, so the control can say why when it cannot. */
export function hasPhotorealisticAccess(): boolean {
  return googleMapsApiKey.length > 0;
}

export async function createPhotorealisticTileset(): Promise<Cesium3DTileset | null> {
  if (!hasPhotorealisticAccess()) {
    return null;
  }

  try {
    // Created only when the mode actually selects it — every tile it fetches is billed.
    return await createGooglePhotorealistic3DTileset({ key: googleMapsApiKey });
  } catch (error) {
    console.warn(
      `[AERIS] Photorealistic 3D Tiles unavailable. The Ion route (asset ${PHOTOREALISTIC_ION_ASSET_ID}) is the documented alternative.`,
      error,
    );
    return null;
  }
}
