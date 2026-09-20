"use client";

import { useQuery } from "@tanstack/react-query";

import { QUERY_KEYS } from "@/lib/constants/query-keys";
import { fetchProjectInvestigations } from "../services/investigation.service";
import type { InvestigationSummary } from "../types/investigation.types";

export function useProjectInvestigations(projectId: string) {
  return useQuery<InvestigationSummary[], Error>({
    queryKey: QUERY_KEYS.investigations.byProject(projectId),
    queryFn: ({ signal }) => fetchProjectInvestigations(projectId, signal),
    enabled: Boolean(projectId),
  });
}
