// features/investigation/components/viewer/TargetLockOverlay.tsx — the corner brackets that draw on arrival.
//
// what  : Four corner brackets that draw themselves over the scene as the descent settles, then fade.
// where : Rendered by InvestigationScreen for the first moments after the workspace mounts.
// how   : Half a second of pure signalling. It costs nothing, it tells the operator the camera has arrived
//         at a specific place rather than drifted there, and it is the difference between a map and an
//         instrument. Reduced motion skips it entirely rather than flashing it.

"use client";

import { useEffect, useState } from "react";

import { usePrefersReducedMotion } from "@/hooks/use-prefers-reduced-motion";
import { cn } from "@/lib/utils";

const VISIBLE_MS = 1_600;

const CORNER_CLASSES = [
  "top-[18%] left-[22%] border-t border-l",
  "top-[18%] right-[22%] border-t border-r",
  "bottom-[22%] left-[22%] border-b border-l",
  "bottom-[22%] right-[22%] border-b border-r",
] as const;

export function TargetLockOverlay() {
  const prefersReducedMotion = usePrefersReducedMotion();
  const [isVisible, setIsVisible] = useState(!prefersReducedMotion);

  useEffect(() => {
    if (prefersReducedMotion) {
      return;
    }
    const timeoutId = window.setTimeout(() => setIsVisible(false), VISIBLE_MS);
    return () => window.clearTimeout(timeoutId);
  }, [prefersReducedMotion]);

  if (prefersReducedMotion) {
    return null;
  }

  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none absolute inset-0 transition-opacity duration-cinematic ease-expo",
        isVisible ? "opacity-100" : "opacity-0",
      )}
    >
      {CORNER_CLASSES.map((cornerClassName) => (
        <span
          key={cornerClassName}
          className={cn("absolute size-8 border-aeris-teal/70", cornerClassName)}
        />
      ))}
    </div>
  );
}
