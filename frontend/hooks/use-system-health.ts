"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/axios/axios-client";
import { REST_API } from "@/lib/constants/rest.api";

export interface DependencyHealth {
  name: string;
  healthy: boolean;
  latencyMs?: number | null;
  error?: string | null;
}

export interface SystemHealthResponse {
  status: "healthy" | "degraded" | "offline";
  dependencies: DependencyHealth[];
}

export function useSystemHealth() {
  return useQuery<SystemHealthResponse>({
    queryKey: ["system-health"],
    queryFn: async () => {
      try {
        const response = await apiClient.get<SystemHealthResponse>(REST_API.health);
        return response.data;
      } catch {
        return {
          status: "offline",
          dependencies: [],
        };
      }
    },
    refetchInterval: 15000,
    staleTime: 10000,
  });
}
