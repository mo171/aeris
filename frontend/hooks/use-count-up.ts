// hooks/use-count-up.ts — animates a number from zero to its value on arrival.
//
// what  : Returns a value that eases up to the target whenever the target changes.
// where : Used by the investigation answer panel metrics, and available to any surface showing a computed
//         figure.
// how   : A hectare figure that counts up reads as computed; one that simply appears reads as asserted.
//         That distinction is the whole product claim, so it is worth the animation.
//
//         Driven by requestAnimationFrame rather than a transition, because the value is text rather than
//         a style: there is nothing for CSS to interpolate.
//
//         Reduced motion is handled by returning the target directly rather than by writing it to state.
//         Setting state inside an effect to reach a value already known during render causes a cascading
//         render for no reason, and React Compiler correctly refuses it.
//
//         A timer backs the animation up, and that is a correctness measure rather than a nicety. Browsers
//         stop firing requestAnimationFrame in a background tab, so an operator who switches away while an
//         answer arrives would come back to a figure frozen at zero — a wrong number, displayed with total
//         confidence, in a product whose entire claim is that its numbers are trustworthy. Timers still
//         fire when hidden, so the value always reaches its target whether or not it got to animate there.

"use client";

import { useEffect, useRef, useState } from "react";

import { usePrefersReducedMotion } from "./use-prefers-reduced-motion";

const DEFAULT_DURATION_MS = 900;

export function useCountUp(target: number, durationMs: number = DEFAULT_DURATION_MS): number {
  const prefersReducedMotion = usePrefersReducedMotion();
  const [animatedValue, setAnimatedValue] = useState(0);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    if (prefersReducedMotion) {
      return;
    }

    const startValue = 0;
    const startedAt = performance.now();

    const step = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / durationMs);
      // Ease-out cubic: fast enough to feel responsive, slow enough at the end to be readable.
      const eased = 1 - Math.pow(1 - progress, 3);
      // Committing from inside the frame callback rather than from the effect body: this is a
      // subscription to an external clock, which is exactly what an effect is for.
      setAnimatedValue(startValue + (target - startValue) * eased);

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(step);
      }
    };

    frameRef.current = requestAnimationFrame(step);

    // Slack past the nominal duration so the timer only ever wins when the frame loop genuinely stalled.
    const settleTimeoutId = window.setTimeout(() => setAnimatedValue(target), durationMs + 250);

    return () => {
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
      }
      window.clearTimeout(settleTimeoutId);
    };
  }, [durationMs, prefersReducedMotion, target]);

  return prefersReducedMotion ? target : animatedValue;
}
