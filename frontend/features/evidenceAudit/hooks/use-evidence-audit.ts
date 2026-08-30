// features/evidenceAudit/hooks/use-evidence-audit.ts — the claim corpus, filtered.
//
// what  : Holds the auditor's filter state and fetches the matching page of claims, paginating as they
//         scroll.
// where : Called once by EvidenceAuditScreen.
// how   : Filter state lives here rather than in a store because nothing outside this surface reads it —
//         there is no scene to bind, no command that needs to reach it, and it should not survive leaving
//         the page. That is the same test the investigation store applies before anything is added to it.
//
//         The search term is DEBOUNCED before it reaches the query key. Without it, every keystroke is a
//         new cache entry and a new request against a corpus that grows with every run ever made.

"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { useDebouncedValue } from "@/hooks/use-debounced-value";
import type { ConfidenceBandId } from "@/lib/constants/evidence-audit";
import type { ModelId } from "@/lib/constants/models";
import { QUERY_KEYS } from "@/lib/constants/query-keys";

import { AUDIT_PAGE_SIZE, fetchAuditedClaimPage } from "../services/evidence-audit.service";
import type { AuditedClaim } from "../types/evidence-audit.types";

const SEARCH_DEBOUNCE_MS = 280;

export interface EvidenceAuditView {
  claims: AuditedClaim[];
  totalCount: number | null;
  isLoading: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
  error: unknown;
  refetch: () => void;

  search: string;
  setSearch: (search: string) => void;
  modelId: ModelId | null;
  setModelId: (modelId: ModelId | null) => void;
  band: ConfidenceBandId;
  setBand: (band: ConfidenceBandId) => void;
  /** True when any filter is narrowing the corpus, so the surface can offer to clear them. */
  isFiltered: boolean;
  clearFilters: () => void;
}

export function useEvidenceAudit(): EvidenceAuditView {
  const [search, setSearch] = useState("");
  const [modelId, setModelId] = useState<ModelId | null>(null);
  const [band, setBand] = useState<ConfidenceBandId>("all");

  const debouncedSearch = useDebouncedValue(search, SEARCH_DEBOUNCE_MS);
  const filterKey = `${debouncedSearch}|${modelId ?? ""}|${band}`;

  const query = useInfiniteQuery({
    queryKey: QUERY_KEYS.evidenceAudit.claims(filterKey),
    queryFn: ({ pageParam, signal }) =>
      fetchAuditedClaimPage(
        { search: debouncedSearch, modelId, band, cursor: pageParam, limit: AUDIT_PAGE_SIZE },
        signal,
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  });

  const claims = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );

  return {
    claims,
    totalCount: query.data?.pages[0]?.totalCount ?? null,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    fetchNextPage: () => {
      if (query.hasNextPage && !query.isFetchingNextPage) {
        void query.fetchNextPage();
      }
    },
    error: query.error,
    refetch: () => void query.refetch(),

    search,
    setSearch,
    modelId,
    setModelId,
    band,
    setBand,
    isFiltered: debouncedSearch.length > 0 || modelId !== null || band !== "all",
    clearFilters: () => {
      setSearch("");
      setModelId(null);
      setBand("all");
    },
  };
}
