import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CursorPageRequest } from "@/lib/types/api.types";

import { createProject, fetchProject, fetchProjectPage } from "../services/project.service";
import type { ProjectCreateRequest } from "../types/project.types";

export const PROJECT_QUERY_KEYS = {
  all: ["projects"] as const,
  lists: () => [...PROJECT_QUERY_KEYS.all, "list"] as const,
  list: (params: CursorPageRequest) => [...PROJECT_QUERY_KEYS.lists(), params] as const,
  details: () => [...PROJECT_QUERY_KEYS.all, "detail"] as const,
  detail: (id: string) => [...PROJECT_QUERY_KEYS.details(), id] as const,
};

export function useProjects(params: Omit<CursorPageRequest, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: PROJECT_QUERY_KEYS.list(params),
    queryFn: ({ pageParam, signal }) =>
      fetchProjectPage({ ...params, cursor: pageParam as string | undefined }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  });
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: PROJECT_QUERY_KEYS.detail(projectId),
    queryFn: ({ signal }) => fetchProject(projectId, signal),
    enabled: !!projectId,
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: ProjectCreateRequest) => createProject(request),
    onSuccess: (newProject) => {
      queryClient.invalidateQueries({ queryKey: PROJECT_QUERY_KEYS.lists() });
      queryClient.setQueryData(PROJECT_QUERY_KEYS.detail(newProject.id), newProject);
    },
  });
}
