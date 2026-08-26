// components/sharedUI/dumbComponent/SectionHeader.tsx — the small uppercase heading used inside panels.

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface SectionHeaderProps {
  title: string;
  /** Right-aligned slot for counts, filters or a small action. */
  trailing?: ReactNode;
  className?: string;
}

export function SectionHeader({ title, trailing, className }: SectionHeaderProps) {
  return (
    <div className={cn("flex h-7 items-center justify-between gap-2 px-3", className)}>
      <h2 className="aeris-technical truncate">{title}</h2>
      {trailing ? <div className="flex shrink-0 items-center gap-1">{trailing}</div> : null}
    </div>
  );
}
