// components/sharedUI/dumbComponent/GlowDot.tsx — a status dot with an optional pulse halo.

import { cn } from "@/lib/utils";

export type GlowDotTone = "teal" | "blue" | "amber" | "red" | "green" | "neutral";

const TONE_CLASS: Record<GlowDotTone, string> = {
  teal: "bg-aeris-teal shadow-[0_0_8px_var(--color-aeris-teal)]",
  blue: "bg-aeris-blue shadow-[0_0_8px_var(--color-aeris-blue)]",
  amber: "bg-aeris-amber shadow-[0_0_8px_var(--color-aeris-amber)]",
  red: "bg-aeris-red shadow-[0_0_8px_var(--color-aeris-red)]",
  green: "bg-aeris-green shadow-[0_0_8px_var(--color-aeris-green)]",
  neutral: "bg-aeris-gray-dim",
};

const HALO_TONE_CLASS: Record<GlowDotTone, string> = {
  teal: "bg-aeris-teal/40",
  blue: "bg-aeris-blue/40",
  amber: "bg-aeris-amber/40",
  red: "bg-aeris-red/40",
  green: "bg-aeris-green/40",
  neutral: "bg-aeris-gray-dim/30",
};

interface GlowDotProps {
  tone?: GlowDotTone;
  isPulsing?: boolean;
  className?: string;
}

export function GlowDot({ tone = "teal", isPulsing = false, className }: GlowDotProps) {
  return (
    <span className={cn("relative inline-flex size-1.5 shrink-0", className)}>
      {isPulsing ? (
        <span
          className={cn(
            "absolute inset-0 animate-ping rounded-full opacity-75",
            HALO_TONE_CLASS[tone],
          )}
        />
      ) : null}
      <span className={cn("relative inline-flex size-full rounded-full", TONE_CLASS[tone])} />
    </span>
  );
}
