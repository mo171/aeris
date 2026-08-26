// features/missionCommand/components/dataPanel/ImageryUploadZone.tsx — imagery intake.
//
// what  : The drop target plus a live list of in-flight uploads with per-file progress and failures.
// where : The top section of the Data & Context panel.
// how   : Progress is shown per file rather than as one aggregate bar because scenes are large and
//         heterogeneous — a 4 GB GeoTIFF and a 40 MB PNG in the same batch make an aggregate percentage
//         meaningless. Failed uploads stay on screen with their reason until dismissed; silently dropping
//         a failure is how an operator ends up analysing a scene that was never ingested.

"use client";

import { LoaderCircle, TriangleAlert, X } from "lucide-react";

import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { DropZone } from "@/components/sharedUI/functionalComponent/input/DropZone";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import { ACCEPTED_IMAGERY_EXTENSIONS, useImageryUpload } from "../../hooks/use-imagery-upload";
import type { ImageryUploadTask } from "../../types/imagery.types";

const UPLOAD_STATE_LABEL: Record<ImageryUploadTask["state"], string> = {
  preparing: "Requesting upload slot",
  uploading: "Uploading",
  processing: "Preprocessing",
  complete: "Ready",
  failed: "Failed",
};

export function ImageryUploadZone() {
  const { uploadTasks, startUploads, dismissUploadTask } = useImageryUpload();

  return (
    <section className="shrink-0">
      <SectionHeader title="Imagery intake" />

      <div className="px-3 pt-1.5 pb-2">
        <DropZone
          onFilesSelected={startUploads}
          accept={ACCEPTED_IMAGERY_EXTENSIONS}
          title="Drop satellite imagery"
          description="GeoTIFF, TIFF, JP2, PNG or JPEG. Optical, SAR and multispectral scenes accepted."
        />

        {uploadTasks.length > 0 ? (
          <ul className="mt-2 flex flex-col gap-1.5">
            {uploadTasks.map((task) => (
              <li
                key={task.localId}
                className={cn(
                  "rounded-md border px-2 py-1.5",
                  task.state === "failed"
                    ? "border-aeris-red/35 bg-aeris-red/[0.06]"
                    : "border-border-soft bg-surface-2/50",
                )}
              >
                <div className="flex items-center gap-2">
                  {task.state === "failed" ? (
                    <TriangleAlert className="size-3 shrink-0 text-aeris-red" aria-hidden="true" />
                  ) : task.state === "complete" ? (
                    <span
                      className="size-1.5 shrink-0 rounded-full bg-aeris-green"
                      aria-hidden="true"
                    />
                  ) : (
                    <LoaderCircle
                      className="size-3 shrink-0 animate-spin text-aeris-teal"
                      aria-hidden="true"
                    />
                  )}

                  <span className="min-w-0 flex-1 truncate text-[10px] text-foreground">
                    {task.fileName}
                  </span>

                  <span className="shrink-0 font-mono text-[9px] text-muted-foreground">
                    {formatBytes(task.fileSizeBytes)}
                  </span>

                  <Button
                    size="icon-xs"
                    variant="ghost"
                    aria-label={`Dismiss ${task.fileName}`}
                    onClick={() => dismissUploadTask(task.localId)}
                  >
                    <X />
                  </Button>
                </div>

                <div className="mt-1 flex items-center gap-2">
                  <div className="h-0.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className={cn(
                        "h-full rounded-full transition-[width] duration-base ease-expo",
                        task.state === "failed" ? "bg-aeris-red" : "bg-aeris-teal",
                      )}
                      style={{ width: `${task.state === "complete" ? 100 : task.progressPercentage}%` }}
                    />
                  </div>
                  <span className="shrink-0 font-mono text-[9px] tracking-wide text-muted-foreground uppercase">
                    {UPLOAD_STATE_LABEL[task.state]}
                  </span>
                </div>

                {task.errorMessage ? (
                  <p className="mt-1 text-[9px] leading-relaxed text-aeris-red">
                    {task.errorMessage}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
