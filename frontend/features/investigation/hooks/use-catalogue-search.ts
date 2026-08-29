// features/investigation/hooks/use-catalogue-search.ts — asking the archive for a different window.
//
// what  : Runs the temporal catalogue query, folds the returned acquisitions into the cached
//         investigation, and keeps the coverage holes and the recommended pair for the timeline to show.
// where : Called by InvestigationScreen and handed to the timeline's filter controls.
// how   : A mutation rather than a query, because the operator asks for a window — it is an action with a
//         moment, not a value that should refetch on focus. Nobody wants the timeline to rearrange itself
//         because they alt-tabbed back.
//
//         The result is merged into the existing investigation cache rather than replacing the record.
//         The acquisitions change; the area of interest, the scene slots, the trace id and everything
//         hanging off them do not, and refetching the whole investigation to learn about new dates would
//         throw away state the operator is in the middle of using.
//
//         The recommended pair is NOT applied. The catalogue can see the archive and the operator can see
//         the question; a backend that silently reassigned the comparison would be answering something
//         nobody asked. It is offered, and stays offered until it is taken or the window changes.

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { QUERY_KEYS } from "@/lib/constants/query-keys";

import { searchCatalogue } from "../services/catalogue.service";
import type {
  CatalogueSearchResponse,
  CoverageGap,
  PairRecommendation,
  TemporalQuery,
} from "../types/catalogue.types";
import type { Investigation } from "../types/investigation.types";

interface CatalogueSearchControls {
  search: (query: TemporalQuery) => void;
  isSearching: boolean;
  error: Error | null;
  /** Holes the backend reported in the requested window. Distinct from the ones derived on the client. */
  coverageGaps: CoverageGap[];
  recommendation: PairRecommendation | null;
  advisory: string | null;
  dismissRecommendation: () => void;
}

export function useCatalogueSearch(investigationId: string): CatalogueSearchControls {
  const queryClient = useQueryClient();
  const [result, setResult] = useState<CatalogueSearchResponse | null>(null);
  const [isRecommendationDismissed, setRecommendationDismissed] = useState(false);

  const mutation = useMutation({
    mutationFn: (query: TemporalQuery) => searchCatalogue(query),
    onSuccess: (response) => {
      setResult(response);
      setRecommendationDismissed(false);

      queryClient.setQueryData<Investigation>(
        QUERY_KEYS.investigations.detail(investigationId),
        (current) =>
          current ? { ...current, acquisitions: response.acquisitions } : current,
      );

      // Cached under the query itself as well, so re-running the same window is free and the coverage
      // report stays inspectable without a second request.
      queryClient.setQueryData(
        QUERY_KEYS.catalogue.search(serialiseQuery(response.query)),
        response,
      );
    },
  });

  return {
    search: mutation.mutate,
    isSearching: mutation.isPending,
    error: (mutation.error as Error | null) ?? null,
    coverageGaps: result?.coverageGaps ?? [],
    recommendation: isRecommendationDismissed ? null : (result?.recommendedPair ?? null),
    advisory: result?.advisory ?? null,
    dismissRecommendation: () => setRecommendationDismissed(true),
  };
}

/** Stable cache key for one window over one area. Field order is fixed so two equal queries agree. */
function serialiseQuery(query: TemporalQuery): string {
  const { areaOfInterest, from, to, modalities, maximumCloudPercentage } = query;
  return [
    areaOfInterest.west,
    areaOfInterest.south,
    areaOfInterest.east,
    areaOfInterest.north,
    from,
    to,
    [...modalities].sort().join("+"),
    maximumCloudPercentage,
  ].join("|");
}
