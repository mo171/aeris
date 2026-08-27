// features/investigation/hooks/use-region-selection.ts — drawn regions, the active scope, and "ask this region".
//
// what  : Exposes every committed region, which one currently scopes questions, the draw and measure
//         tools, and the backend's suggested questions for the active shape.
// where : Consumed by the draw toolbar, the region list and the region prompt.
// how   : Several regions can exist at once because an analyst comparing two sites needs both on screen.
//         Exactly one is ACTIVE, and only that one scopes the next question — an interface where every
//         drawn shape silently contributes to the query is one where the operator cannot tell what they
//         actually asked.
//
//         Suggestions are backend-driven, as they are on Mission Command. What is worth asking about a
//         polygon depends on which imagery covers it and what has already been analysed there, and the
//         browser knows neither.
//
//         The query key rounds the bounds to six decimals — roughly a tenth of a metre, far below any
//         sensor this system ingests — so nudging a shape does not refetch while drawing somewhere
//         genuinely different does.

"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";

import type { StageDrawTool } from "@/components/sharedUI/functionalComponent/geoStage/geo-stage.types";
import { QUERY_KEYS } from "@/lib/constants/query-keys";
import { useGeoStageStore } from "@/store/geo-stage-store";

import { fetchRegionSuggestions } from "../services/analysis.service";
import { useInvestigationStore } from "../store/investigation-store";
import type { RegionSuggestion } from "../types/analysis.types";

const SUGGESTIONS_STALE_TIME_MS = 5 * 60_000;

interface RegionSelectionResult {
  regions: ReturnType<typeof useInvestigationStore.getState>["drawnRegions"];
  activeRegion: ReturnType<typeof useInvestigationStore.getState>["drawnRegions"][number] | null;
  activeTool: StageDrawTool | null;
  suggestions: RegionSuggestion[];
  isLoadingSuggestions: boolean;
  selectTool: (tool: StageDrawTool | null) => void;
  setActiveRegion: (regionId: string | null) => void;
  removeRegion: (regionId: string) => void;
  clearAll: () => void;
}

export function useRegionSelection(investigationId: string): RegionSelectionResult {
  const regions = useInvestigationStore((state) => state.drawnRegions);
  const activeRegionId = useInvestigationStore((state) => state.activeRegionId);
  const activeTool = useInvestigationStore((state) => state.activeDrawTool);
  const setActiveDrawTool = useInvestigationStore((state) => state.setActiveDrawTool);
  const setActiveRegionId = useInvestigationStore((state) => state.setActiveRegionId);

  const activeRegion = regions.find((region) => region.id === activeRegionId) ?? null;
  const geometryKey = activeRegion ? buildGeometryKey(activeRegion.bounds) : "";

  const { data, isLoading } = useQuery({
    queryKey: QUERY_KEYS.regions.suggestions(investigationId, geometryKey),
    queryFn: ({ signal }) =>
      fetchRegionSuggestions(investigationId, activeRegion!.bounds, signal),
    enabled: activeRegion !== null,
    staleTime: SUGGESTIONS_STALE_TIME_MS,
  });

  const removeRegion = useCallback((regionId: string) => {
    // Removed on the stage, which then republishes the list — so the scene and the store can never
    // disagree about what has been drawn.
    useGeoStageStore.getState().handle?.draw.removeRegion(regionId);
  }, []);

  const clearAll = useCallback(() => {
    useGeoStageStore.getState().handle?.draw.clearAll();
  }, []);

  return {
    regions,
    activeRegion,
    activeTool,
    suggestions: data ?? [],
    isLoadingSuggestions: isLoading,
    selectTool: useCallback(
      // Pressing the armed tool again disarms it, so the same button both enters and leaves the mode.
      (tool: StageDrawTool | null) =>
        setActiveDrawTool(tool === useInvestigationStore.getState().activeDrawTool ? null : tool),
      [setActiveDrawTool],
    ),
    setActiveRegion: setActiveRegionId,
    removeRegion,
    clearAll,
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
