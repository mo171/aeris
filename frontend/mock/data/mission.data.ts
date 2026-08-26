// mock/data/mission.data.ts — generates mock missions, globe markers and ambient satellite tracks.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : Deterministic mission records, a marker feed sized from the environment, and great-circle
//         satellite tracks between real ground stations.
// where : Used by the mission and globe routes in mock/transport/routes.ts.
// how   : Marker count comes from NEXT_PUBLIC_MOCK_MARKER_COUNT so the instanced renderer can be pushed to
//         thousands of points without touching code. Markers cluster around the real AOIs in
//         mock/data/geography.ts rather than scattering uniformly, because uniform scatter puts most
//         points in the ocean and would make the clustering path look better than it really is.

import { env } from "@/lib/env";
import type { GlobeMarker, SatelliteTrack } from "@/features/missionCommand/types/globe.types";
import type { Mission, MissionStatus } from "@/features/missionCommand/types/mission.types";

import {
  createSeededRandom,
  pickOne,
  pickWeighted,
  randomFloat,
  randomInteger,
} from "../transport/deterministic-random";
import { MOCK_AREAS, MOCK_SENSOR_PLATFORMS } from "./geography";

const MISSION_SEED = 771026;
const MARKER_SEED = 4410882;
const TRACK_SEED = 99117;
const REFERENCE_TIME_MS = Date.parse("2026-08-26T09:00:00.000Z");
const ONE_HOUR_MS = 3_600_000;
const MISSION_COUNT = 180;
const SATELLITE_TRACK_COUNT = 14;

let cachedMissions: Mission[] | null = null;
let cachedMarkers: GlobeMarker[] | null = null;
let cachedTracks: SatelliteTrack[] | null = null;

const MISSION_SUMMARIES: Record<Mission["analysisKind"], string> = {
  "change-detection": "Bi-temporal built-up change tracked against the last verified baseline.",
  "vegetation-health": "NDVI trend monitored across the growing season with stress flagging.",
  "urban-growth": "Settlement footprint expansion measured quarter over quarter.",
  "flood-mapping": "Water extent delineated from SAR backscatter, cloud independent.",
  "cross-modal": "Optical and SAR evidence fused; conclusions require agreement from both sensors.",
};

export function getMissions(): Mission[] {
  if (!cachedMissions) {
    cachedMissions = generateMissions();
  }
  return cachedMissions;
}

function generateMissions(): Mission[] {
  const random = createSeededRandom(MISSION_SEED);
  const missions: Mission[] = [];

  for (let index = 0; index < MISSION_COUNT; index += 1) {
    const area = pickOne(random, MOCK_AREAS);
    const analysisKind = pickOne(random, [
      "change-detection",
      "vegetation-health",
      "urban-growth",
      "flood-mapping",
      "cross-modal",
    ] as const);
    const status = pickWeighted(random, [
      { value: "monitoring" as const, weight: 44 },
      { value: "active" as const, weight: 30 },
      { value: "alert" as const, weight: 12 },
      { value: "archived" as const, weight: 14 },
    ]);
    const createdAtMs = REFERENCE_TIME_MS - randomInteger(random, 24, 24 * 300) * ONE_HOUR_MS;
    const lastRunAtMs = createdAtMs + randomInteger(random, 1, 200) * ONE_HOUR_MS;
    const hasRun = lastRunAtMs < REFERENCE_TIME_MS && status !== "archived";

    missions.push({
      id: `msn_${(index + 1).toString().padStart(4, "0")}`,
      name: `${area.name} ${formatAnalysisLabel(analysisKind)}`,
      status,
      analysisKind,
      areaOfInterestName: area.name,
      centroid: { latitude: area.latitude, longitude: area.longitude },
      createdAt: new Date(createdAtMs).toISOString(),
      lastRunAt: hasRun ? new Date(lastRunAtMs).toISOString() : null,
      nextRunAt:
        status === "monitoring"
          ? new Date(REFERENCE_TIME_MS + randomInteger(random, 2, 96) * ONE_HOUR_MS).toISOString()
          : null,
      sceneCount: randomInteger(random, 2, 48),
      confidence: hasRun ? Math.round(randomFloat(random, 0.62, 0.98) * 100) / 100 : null,
      openAlertCount: status === "alert" ? randomInteger(random, 1, 6) : 0,
      summary: MISSION_SUMMARIES[analysisKind],
    });
  }

  const statusPriority: Record<MissionStatus, number> = {
    alert: 0,
    active: 1,
    monitoring: 2,
    archived: 3,
  };

  missions.sort((left, right) => {
    const priorityDelta = statusPriority[left.status] - statusPriority[right.status];
    if (priorityDelta !== 0) {
      return priorityDelta;
    }
    return Date.parse(right.createdAt) - Date.parse(left.createdAt);
  });

  return missions;
}

