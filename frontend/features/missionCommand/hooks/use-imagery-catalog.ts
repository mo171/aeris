// features/missionCommand/hooks/use-imagery-catalog.ts — paginated, searchable access to the scene catalogue.
//
// what  : Exposes a flattened, infinitely-scrolling list of imagery scenes plus the search term that
//         filters it.
// where : Consumed by ImageryCatalogList in the data panel.
// how   : Cursor pagination, not offset. The catalogue is unbounded and receives new scenes continuously,
//         so an offset would silently skip or duplicate rows whenever an ingest lands mid-scroll.
//
//         The search term is debounced before it reaches the query key: keying on every keystroke would
//         create and discard a cache entry per character and fire a request per character. The raw term
//         still drives the input so typing stays instant.

"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { QUERY_KEYS } from "@/lib/constants/query-keys";

import { fetchImageryCatalogPage, IMAGERY_PAGE_SIZE } from "../services/imagery.service";
import { useMissionCommandStore } from "../store/mission-command-store";
import type { ImageryScene } from "../types/imagery.types";

const SEARCH_DEBOUNCE_MS = 280;

interface ImageryCatalogResult {
  scenes: ImageryScene[];
  totalCount: number | null;
  searchTerm: string;
  setSearchTerm: (searchTerm: string) => void;
  isLoading: boolean;
  isFetchingNextPage: boolean;
  hasNextPage: boolean;
  fetchNextPage: () => void;
  error: unknown;
  refetch: () => void;
}

export function useImageryCatalog(): ImageryCatalogResult {
  const searchTerm = useMissionCommandStore((state) => state.catalogSearchTerm);
  const setSearchTerm = useMissionCommandStore((state) => state.setCatalogSearchTerm);
  const debouncedSearchTerm = useDebouncedValue(searchTerm, SEARCH_DEBOUNCE_MS);

  const query = useInfiniteQuery({
    queryKey: QUERY_KEYS.imagery.catalog(debouncedSearchTerm),
    queryFn: ({ pageParam, signal }) =>
      fetchImageryCatalogPage(
        { cursor: pageParam, limit: IMAGERY_PAGE_SIZE, search: debouncedSearchTerm },
        signal,
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  });

  // Flattening is memoised on the page array so scrolling does not rebuild the list on every render.
  const scenes = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );

  return {
    scenes,
    totalCount: query.data?.pages[0]?.totalCount ?? null,
    searchTerm,
    setSearchTerm,
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
