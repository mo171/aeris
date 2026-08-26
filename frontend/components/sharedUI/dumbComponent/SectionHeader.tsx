// components/sharedUI/dumbComponent/SectionHeader.tsx — the small uppercase heading used inside panels.
//
// Pass `onToggle` to make the whole header a collapse control; leave it off for a static heading.

import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface SectionHeaderProps {
  title: string;
  /** Right-aligned slot for counts, filters or a small action. */
  trailing?: ReactNode;
  /** Supplying this turns the header into a collapse toggle. */
  onToggle?: () => void;
  isExpanded?: boolean;
  className?: string;
}

export function SectionHeader({
  title,
  trailing,
  onToggle,
  isExpanded = true,
  className,
}: SectionHeaderProps) {
  const heading = (
    <>
      {onToggle ? (
        <ChevronDown
          className={cn(
            "size-3 shrink-0 text-muted-foreground transition-transform duration-base ease-expo",
            !isExpanded && "-rotate-90",
          )}
          aria-hidden="true"
        />
      ) : null}
      <h2 className="aeris-technical truncate">{title}</h2>
    </>
  );

  if (!onToggle) {
    return (
      <div className={cn("flex h-7 items-center justify-between gap-2 px-3", className)}>
        <span className="flex min-w-0 items-center gap-1.5">{heading}</span>
        {trailing ? <div className="flex shrink-0 items-center gap-1">{trailing}</div> : null}
      </div>
    );
  }

  return (
    <div className={cn("flex h-7 shrink-0 items-center justify-between gap-2 px-3", className)}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isExpanded}
        className="flex min-w-0 flex-1 items-center gap-1.5 rounded-sm text-left transition-colors duration-fast hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        {heading}
      </button>
      {trailing ? <div className="flex shrink-0 items-center gap-1">{trailing}</div> : null}
    </div>
  );
}
