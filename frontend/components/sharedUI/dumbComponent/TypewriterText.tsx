// components/sharedUI/dumbComponent/TypewriterText.tsx — the terminal-decrypt reveal for streamed agent text.
//
// what  : Reveals text progressively, with a short run of scrambled characters at the reveal head, and
//         keeps up when the source text is still growing from a stream.
// where : Used by the assistant panel for answers and by execution-trace detail lines.
// how   : This is the component most likely to make an interface feel broken, so it is written defensively.
//         Reveal position is driven by a single requestAnimationFrame loop and committed to React state at
//         most every COMMIT_INTERVAL_MS — a naive per-character setState re-renders the transcript
//         hundreds of times a second and visibly stutters once the answer grows long. The full text is
//         always present in the DOM for assistive technology, and operators who ask for reduced motion get
//         it instantly with no animation at all.

"use client";

import { useEffect, useRef, useState } from "react";

import { usePrefersReducedMotion } from "@/hooks/use-prefers-reduced-motion";
import { cn } from "@/lib/utils";

const SCRAMBLE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#%&/\\<>";
const SCRAMBLE_LENGTH = 3;
const COMMIT_INTERVAL_MS = 33;

interface TypewriterTextProps {
  text: string;
  /** While true the reveal keeps chasing new text; when it flips to false the remainder is flushed. */
  isStreaming?: boolean;
  charactersPerSecond?: number;
  className?: string;
}

export function TypewriterText({
  text,
  isStreaming = false,
  charactersPerSecond = 900,
  className,
}: TypewriterTextProps) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const [revealedCount, setRevealedCount] = useState(prefersReducedMotion ? text.length : 0);
  const revealedCountRef = useRef(revealedCount);
  const textRef = useRef(text);

  // The animation loop needs the newest text without re-subscribing on every streamed chunk, so the
  // latest value is mirrored into a ref from an effect rather than written during render.
  useEffect(() => {
    textRef.current = text;
  }, [text]);

  useEffect(() => {
    if (prefersReducedMotion) {
      revealedCountRef.current = textRef.current.length;
      setRevealedCount(textRef.current.length);
      return;
    }

    let animationFrameId = 0;
    let previousTimestamp: number | null = null;
    let lastCommitTimestamp = 0;
    let fractionalProgress = revealedCountRef.current;

    const step = (timestamp: number) => {
      if (previousTimestamp === null) {
        previousTimestamp = timestamp;
        lastCommitTimestamp = timestamp;
      }

      const elapsedSeconds = (timestamp - previousTimestamp) / 1000;
      previousTimestamp = timestamp;

      const targetLength = textRef.current.length;
      fractionalProgress = Math.min(
        targetLength,
        fractionalProgress + elapsedSeconds * charactersPerSecond,
      );

      const nextCount = Math.floor(fractionalProgress);
      const hasReachedEnd = nextCount >= targetLength;

      if (
        nextCount !== revealedCountRef.current &&
        (timestamp - lastCommitTimestamp >= COMMIT_INTERVAL_MS || hasReachedEnd)
      ) {
        lastCommitTimestamp = timestamp;
        revealedCountRef.current = nextCount;
        setRevealedCount(nextCount);
      }

      animationFrameId = window.requestAnimationFrame(step);
    };

    animationFrameId = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(animationFrameId);
  }, [charactersPerSecond, prefersReducedMotion]);

  // A finished stream must never leave characters behind, whatever the animation was doing.
  useEffect(() => {
    if (!isStreaming && revealedCountRef.current < text.length) {
      revealedCountRef.current = text.length;
      setRevealedCount(text.length);
    }
  }, [isStreaming, text]);

  const safeRevealedCount = Math.min(revealedCount, text.length);
  const revealedText = text.slice(0, safeRevealedCount);
  const isRevealing = safeRevealedCount < text.length;

  return (
    <span className={cn("whitespace-pre-wrap", className)} aria-label={text}>
      <span aria-hidden={false}>{revealedText}</span>
      {isRevealing ? (
        <span aria-hidden="true" className="text-aeris-teal/70">
          {buildScramble(text, safeRevealedCount)}
        </span>
      ) : null}
    </span>
  );
}

/**
 * Produces the short run of noise sitting just ahead of the reveal head.
 *
 * Deliberately deterministic: the characters are derived from the reveal position rather than from
 * Math.random(). Rendering must be pure, and it costs nothing visually — the head advances on every
 * commit, so the noise still changes constantly to the eye while the same render always produces the
 * same output.
 */
function buildScramble(text: string, position: number): string {
  const available = Math.min(SCRAMBLE_LENGTH, text.length - position);
  let scramble = "";

  for (let offset = 0; offset < available; offset += 1) {
    const sourceCharacter = text[position + offset];

    // Whitespace is preserved so the reveal never reflows the paragraph as it advances.
    if (sourceCharacter === " " || sourceCharacter === "\n") {
      scramble += sourceCharacter;
      continue;
    }

    const scrambleIndex = (position * 31 + offset * 17 + text.charCodeAt(position)) % SCRAMBLE_ALPHABET.length;
    scramble += SCRAMBLE_ALPHABET[scrambleIndex];
  }

  return scramble;
}
