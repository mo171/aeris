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

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect } from "react";

import { QUERY_KEYS } from "@/lib/constants/query-keys";

import { attachScene, fetchInvestigation } from "../services/investigation.service";
import { useInvestigationStore } from "../store/investigation-store";
import type { Investigation, SceneRole } from "../types/investigation.types";

interface UseInvestigationResult {
  investigation: Investigation | undefined;
  isLoading: boolean;
  error: Error | null;
  /** Binds an acquisition into a comparison role. Used by the pop-out windows and the acquisition list. */
  assignSceneRole: (sceneId: string, role: SceneRole) => void;
}

export function useInvestigation(investigationId: string): UseInvestigationResult {
  const queryClient = useQueryClient();
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

  const { mutate } = useMutation({
    mutationFn: ({ sceneId, role }: { sceneId: string; role: SceneRole }) =>
      attachScene(investigationId, sceneId, role),
    // The response IS the updated record, so it replaces the cache directly. Invalidating instead would
    // leave a window where the layer stack and the comparator disagree about which scene is T1.
    onSuccess: (updated) =>
      queryClient.setQueryData(QUERY_KEYS.investigations.detail(investigationId), updated),
  });

  return {
    investigation: data,
    isLoading,
    error: error as Error | null,
    assignSceneRole: useCallback(
      (sceneId: string, role: SceneRole) => mutate({ sceneId, role }),
      [mutate],
    ),
  };
}
