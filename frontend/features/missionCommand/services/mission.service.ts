// features/missionCommand/services/mission.service.ts — backend communication about missions and the globe.
//
// what  : Fetches paginated missions, the globe marker feed, and the ambient satellite tracks.
// where : Called by use-active-missions.ts and use-globe-layers.ts.
// how   : Markers and tracks are fetched as whole collections rather than paginated, because the renderer
//         needs all of them at once to build a single instanced draw call. The payload stays small because
//         the marker schema carries only render-relevant fields — the full mission record is fetched on
//         demand when the operator opens one.

import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";
import type { CursorPageRequest } from "@/lib/types/api.types";

import {
  globeMarkerCollectionSchema,
  missionPageSchema,
  missionSchema,
  satelliteTrackCollectionSchema,
} from "../schemas/mission.schema";
import type { GlobeMarker, SatelliteTrack } from "../types/globe.types";
import type { Mission, MissionCreateRequest, MissionPage } from "../types/mission.types";

export const MISSION_PAGE_SIZE = 20;

export async function fetchMissionPage(
  request: CursorPageRequest,
  signal?: AbortSignal,
): Promise<MissionPage> {
  const response = await apiClient.get(REST_API.missions.list, {
    signal,
    params: {
      cursor: request.cursor ?? undefined,
      limit: request.limit ?? MISSION_PAGE_SIZE,
    },
  });

  return parseApiResponse(missionPageSchema, response.data, "the mission list");
}

/** Saves a finished investigation as a mission over the same area. */
export async function createMission(
  request: MissionCreateRequest,
  signal?: AbortSignal,
): Promise<Mission> {
  const response = await apiClient.post(REST_API.missions.create, request, { signal });

  return parseApiResponse(missionSchema, response.data, "the saved mission");
}

export async function fetchGlobeMarkers(signal?: AbortSignal): Promise<GlobeMarker[]> {
  const response = await apiClient.get(REST_API.globe.markers, { signal });
  const collection = parseApiResponse(
    globeMarkerCollectionSchema,
    response.data,
    "the globe marker feed",
  );

  return collection.markers;
}

export async function fetchSatelliteTracks(signal?: AbortSignal): Promise<SatelliteTrack[]> {
  const response = await apiClient.get(REST_API.globe.satelliteTracks, { signal });
  const collection = parseApiResponse(
    satelliteTrackCollectionSchema,
    response.data,
    "the satellite track feed",
  );

  return collection.tracks;
}
