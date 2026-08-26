// components/sharedUI/dumbComponent/BrandLogo.tsx — the AERIS mark: an orbital ring around a sensor node.

import { cn } from "@/lib/utils";
import { APP } from "@/lib/constants/app";

interface BrandLogoProps {
  showWordmark?: boolean;
  className?: string;
}

export function BrandLogo({ showWordmark = true, className }: BrandLogoProps) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <span className="relative flex size-7 items-center justify-center">
        <svg viewBox="0 0 32 32" className="size-7" aria-hidden="true">
          <defs>
            <linearGradient id="aeris-mark-gradient" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="var(--color-aeris-teal)" />
              <stop offset="100%" stopColor="var(--color-aeris-blue)" />
            </linearGradient>
          </defs>
          <circle cx="16" cy="16" r="9.5" fill="none" stroke="url(#aeris-mark-gradient)" strokeWidth="1.4" />
          <ellipse
            cx="16"
            cy="16"
            rx="14"
            ry="5.5"
            fill="none"
            stroke="var(--color-aeris-teal)"
            strokeWidth="1"
            opacity="0.55"
            transform="rotate(-28 16 16)"
          />
          <circle cx="16" cy="16" r="2.6" fill="var(--color-aeris-teal)" />
          <circle cx="27.2" cy="9.8" r="1.5" fill="var(--color-aeris-blue)" />
        </svg>
      </span>

      {showWordmark ? (
        <span className="flex flex-col leading-none">
          <span className="text-sm font-semibold tracking-[0.22em] text-foreground">{APP.name}</span>
          <span className="mt-0.5 font-mono text-[9px] tracking-[0.16em] text-muted-foreground uppercase">
            Earth Intelligence
          </span>
        </span>
      ) : null}

      <span className="sr-only">{APP.fullName}</span>
    </span>
  );
}
