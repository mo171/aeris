// lib/constants/query-keys.ts — every TanStack Query cache key, built by factories.
//
// what  : Hierarchical query-key factories so related caches can be invalidated as a group.
// where : Used by feature hooks for useQuery/useInfiniteQuery and by mutations for invalidation.
// how   : Each domain exposes an `all` root plus narrower builders. Invalidating QUERY_KEYS.imagery.all
//         drops every imagery cache regardless of filters — that is why the root must stay the prefix of
//         every child key.

export const QUERY_KEYS = {
  imagery: {
    all: ["imagery"] as const,
    catalog: (search: string) => ["imagery", "catalog", search] as const,
    detail: (sceneId: string) => ["imagery", "detail", sceneId] as const,
  },
  missions: {
    all: ["missions"] as const,
    active: () => ["missions", "active"] as const,
    detail: (missionId: string) => ["missions", "detail", missionId] as const,
  },
  globe: {
    all: ["globe"] as const,
    markers: () => ["globe", "markers"] as const,
    satelliteTracks: () => ["globe", "satellite-tracks"] as const,
  },
  models: {
    all: ["models"] as const,
    status: () => ["models", "status"] as const,
  },
  assistant: {
    all: ["assistant"] as const,
    suggestions: () => ["assistant", "suggestions"] as const,
    history: (sessionId: string) => ["assistant", "history", sessionId] as const,
  },
} as const;
