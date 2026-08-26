// components/sharedUI/functionalComponent/feedback/PanelSkeleton.tsx — loading placeholder for list panels.
//
// what  : Repeats a row-shaped skeleton with a sweeping highlight.
// where : Rendered by every list panel while its first page is in flight.
// how   : rowHeight is passed by the caller and must match the real row height. A skeleton that is not the
//         same size as the content it replaces produces a visible jump when data arrives, which is exactly
//         the kind of glitch this component exists to prevent.

import { cn } from "@/lib/utils";

interface PanelSkeletonProps {
  rowCount?: number;
  rowHeight: number;
  className?: string;
}

export function PanelSkeleton({ rowCount = 6, rowHeight, className }: PanelSkeletonProps) {
  return (
    <div className={cn("flex flex-col gap-1.5 px-3 py-2", className)} aria-hidden="true">
      {Array.from({ length: rowCount }, (_, index) => (
        <div
          key={index}
          style={{ height: rowHeight, animationDelay: `${index * 90}ms` }}
          className="relative overflow-hidden rounded-md border border-border-soft bg-muted/25"
        >
          <span className="absolute inset-y-0 -left-1/2 w-1/2 animate-sweep bg-gradient-to-r from-transparent via-white/[0.045] to-transparent" />
        </div>
      ))}
    </div>
  );
}
