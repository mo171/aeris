// features/missionCommand/hooks/use-land-dots.ts — builds the globe's land point cloud, once.
//
// what  : Loads the land outline and converts it into a Float32Array of sphere-surface positions.
// where : Consumed by the EarthLandDots layer.
// how   : Both steps are expensive and neither depends on anything that changes: the fetch is cached by
//         TanStack Query with an infinite stale time, and the rasterise-and-sample step is memoised on the
//         geometry reference. The result is that the globe pays this cost once per session — on a route
//         change back to Mission Command it is already in the cache and the globe appears immediately.

"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { GLOBE_RADIUS, LAND_DOT_SAMPLING } from "@/lib/constants/globe";

import { fetchLandGeometry } from "../services/globe-assets.service";
import { buildLandDotPositions } from "../components/globe/globe-geometry";

const LAND_GEOMETRY_QUERY_KEY = ["globe", "land-geometry"] as const;

export function useLandDots(): { positions: Float32Array | null; isLoading: boolean } {
  const { data: landGeometry, isLoading } = useQuery({
    queryKey: LAND_GEOMETRY_QUERY_KEY,
    queryFn: ({ signal }) => fetchLandGeometry(signal),
    // The coastline of the Earth is not going to change during a session.
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });

  const positions = useMemo(() => {
    if (!landGeometry) {
      return null;
    }
    return buildLandDotPositions(
      landGeometry,
      GLOBE_RADIUS + LAND_DOT_SAMPLING.surfaceOffset,
    );
  }, [landGeometry]);

  return { positions, isLoading };
}
