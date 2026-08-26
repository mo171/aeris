// components/sharedUI/functionalComponent/input/DropZone.tsx — drag-and-drop / click-to-browse file intake.
//
// what  : A dashed target that accepts dropped files or opens a file picker, with a glowing drag-over state.
// where : Used by the imagery upload zone; reusable by any future surface that takes file input.
// how   : Drag events fire on every child element, so a naive `dragleave` handler flickers the highlight
//         constantly as the pointer crosses inner nodes. This tracks a depth counter instead, which is the
//         only reliable way to know the pointer has actually left the zone — that flicker is precisely the
//         kind of glitch that makes an interface feel unfinished.
//
//         The component holds no upload logic. It reports files upward; the feature hook owns the transfer.

"use client";

import { CloudUpload } from "lucide-react";
import { useCallback, useId, useRef, useState, type DragEvent } from "react";

import { cn } from "@/lib/utils";

interface DropZoneProps {
  onFilesSelected: (files: File[]) => void;
  /** Comma-separated accept attribute, e.g. ".tif,.tiff,image/png". */
  accept?: string;
  isDisabled?: boolean;
  title: string;
  description: string;
  className?: string;
}

export function DropZone({
  onFilesSelected,
  accept,
  isDisabled = false,
  title,
  description,
  className,
}: DropZoneProps) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dragDepthRef = useRef(0);
  const [isDragActive, setIsDragActive] = useState(false);

  const emitFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) {
        return;
      }
      onFilesSelected(Array.from(fileList));
    },
    [onFilesSelected],
  );

  const handleDragEnter = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      if (isDisabled) {
        return;
      }
      dragDepthRef.current += 1;
      setIsDragActive(true);
    },
    [isDisabled],
  );

  const handleDragLeave = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setIsDragActive(false);
    }
  }, []);

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      dragDepthRef.current = 0;
      setIsDragActive(false);
      if (isDisabled) {
        return;
      }
      emitFiles(event.dataTransfer.files);
    },
    [emitFiles, isDisabled],
  );

  return (
    <div
      onDragEnter={handleDragEnter}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={cn(
        "group/dropzone relative flex flex-col items-center justify-center gap-1.5 rounded-md border border-dashed px-4 py-5 text-center transition-colors duration-base",
        isDragActive
          ? "border-aeris-teal bg-aeris-teal/[0.07] shadow-glow-teal"
          : "border-border bg-muted/20 hover:border-aeris-teal/45 hover:bg-aeris-teal/[0.03]",
        isDisabled && "pointer-events-none opacity-50",
        className,
      )}
    >
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        multiple
        accept={accept}
        disabled={isDisabled}
        className="sr-only"
        onChange={(event) => {
          emitFiles(event.target.files);
          // Reset so selecting the same file twice in a row still fires a change event.
          event.target.value = "";
        }}
      />

      <CloudUpload
        className={cn(
          "size-5 transition-colors duration-base",
          isDragActive ? "text-aeris-teal" : "text-muted-foreground",
        )}
        aria-hidden="true"
      />

      <label htmlFor={inputId} className="cursor-pointer text-xs font-medium text-foreground">
        {title}
        <span className="absolute inset-0" aria-hidden="true" />
      </label>
      <p className="max-w-[28ch] text-[10px] leading-relaxed text-muted-foreground">{description}</p>
    </div>
  );
}
