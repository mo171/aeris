// mock/data/imagery.data.ts — generates the mock satellite scene catalogue.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : Builds a large, deterministic catalogue of ImageryScene records and serves cursor-paginated,
//         optionally search-filtered slices of it.
// where : Used by the imagery routes in mock/transport/routes.ts.
// how   : The catalogue is generated once, lazily, and cached at module scope — regenerating thousands of
//         records per request would measure the generator instead of the UI. Size comes from
//         NEXT_PUBLIC_MOCK_SCENE_COUNT so the virtualised list can be stress-tested by changing one
//         environment variable rather than by editing code.

import { env } from "@/lib/env";
import type { ImageryScene } from "@/features/missionCommand/types/imagery.types";

import {
  createSeededRandom,
  pickOne,
  pickWeighted,
  randomFloat,
  randomInteger,
} from "../transport/deterministic-random";
import {
  MOCK_AREAS,
  MOCK_COORDINATE_SYSTEMS,
  MOCK_SENSOR_PLATFORMS,
} from "./geography";

const CATALOGUE_SEED = 20260826;
const REFERENCE_TIME_MS = Date.parse("2026-08-26T09:00:00.000Z");
const ONE_HOUR_MS = 3_600_000;

let cachedCatalogue: ImageryScene[] | null = null;

export function getImageryCatalogue(): ImageryScene[] {
  if (!cachedCatalogue) {
    cachedCatalogue = generateImageryCatalogue(env.NEXT_PUBLIC_MOCK_SCENE_COUNT);
  }
  return cachedCatalogue;
}

function generateImageryCatalogue(sceneCount: number): ImageryScene[] {
  const random = createSeededRandom(CATALOGUE_SEED);
  const scenes: ImageryScene[] = [];

  for (let index = 0; index < sceneCount; index += 1) {
    const area = pickOne(random, MOCK_AREAS);
    const modality = pickWeighted(random, [
      { value: "optical" as const, weight: 52 },
      { value: "sar" as const, weight: 24 },
      { value: "multispectral" as const, weight: 20 },
      { value: "hyperspectral" as const, weight: 4 },
    ]);

    const capturedAtMs = REFERENCE_TIME_MS - randomInteger(random, 1, 24 * 400) * ONE_HOUR_MS;
    const ingestedAtMs = capturedAtMs + randomInteger(random, 1, 72) * ONE_HOUR_MS;
    const latitude = clampLatitude(area.latitude + randomFloat(random, -0.55, 0.55));
    const longitude = wrapLongitude(area.longitude + randomFloat(random, -0.55, 0.55));
    const halfSpanDegrees = randomFloat(random, 0.08, 0.42);

    scenes.push({
      id: `scn_${(index + 1).toString().padStart(6, "0")}`,
      name: `${area.name} · ${formatSceneDate(capturedAtMs)}`,
      capturedAt: new Date(capturedAtMs).toISOString(),
      ingestedAt: new Date(Math.min(ingestedAtMs, REFERENCE_TIME_MS)).toISOString(),
      modality,
      sensorPlatform: pickPlatformForModality(random, modality),
      bandCount: pickBandCount(random, modality),
      groundSampleDistanceMeters: pickGroundSampleDistance(random, modality),
      cloudCoverPercentage:
        modality === "sar" ? null : Math.round(randomFloat(random, 0, 68) * 10) / 10,
      coordinateReferenceSystem: pickOne(random, MOCK_COORDINATE_SYSTEMS),
      boundingBox: {
        west: wrapLongitude(longitude - halfSpanDegrees),
        east: wrapLongitude(longitude + halfSpanDegrees),
        south: clampLatitude(latitude - halfSpanDegrees),
        north: clampLatitude(latitude + halfSpanDegrees),
      },
      centroid: { latitude, longitude },
      fileSizeBytes: randomInteger(random, 42, 4_800) * 1_048_576,
      processingState: pickWeighted(random, [
        { value: "ready" as const, weight: 88 },
        { value: "processing" as const, weight: 6 },
        { value: "queued" as const, weight: 4 },
        { value: "failed" as const, weight: 2 },
      ]),
      temporalRole: pickWeighted(random, [
        { value: "single" as const, weight: 70 },
        { value: "t0" as const, weight: 15 },
        { value: "t1" as const, weight: 15 },
      ]),
      thumbnailUrl: null,
    });
  }

  // Newest first — the operator cares about recent acquisitions.
  scenes.sort((left, right) => Date.parse(right.capturedAt) - Date.parse(left.capturedAt));
  return scenes;
}

export interface ImageryQuery {
  cursor: string | null;
  limit: number;
  search: string | null;
}

export function selectImageryPage(query: ImageryQuery) {
  const catalogue = getImageryCatalogue();
  const searchTerm = query.search?.toLowerCase().trim() ?? "";

  const matching =
    searchTerm.length > 0
      ? catalogue.filter(
          (scene) =>
            scene.name.toLowerCase().includes(searchTerm) ||
            scene.sensorPlatform.toLowerCase().includes(searchTerm) ||
            scene.modality.includes(searchTerm),
        )
      : catalogue;

  const startIndex = query.cursor ? Number.parseInt(query.cursor, 10) : 0;
  const safeStartIndex = Number.isFinite(startIndex) && startIndex > 0 ? startIndex : 0;
  const endIndex = Math.min(safeStartIndex + query.limit, matching.length);

  return {
    items: matching.slice(safeStartIndex, endIndex),
    nextCursor: endIndex < matching.length ? String(endIndex) : null,
    totalCount: matching.length,
  };
}

/** Prepends a freshly uploaded scene so the catalogue reacts to uploads like the real one will. */
export function insertUploadedScene(scene: ImageryScene): void {
  getImageryCatalogue().unshift(scene);
}

function pickPlatformForModality(random: () => number, modality: ImageryScene["modality"]): string {
  if (modality === "sar") {
    return pickOne(random, ["Sentinel-1A", "Sentinel-1B", "RISAT-2B", "TerraSAR-X"]);
  }
  return pickOne(random, MOCK_SENSOR_PLATFORMS);
}

function pickBandCount(random: () => number, modality: ImageryScene["modality"]): number {
  switch (modality) {
    case "sar":
      return randomInteger(random, 1, 2);
    case "multispectral":
      return randomInteger(random, 8, 13);
    case "hyperspectral":
      return randomInteger(random, 120, 224);
    default:
      return randomInteger(random, 3, 4);
  }
}

function pickGroundSampleDistance(random: () => number, modality: ImageryScene["modality"]): number {
  switch (modality) {
    case "sar":
      return pickOne(random, [5, 10, 20]);
    case "hyperspectral":
      return pickOne(random, [30, 60]);
    default:
      return pickOne(random, [0.3, 0.5, 1.5, 3, 10, 30]);
  }
}

function formatSceneDate(timestampMs: number): string {
  return new Date(timestampMs).toISOString().slice(0, 10);
}

function clampLatitude(latitude: number): number {
  return Math.max(-89.9, Math.min(89.9, latitude));
}

function wrapLongitude(longitude: number): number {
  return ((((longitude + 180) % 360) + 360) % 360) - 180;
}
