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

import {
  attachScene,
  fetchInvestigation,
  saveCameraBookmark,
} from "../services/investigation.service";
import { useInvestigationStore } from "../store/investigation-store";
import type { CameraBookmark, Investigation, SceneRole } from "../types/investigation.types";

interface UseInvestigationResult {
  investigation: Investigation | undefined;
  isLoading: boolean;
  error: Error | null;
  /** Binds an acquisition into a comparison role. Used by the pop-out windows and the acquisition list. */
  assignSceneRole: (sceneId: string, role: SceneRole) => void;
  /** Persists the current camera pose so the investigation's link reopens this exact framing. */
  saveCameraView: (bookmark: CameraBookmark) => void;
  isSavingCameraView: boolean;
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

  /**
   * Persists the current camera pose against the investigation.
   *
   * Written on an explicit save, never on camera movement: the camera changes every frame and mirroring
   * that to the backend would be thousands of requests a session. The cached record is patched optimistically
   * so the header can confirm the view was saved without waiting for a round trip it does not need.
   */
  const { mutate: mutateBookmark, isPending: isSavingBookmark } = useMutation({
    mutationFn: (bookmark: CameraBookmark) => saveCameraBookmark(investigationId, bookmark),
    onSuccess: (_result, bookmark) =>
      queryClient.setQueryData<Investigation>(
        QUERY_KEYS.investigations.detail(investigationId),
        (current) => (current ? { ...current, cameraBookmark: bookmark } : current),
      ),
  });

  return {
    investigation: data,
    isLoading,
    error: error as Error | null,
    assignSceneRole: useCallback(
      (sceneId: string, role: SceneRole) => mutate({ sceneId, role }),
      [mutate],
    ),
    saveCameraView: useCallback(
      (bookmark: CameraBookmark) => mutateBookmark(bookmark),
      [mutateBookmark],
    ),
    isSavingCameraView: isSavingBookmark,
  };
}
