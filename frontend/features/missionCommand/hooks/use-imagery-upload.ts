// features/missionCommand/hooks/use-imagery-upload.ts — the three-step imagery ingest flow.
//
// what  : Takes files from the drop zone through ticket → direct upload → confirm, tracking per-file
//         progress, and refreshes the catalogue when a file lands.
// where : Consumed by ImageryUploadZone in the data panel.
// how   : The upload is a three-step handshake rather than a single POST because files go straight to
//         cloud storage: the backend mints a signed ticket, the browser streams to storage, and only then
//         does the backend hear that the object exists. Each file runs independently, so one failure
//         never blocks the rest of a batch.
//
//         Progress lives in the feature store, not in query state — it is client-side, high frequency,
//         and meaningless to the cache. Only the final catalogue invalidation touches TanStack Query.

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/axios/api-error";
import { QUERY_KEYS } from "@/lib/constants/query-keys";

import {
  confirmImageryUpload,
  createImageryUploadTicket,
  uploadImageryFile,
} from "../services/imagery.service";
import { useMissionCommandStore } from "../store/mission-command-store";
import type { ImageryUploadTask } from "../types/imagery.types";

/** Formats accepted by the ingest pipeline. Anything else is rejected before a request is made. */
export const ACCEPTED_IMAGERY_EXTENSIONS = ".tif,.tiff,.geotiff,.png,.jpg,.jpeg,.jp2,.zip";
const MAX_UPLOAD_BYTES = 8 * 1024 * 1024 * 1024;

interface ImageryUploadResult {
  uploadTasks: ImageryUploadTask[];
  startUploads: (files: File[]) => void;
  dismissUploadTask: (localId: string) => void;
  isUploading: boolean;
}

export function useImageryUpload(): ImageryUploadResult {
  const queryClient = useQueryClient();
  const uploadTasks = useMissionCommandStore((state) => state.uploadTasks);
  const addUploadTask = useMissionCommandStore((state) => state.addUploadTask);
  const updateUploadTask = useMissionCommandStore((state) => state.updateUploadTask);
  const removeUploadTask = useMissionCommandStore((state) => state.removeUploadTask);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const localId = `${file.name}-${file.size}-${Date.now()}`;

      addUploadTask({
        localId,
        fileName: file.name,
        fileSizeBytes: file.size,
        progressPercentage: 0,
        state: "preparing",
        errorMessage: null,
      });

      try {
        const ticket = await createImageryUploadTicket({
          fileName: file.name,
          fileSizeBytes: file.size,
          contentType: file.type.length > 0 ? file.type : "application/octet-stream",
        });

        updateUploadTask(localId, { state: "uploading" });

        await uploadImageryFile(ticket, file, (progressPercentage) => {
          updateUploadTask(localId, { progressPercentage });
        });

        updateUploadTask(localId, { state: "processing", progressPercentage: 100 });
        await confirmImageryUpload(ticket.sceneId);
        updateUploadTask(localId, { state: "complete" });

        return ticket.sceneId;
      } catch (error) {
        const message =
          error instanceof ApiError ? error.message : "The upload could not be completed.";
        updateUploadTask(localId, { state: "failed", errorMessage: message });
        throw error;
      }
    },
    onSuccess: () => {
      // The scene now exists server-side, so the catalogue must be refetched to include it.
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.imagery.all });
    },
  });

  const startUploads = useCallback(
    (files: File[]) => {
      for (const file of files) {
        if (file.size > MAX_UPLOAD_BYTES) {
          toast.error("File is too large", {
            description: `${file.name} exceeds the 8 GB scene limit.`,
          });
          continue;
        }
        uploadMutation.mutate(file);
      }
    },
    [uploadMutation],
  );

  return {
    uploadTasks,
    startUploads,
    dismissUploadTask: removeUploadTask,
    isUploading: uploadTasks.some(
      (task) => task.state === "preparing" || task.state === "uploading" || task.state === "processing",
    ),
  };
}
