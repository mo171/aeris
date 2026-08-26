// features/missionCommand/services/imagery.service.ts — all backend communication about satellite scenes.
//
// what  : Fetches the imagery catalogue page by page, mints signed upload tickets, sends a file straight to
//         cloud storage, and confirms ingestion.
// where : Called only by features/missionCommand/hooks/*. Components never import this file.
// how   : Every function accepts an AbortSignal so in-flight work is cancelled when a panel unmounts or a
//         search term changes. Uploads go directly to the storage provider using the signed URL and never
//         through the AERIS backend — a multi-gigabyte GeoTIFF must not occupy an application server.

import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";
import type { CursorPageRequest } from "@/lib/types/api.types";

import { imageryCatalogPageSchema, imageryUploadTicketSchema } from "../schemas/imagery.schema";
import type { ImageryCatalogPage, ImageryUploadTicket } from "../types/imagery.types";

export const IMAGERY_PAGE_SIZE = 25;

export async function fetchImageryCatalogPage(
  request: CursorPageRequest,
  signal?: AbortSignal,
): Promise<ImageryCatalogPage> {
  const trimmedSearch = request.search?.trim();

  const response = await apiClient.get(REST_API.imagery.list, {
    signal,
    params: {
      cursor: request.cursor ?? undefined,
      limit: request.limit ?? IMAGERY_PAGE_SIZE,
      search: trimmedSearch && trimmedSearch.length > 0 ? trimmedSearch : undefined,
    },
  });

  return parseApiResponse(imageryCatalogPageSchema, response.data, "the imagery catalogue");
}

export interface CreateUploadTicketRequest {
  fileName: string;
  fileSizeBytes: number;
  contentType: string;
}

export async function createImageryUploadTicket(
  request: CreateUploadTicketRequest,
  signal?: AbortSignal,
): Promise<ImageryUploadTicket> {
  const response = await apiClient.post(REST_API.imagery.createUploadTicket, request, { signal });

  return parseApiResponse(
    imageryUploadTicketSchema,
    response.data,
    "the imagery upload ticket endpoint",
  );
}

/**
 * Sends the file to the storage provider using the signed URL from the ticket.
 * The absolute URL bypasses the client base URL, so this still uses the single shared axios instance —
 * and therefore the shared error normalisation — without introducing a second one.
 */
export async function uploadImageryFile(
  ticket: ImageryUploadTicket,
  file: File,
  onProgress: (progressPercentage: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  await apiClient.put(ticket.uploadUrl, file, {
    signal,
    headers: {
      ...ticket.requiredHeaders,
      "Content-Type": file.type.length > 0 ? file.type : "application/octet-stream",
    },
    onUploadProgress: (event) => {
      if (!event.total) {
        return;
      }
      onProgress(Math.round((event.loaded / event.total) * 100));
    },
  });
}

export async function confirmImageryUpload(sceneId: string, signal?: AbortSignal): Promise<void> {
  await apiClient.post(REST_API.imagery.confirmUpload(sceneId), undefined, { signal });
}
