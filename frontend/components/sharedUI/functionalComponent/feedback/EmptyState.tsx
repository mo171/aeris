// components/sharedUI/functionalComponent/feedback/EmptyState.tsx — the "nothing here yet" panel state.
//
// what  : A centred icon, title, explanation and optional action, sized to sit inside a panel column.
// where : Used wherever a list can legitimately be empty — imagery catalogue, missions, notifications.
// how   : Every data surface in AERIS must render one of four states: loading, empty, error or content.
//         Sharing this component means the empty state is never an afterthought that ships as a blank box.

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-10 text-center",
        className,
      )}
    >
      <span className="flex size-9 items-center justify-center rounded-md border border-border bg-muted/40">
        <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
      </span>
      <p className="text-xs font-medium text-foreground">{title}</p>
      {description ? (
        <p className="max-w-[26ch] text-[11px] leading-relaxed text-muted-foreground">
          {description}
        </p>
      ) : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}
