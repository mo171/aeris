// features/missionCommand/hooks/use-model-status.ts — health of the specialist model fleet.
//
// what  : Fetches model registry status and derives the fleet-level summary shown in the data panel.
// where : Consumed by ModelStatusStrip.
// how   : Near-static data with a long stale time and no refetch on focus, per the caching rules in the
//         architecture context — model versions change on deploys, not on window focus. A slow poll keeps
//         health roughly current without the panel becoming a request generator; in Phase 2 this becomes a
//         WebSocket push and the interval goes away.

"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { QUERY_KEYS } from "@/lib/constants/query-keys";

import { fetchModelStatus } from "../services/model-registry.service";
import type { ModelStatus } from "../types/model.types";

const MODEL_STATUS_STALE_TIME_MS = 5 * 60_000;
const MODEL_STATUS_POLL_INTERVAL_MS = 2 * 60_000;

interface ModelStatusResult {
  models: ModelStatus[];
  onlineCount: number;
  degradedCount: number;
  offlineCount: number;
  isLoading: boolean;
  error: unknown;
  refetch: () => void;
}

export function useModelStatus(): ModelStatusResult {
  const query = useQuery({
    queryKey: QUERY_KEYS.models.status(),
    queryFn: ({ signal }) => fetchModelStatus(signal),
    staleTime: MODEL_STATUS_STALE_TIME_MS,
    refetchInterval: MODEL_STATUS_POLL_INTERVAL_MS,
  });

  const models = useMemo(() => query.data?.models ?? [], [query.data]);

  const counts = useMemo(
    () => ({
      onlineCount: models.filter((model) => model.health === "online").length,
      degradedCount: models.filter(
        (model) => model.health === "degraded" || model.health === "warming",
      ).length,
      offlineCount: models.filter((model) => model.health === "offline").length,
    }),
    [models],
  );

  return {
    models,
    ...counts,
    isLoading: query.isLoading,
    error: query.error,
    refetch: () => void query.refetch(),
  };
}
