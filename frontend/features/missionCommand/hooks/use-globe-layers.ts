// features/missionCommand/hooks/use-globe-layers.ts — server data for the globe's marker and arc layers.
//
// what  : Fetches the globe marker feed and the ambient satellite tracks.
// where : Consumed by GlobeScene.
// how   : Both feeds are whole collections rather than pages, because the renderer uploads all of them to
//         the GPU in one buffer — a paginated marker feed would mean rebuilding that buffer per page.
//         Markers carry a moderate stale time so a route change back to Mission Command reuses the cache
//         instead of re-uploading thousands of points; satellite tracks are ambient decoration and are
//         allowed to go stale for much longer.

"use client";

import { useQuery } from "@tanstack/react-query";

import { QUERY_KEYS } from "@/lib/constants/query-keys";

import { fetchGlobeMarkers, fetchSatelliteTracks } from "../services/mission.service";
import type { GlobeMarker, SatelliteTrack } from "../types/globe.types";

const MARKER_STALE_TIME_MS = 60_000;
const SATELLITE_TRACK_STALE_TIME_MS = 5 * 60_000;

interface GlobeLayersResult {
  markers: GlobeMarker[];
  satelliteTracks: SatelliteTrack[];
  isLoading: boolean;
  error: unknown;
  refetch: () => void;
}

export function useGlobeLayers(): GlobeLayersResult {
  const markersQuery = useQuery({
    queryKey: QUERY_KEYS.globe.markers(),
    queryFn: ({ signal }) => fetchGlobeMarkers(signal),
    staleTime: MARKER_STALE_TIME_MS,
  });

  const satelliteTracksQuery = useQuery({
    queryKey: QUERY_KEYS.globe.satelliteTracks(),
    queryFn: ({ signal }) => fetchSatelliteTracks(signal),
    staleTime: SATELLITE_TRACK_STALE_TIME_MS,
  });

  return {
    markers: markersQuery.data ?? [],
    satelliteTracks: satelliteTracksQuery.data ?? [],
    isLoading: markersQuery.isLoading,
    // Only a marker failure is worth surfacing; ambient arcs failing must not blank the globe.
    error: markersQuery.error,
    refetch: () => {
      void markersQuery.refetch();
      void satelliteTracksQuery.refetch();
    },
  };
}