export function selectMissionPage(cursor: string | null, limit: number) {
  const missions = getMissions();
  const parsedCursor = cursor ? Number.parseInt(cursor, 10) : 0;
  const startIndex = Number.isFinite(parsedCursor) && parsedCursor > 0 ? parsedCursor : 0;
  const endIndex = Math.min(startIndex + limit, missions.length);

  return {
    items: missions.slice(startIndex, endIndex),
    nextCursor: endIndex < missions.length ? String(endIndex) : null,
    totalCount: missions.length,
  };
}

export function getGlobeMarkers(): GlobeMarker[] {
  if (!cachedMarkers) {
    cachedMarkers = generateGlobeMarkers(env.NEXT_PUBLIC_MOCK_MARKER_COUNT);
  }
  return cachedMarkers;
}

function generateGlobeMarkers(markerCount: number): GlobeMarker[] {
  const random = createSeededRandom(MARKER_SEED);
  const missions = getMissions();
  const markers: GlobeMarker[] = [];

  for (let index = 0; index < markerCount; index += 1) {
    // The first markers mirror real missions; the remainder are anonymous AOI activity, which is how the
    // production feed behaves — far more observed areas than saved missions.
    const linkedMission = index < missions.length ? missions[index] : null;
    const area = linkedMission
      ? { name: linkedMission.areaOfInterestName, ...linkedMission.centroid }
      : (() => {
          const picked = pickOne(random, MOCK_AREAS);
          return { name: picked.name, latitude: picked.latitude, longitude: picked.longitude };
        })();

    const spread = linkedMission ? 0.35 : 5.5;

    markers.push({
      id: `mkr_${(index + 1).toString().padStart(6, "0")}`,
      missionId: linkedMission?.id ?? null,
      label: linkedMission ? linkedMission.name : `${area.name} observation`,
      position: {
        latitude: clampLatitude(area.latitude + randomFloat(random, -spread, spread)),
        longitude: wrapLongitude(area.longitude + randomFloat(random, -spread, spread)),
      },
      status:
        linkedMission?.status ??
        pickWeighted(random, [
          { value: "monitoring" as const, weight: 52 },
          { value: "active" as const, weight: 28 },
          { value: "alert" as const, weight: 8 },
          { value: "archived" as const, weight: 12 },
        ]),
      magnitude: Math.round(randomFloat(random, 0.15, 1) * 100) / 100,
    });
  }

  return markers;
}

export function getSatelliteTracks(): SatelliteTrack[] {
  if (!cachedTracks) {
    cachedTracks = generateSatelliteTracks();
  }
  return cachedTracks;
}

function generateSatelliteTracks(): SatelliteTrack[] {
  const random = createSeededRandom(TRACK_SEED);
  const tracks: SatelliteTrack[] = [];

  for (let index = 0; index < SATELLITE_TRACK_COUNT; index += 1) {
    const origin = pickOne(random, MOCK_AREAS);
    let destination = pickOne(random, MOCK_AREAS);
    while (destination.name === origin.name) {
      destination = pickOne(random, MOCK_AREAS);
    }

    tracks.push({
      id: `trk_${(index + 1).toString().padStart(3, "0")}`,
      platform: pickOne(random, MOCK_SENSOR_PLATFORMS),
      origin: { latitude: origin.latitude, longitude: origin.longitude },
      destination: { latitude: destination.latitude, longitude: destination.longitude },
      phase: Math.round(random() * 100) / 100,
    });
  }

  return tracks;
}

function formatAnalysisLabel(analysisKind: Mission["analysisKind"]): string {
  switch (analysisKind) {
    case "change-detection":
      return "Change Watch";
    case "vegetation-health":
      return "Vegetation Watch";
    case "urban-growth":
      return "Growth Survey";
    case "flood-mapping":
      return "Flood Watch";
    case "cross-modal":
      return "Dual-Sensor Audit";
  }
}

function clampLatitude(latitude: number): number {
  return Math.max(-84, Math.min(84, latitude));
}

function wrapLongitude(longitude: number): number {
  return ((((longitude + 180) % 360) + 360) % 360) - 180;
}
