// features/missionCommand/hooks/use-active-missions.ts — the operator's mission list.
//
// what  : Paginated access to missions, ordered by the backend with alerts first.
// where : Consumed by ActiveMissionsList in the data panel.
// how   : Missions change on a slower cadence than imagery, so the stale time is longer. Ordering is the
//         backend's job, not the client's — sorting here would fight the server's ordering as pages
//         arrive and make rows jump between pages during a scroll.

"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { QUERY_KEYS } from "@/lib/constants/query-keys";

import { fetchMissionPage, MISSION_PAGE_SIZE } from "../services/mission.service";
import type { Mission } from "../types/mission.types";

const MISSION_STALE_TIME_MS = 60_000;

interface ActiveMissionsResult {
  missions: Mission[];
  totalCount: number | null;
  isLoading: boolean;
  isFetchingNextPage: boolean;
  hasNextPage: boolean;
  fetchNextPage: () => void;
  error: unknown;
  refetch: () => void;
}

export function useActiveMissions(): ActiveMissionsResult {
  const query = useInfiniteQuery({
    queryKey: QUERY_KEYS.missions.active(),
    queryFn: ({ pageParam, signal }) =>
      fetchMissionPage({ cursor: pageParam, limit: MISSION_PAGE_SIZE }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    staleTime: MISSION_STALE_TIME_MS,
  });

  const missions = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );

  return {
    missions,
    totalCount: query.data?.pages[0]?.totalCount ?? null,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: query.hasNextPage,
    fetchNextPage: () => {
      if (query.hasNextPage && !query.isFetchingNextPage) {
        void query.fetchNextPage();
      }
    },
    error: query.error,
    refetch: () => void query.refetch(),
  };
}
