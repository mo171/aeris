import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";
import type { CursorPageRequest } from "@/lib/types/api.types";

import { projectPageSchema, projectSchema } from "../schemas/project.schema";
import type { Project, ProjectCreateRequest, ProjectPage } from "../types/project.types";

export const PROJECT_PAGE_SIZE = 20;

export async function fetchProjectPage(
  request: CursorPageRequest,
  signal?: AbortSignal,
): Promise<ProjectPage> {
  const response = await apiClient.get(REST_API.projects.list, {
    signal,
    params: {
      cursor: request.cursor ?? undefined,
      limit: request.limit ?? PROJECT_PAGE_SIZE,
    },
  });

  return parseApiResponse(projectPageSchema, response.data, "the project list");
}

export async function fetchProject(
  projectId: string,
  signal?: AbortSignal,
): Promise<Project> {
  const response = await apiClient.get(REST_API.projects.detail(projectId), { signal });

  return parseApiResponse(projectSchema, response.data, "the project detail");
}

export async function createProject(
  request: ProjectCreateRequest,
  signal?: AbortSignal,
): Promise<Project> {
  const response = await apiClient.post(REST_API.projects.create, request, { signal });

  return parseApiResponse(projectSchema, response.data, "the created project");
}
