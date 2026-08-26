// components/sharedUI/functionalComponent/geoStage/split-comparator.ts — the before/after reveal.
//
// what  : Owns scene.splitPosition, the commanded sweep, ping-pong auto-play, and the subscription DOM
//         handles use to follow a movement they did not initiate.
// where : Owned by CesiumStage.tsx; bound to raster layers by the scene imagery layer set.
// how   : Cesium splits the scene natively — an imagery layer declares which half it belongs to and the
//         scene carries one horizontal position. Two properties. This is the interaction that kept the
//         project on a single engine: dragging a handle to watch T0 become T1 is the most direct
//         expression of felt change available, and every other engine would need a hand-rolled clip mask.
//
//         Position is deliberately NOT React state. It changes every frame while dragging or sweeping,
//         and a render per frame would cost the frame budget it is meant to showcase. The DOM handle
//         subscribes instead, so it tracks a commanded sweep without owning the value.
//
//         `sweep` is what makes this agentic: it is registered as a command, so AERIS can perform the
//         reveal itself while narrating the answer.

import type { Scene } from "cesium";

import { INVESTIGATION_COMPARATOR } from "@/lib/constants/investigation";

type PositionListener = (position: number) => void;

export interface SplitComparator {
  setPosition: (position: number) => void;
  getPosition: () => number;
  sweep: (options?: { from?: number; to?: number; durationMs?: number }) => void;
  setPlayback: (isPlaying: boolean) => void;
  isPlaying: () => boolean;
  subscribe: (listener: PositionListener) => () => void;
  /** Advances any animation in flight. Called once per frame by the stage. */
  update: (nowMs: number) => void;
  reset: () => void;
}

interface SweepAnimation {
  from: number;
  to: number;
  startedAt: number;
  durationMs: number;
}

export function createSplitComparator(scene: Scene): SplitComparator {
  const listeners = new Set<PositionListener>();
  let position: number = INVESTIGATION_COMPARATOR.defaultPosition;
  let sweepAnimation: SweepAnimation | null = null;
  let playbackDirection: 1 | -1 = 1;
  let playbackHoldUntilMs = 0;
  let isPlayingBack = false;

  scene.splitPosition = position;

  function clamp(value: number): number {
    return Math.max(
      INVESTIGATION_COMPARATOR.minimumPosition,
      Math.min(INVESTIGATION_COMPARATOR.maximumPosition, value),
    );
  }

  function commit(nextPosition: number): void {
    position = clamp(nextPosition);
    scene.splitPosition = position;
    for (const listener of listeners) {
      listener(position);
    }
  }

  function setPosition(nextPosition: number): void {
    // A direct set is an operator action and always wins over a machine-driven animation.
    sweepAnimation = null;
    isPlayingBack = false;
    commit(nextPosition);
  }

  function sweep(options?: { from?: number; to?: number; durationMs?: number }): void {
    const from = options?.from ?? INVESTIGATION_COMPARATOR.maximumPosition;
    const to = options?.to ?? INVESTIGATION_COMPARATOR.minimumPosition;

    isPlayingBack = false;
    commit(from);
    sweepAnimation = {
      from: clamp(from),
      to: clamp(to),
      startedAt: performance.now(),
      durationMs: options?.durationMs ?? INVESTIGATION_COMPARATOR.sweepDurationMs,
    };
  }

  function setPlayback(shouldPlay: boolean): void {
    isPlayingBack = shouldPlay;
    sweepAnimation = null;
    if (shouldPlay) {
      playbackHoldUntilMs = 0;
      playbackDirection = position > 0.5 ? -1 : 1;
    }
  }

  function update(nowMs: number): void {
    if (sweepAnimation) {
      const elapsed = nowMs - sweepAnimation.startedAt;
      const progress = Math.min(1, elapsed / sweepAnimation.durationMs);
      // Ease in and out: a linear sweep reads as a machine wiping the screen, an eased one reads as a
      // deliberate reveal.
      const eased =
        progress < 0.5
          ? 2 * progress * progress
          : 1 - Math.pow(-2 * progress + 2, 2) / 2;

      commit(sweepAnimation.from + (sweepAnimation.to - sweepAnimation.from) * eased);

      if (progress >= 1) {
        sweepAnimation = null;
      }
      return;
    }

    if (!isPlayingBack) {
      return;
    }

    if (nowMs < playbackHoldUntilMs) {
      return;
    }

    const step =
      (1 / (INVESTIGATION_COMPARATOR.playbackCrossSeconds * 60)) * playbackDirection;
    const next = position + step;

    if (next >= INVESTIGATION_COMPARATOR.maximumPosition) {
      commit(INVESTIGATION_COMPARATOR.maximumPosition);
      playbackDirection = -1;
      playbackHoldUntilMs = nowMs + INVESTIGATION_COMPARATOR.playbackHoldSeconds * 1000;
      return;
    }

    if (next <= INVESTIGATION_COMPARATOR.minimumPosition) {
      commit(INVESTIGATION_COMPARATOR.minimumPosition);
      playbackDirection = 1;
      playbackHoldUntilMs = nowMs + INVESTIGATION_COMPARATOR.playbackHoldSeconds * 1000;
      return;
    }

    commit(next);
  }

  function reset(): void {
    sweepAnimation = null;
    isPlayingBack = false;
    commit(INVESTIGATION_COMPARATOR.defaultPosition);
  }

  return {
    setPosition,
    getPosition: () => position,
    sweep,
    setPlayback,
    isPlaying: () => isPlayingBack,
    subscribe: (listener) => {
      listeners.add(listener);
      listener(position);
      return () => listeners.delete(listener);
    },
    update,
    reset,
  };
}
