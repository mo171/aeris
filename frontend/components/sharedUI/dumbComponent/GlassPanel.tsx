// components/sharedUI/dumbComponent/GlassPanel.tsx — the glassmorphic surface every floating panel uses.

import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

type GlassPanelElevation = "flat" | "raised" | "floating";

const ELEVATION_CLASS: Record<GlassPanelElevation, string> = {
  flat: "shadow-none",
  raised: "shadow-raised",
  floating: "shadow-panel",
};

interface GlassPanelProps extends ComponentProps<"div"> {
  elevation?: GlassPanelElevation;
}

export function GlassPanel({
  className,
  elevation = "floating",
  ...props
}: GlassPanelProps) {
  return (
    <div
      data-slot="glass-panel"
      className={cn("aeris-glass rounded-lg", ELEVATION_CLASS[elevation], className)}
      {...props}
    />
  );
}
