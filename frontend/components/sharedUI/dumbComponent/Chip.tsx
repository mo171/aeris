// components/sharedUI/dumbComponent/Chip.tsx — compact metadata tag used across scene and mission cards.

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type ChipTone = "neutral" | "teal" | "blue" | "amber" | "red" | "green";

const TONE_CLASS: Record<ChipTone, string> = {
  neutral: "border-border text-muted-foreground bg-muted/40",
  teal: "border-aeris-teal/35 text-aeris-teal bg-aeris-teal/10",
  blue: "border-aeris-blue/35 text-aeris-blue bg-aeris-blue/10",
  amber: "border-aeris-amber/35 text-aeris-amber bg-aeris-amber/10",
  red: "border-aeris-red/35 text-aeris-red bg-aeris-red/10",
  green: "border-aeris-green/35 text-aeris-green bg-aeris-green/10",
};

interface ChipProps {
  children: ReactNode;
  tone?: ChipTone;
  className?: string;
  title?: string;
}

export function Chip({ children, tone = "neutral", className, title }: ChipProps) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border px-1.5 py-px font-mono text-[10px] leading-4 tracking-wide uppercase",
        TONE_CLASS[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
