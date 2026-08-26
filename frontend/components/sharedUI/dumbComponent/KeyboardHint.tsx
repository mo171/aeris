// components/sharedUI/dumbComponent/KeyboardHint.tsx — renders a key combination as small keycaps.

import { cn } from "@/lib/utils";

interface KeyboardHintProps {
  keys: readonly string[];
  className?: string;
}

export function KeyboardHint({ keys, className }: KeyboardHintProps) {
  return (
    <span className={cn("inline-flex items-center gap-0.5", className)}>
      {keys.map((key) => (
        <kbd
          key={key}
          className="inline-flex h-4 min-w-4 items-center justify-center rounded-[3px] border border-border bg-muted/60 px-1 font-mono text-[9px] tracking-wide text-muted-foreground uppercase"
        >
          {key}
        </kbd>
      ))}
    </span>
  );
}
