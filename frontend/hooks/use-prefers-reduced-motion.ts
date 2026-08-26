// hooks/use-prefers-reduced-motion.ts — respects the operator's motion preference in JS-driven animation.
//
// what  : Returns true when the operating system requests reduced motion.
// where : Used by the boot choreography, the typewriter effect and the globe's idle rotation.
// how   : globals.css already neutralises CSS animation for these users, but framer-motion and the
//         requestAnimationFrame loops in the globe run outside CSS and must opt out explicitly.

"use client";

import { useMediaQuery } from "./use-media-query";

export function usePrefersReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)");
}
