// features/investigation/hooks/use-region-selection.ts — "ask this region".
//
// what  : Exposes the drawn region, arms and cancels the draw tool, and fetches the questions worth
//         asking about whatever the operator outlined.
// where : Consumed by the region prompt popover and the viewer tool cluster.
// how   : Suggestions are backend-driven, exactly as they are on Mission Command. What is worth asking
//         about a polygon depends on which imagery covers it and what has already been analysed there,
//         and the browser knows neither.
//
//         The query key includes the rounded bounds so nudging the box by a pixel does not refetch, while
//         drawing somewhere genuinely different does. Six decimal places is roughly a tenth of a metre —
//         far below the resolution of any sensor this system ingests.

"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";

import { QUERY_KEYS } from "@/lib/constants/query-keys";

import { fetchRegionSuggestions } from "../services/analysis.service";
import { useInvestigationStore } from "../store/investigation-store";
import type { RegionSuggestion } from "../types/analysis.types";

const SUGGESTIONS_STALE_TIME_MS = 5 * 60_000;

interface RegionSelectionResult {
  region: ReturnType<typeof useInvestigationStore.getState>["drawnRegion"];
  isArmed: boolean;
  suggestions: RegionSuggestion[];
  isLoadingSuggestions: boolean;
  beginDraw: () => void;
  cancelDraw: () => void;
  clearRegion: () => void;
}

export function useRegionSelection(investigationId: string): RegionSelectionResult {
  const region = useInvestigationStore((state) => state.drawnRegion);
  const isArmed = useInvestigationStore((state) => state.isRegionDrawArmed);
  const setRegionDrawArmed = useInvestigationStore((state) => state.setRegionDrawArmed);
  const setDrawnRegion = useInvestigationStore((state) => state.setDrawnRegion);

  const geometryKey = region ? buildGeometryKey(region.bounds) : "";

  const { data, isLoading } = useQuery({
    queryKey: QUERY_KEYS.regions.suggestions(investigationId, geometryKey),
    queryFn: ({ signal }) => fetchRegionSuggestions(investigationId, region!.bounds, signal),
    enabled: region !== null,
    staleTime: SUGGESTIONS_STALE_TIME_MS,
  });

  return {
    region,
    isArmed,
    suggestions: data ?? [],
    isLoadingSuggestions: isLoading,
    beginDraw: useCallback(() => setRegionDrawArmed(true), [setRegionDrawArmed]),
    cancelDraw: useCallback(() => setRegionDrawArmed(false), [setRegionDrawArmed]),
    clearRegion: useCallback(() => setDrawnRegion(null), [setDrawnRegion]),
  };
}

function buildGeometryKey(bounds: {
  west: number;
  south: number;
  east: number;
  north: number;
}): string {
  return [bounds.west, bounds.south, bounds.east, bounds.north]
    .map((value) => value.toFixed(6))
    .join(",");
}
