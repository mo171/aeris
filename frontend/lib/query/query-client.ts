// lib/query/query-client.ts — TanStack Query defaults tuned for AERIS's data profile.
//
// what  : Builds the QueryClient with cache, retry and refetch policy.
// where : Instantiated once per browser session by lib/providers/query-provider.tsx.
// how   : Two rules from the architecture context drive this configuration: near-static data (model
//         registry, sensor definitions) must never be refetched on a whim, and client errors must not be
//         retried. Per-query staleTime overrides are set at the hook level where the data profile differs.

import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/axios/api-error";

const DEFAULT_STALE_TIME_MS = 30_000;
const DEFAULT_GARBAGE_COLLECT_TIME_MS = 5 * 60_000;
const MAX_RETRY_ATTEMPTS = 2;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: DEFAULT_STALE_TIME_MS,
        gcTime: DEFAULT_GARBAGE_COLLECT_TIME_MS,
        // Refetching on every window focus is noise for an analyst who alt-tabs constantly.
        refetchOnWindowFocus: false,
        refetchOnReconnect: true,
        retry: (failureCount, error) => {
          if (error instanceof ApiError && !error.isRetryable) {
            return false;
          }
          return failureCount < MAX_RETRY_ATTEMPTS;
        },
        retryDelay: (attemptIndex) => Math.min(1_000 * 2 ** attemptIndex, 8_000),
      },
      mutations: {
        retry: false,
      },
    },
  });
}
