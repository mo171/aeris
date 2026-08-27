// features/investigation/hooks/use-investigation.ts — loads one investigation and scopes the workspace to it.
//
// what  : Fetches the investigation record, tells the feature store which investigation is open, and
//         clears that scope on unmount.
// where : Called once by InvestigationScreen. Everything else reads the record from this hook or the id
//         from the store.
// how   : The record is server state, so it lives in the query cache rather than the store. What goes in
//         the store is only the ID and the comparator binding, because those are what the commands and
//         the stage binding need to reach from outside React.
//
//         Entering resets the workspace view state deliberately: carrying one investigation hidden layers
//         and spotlight into the next would make the surface feel haunted.

"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { QUERY_KEYS } from "@/lib/constants/query-keys";

import { fetchInvestigation } from "../services/investigation.service";
import { useInvestigationStore } from "../store/investigation-store";
import type { Investigation } from "../types/investigation.types";

interface UseInvestigationResult {
  investigation: Investigation | undefined;
  isLoading: boolean;
  error: Error | null;
}

export function useInvestigation(investigationId: string): UseInvestigationResult {
  const enterInvestigation = useInvestigationStore((state) => state.enterInvestigation);
  const leaveInvestigation = useInvestigationStore((state) => state.leaveInvestigation);

  const { data, isLoading, error } = useQuery({
    queryKey: QUERY_KEYS.investigations.detail(investigationId),
    queryFn: ({ signal }) => fetchInvestigation(investigationId, signal),
  });

  const mode = data?.mode;

  useEffect(() => {
    if (!mode) {
      return;
    }
    enterInvestigation(investigationId, mode);
  }, [enterInvestigation, investigationId, mode]);

  useEffect(() => {
    return () => {
      leaveInvestigation();
    };
  }, [leaveInvestigation]);

  return { investigation: data, isLoading, error: error as Error | null };
}
