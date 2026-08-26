// components/sharedUI/functionalComponent/appShell/PanelContainer.tsx — a resizable, collapsible glass panel.
//
// what  : Wraps panel content in a glass surface that can be collapsed, and gives it a drag handle on its
//         inner edge for resizing.
// where : Used for the Data & Context panel and the Assistant panel, and by any future surface that
//         floats a panel over a canvas.
// how   : Resizing is done with pointer capture and a direct style write during the drag, committing the
//         final width to the store only on release. Writing every mousemove into Zustand would re-render
//         the whole panel subtree dozens of times a second and the drag would visibly lag behind the
//         cursor. Transitions are suppressed while dragging for the same reason — a width transition
//         fighting a live drag is the classic source of rubber-banding.
//
//         Collapse animates transform and opacity rather than unmounting, so the panel's scroll position
//         and any in-flight state survive being hidden.

"use client";

import { useCallback, useRef, useState, type PointerEvent, type ReactNode } from "react";

import { GlassPanel } from "@/components/sharedUI/dumbComponent/GlassPanel";
import { PANEL_WIDTH_LIMITS } from "@/store/ui-store";
import { cn } from "@/lib/utils";

interface PanelContainerProps {
  side: "left" | "right";
  isOpen: boolean;
  width: number;
  onWidthCommit: (width: number) => void;
  children: ReactNode;
  /** Entrance delay in seconds for the shell boot choreography. */
  revealDelaySeconds?: number;
  ariaLabel: string;
  className?: string;
}

export function PanelContainer({
  side,
  isOpen,
  width,
  onWidthCommit,
  children,
  revealDelaySeconds = 0,
  ariaLabel,
  className,
}: PanelContainerProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const dragStateRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handlePointerDown = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      dragStateRef.current = { startX: event.clientX, startWidth: width };
      setIsDragging(true);
    },
    [width],
  );

  const handlePointerMove = useCallback((event: PointerEvent<HTMLDivElement>) => {
    const dragState = dragStateRef.current;
    const panel = panelRef.current;
    if (!dragState || !panel) {
      return;
    }

    const delta = event.clientX - dragState.startX;
    const nextWidth = clampWidth(
      side === "left" ? dragState.startWidth + delta : dragState.startWidth - delta,
    );
    panel.style.width = `${nextWidth}px`;
  }, [side]);

  const handlePointerUp = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      const dragState = dragStateRef.current;
      if (!dragState) {
        return;
      }

      event.currentTarget.releasePointerCapture(event.pointerId);
      dragStateRef.current = null;
      setIsDragging(false);

      const committedWidth = panelRef.current
        ? Number.parseInt(panelRef.current.style.width, 10)
        : width;
      onWidthCommit(Number.isFinite(committedWidth) ? committedWidth : width);
    },
    [onWidthCommit, width],
  );

  return (
    <GlassPanel
      ref={panelRef}
      aria-label={ariaLabel}
      aria-hidden={!isOpen}
      style={{
        width,
        animationDelay: `${revealDelaySeconds}s`,
      }}
      className={cn(
        "pointer-events-auto relative flex h-full min-h-0 animate-rise flex-col overflow-hidden",
        !isDragging && "transition-[transform,opacity] duration-base ease-expo",
        isOpen
          ? "translate-x-0 opacity-100"
          : cn(
              "pointer-events-none opacity-0",
              side === "left" ? "-translate-x-[calc(100%+1rem)]" : "translate-x-[calc(100%+1rem)]",
            ),
        className,
      )}
    >
      {children}

      <div
        role="separator"
        aria-orientation="vertical"
        aria-label={`Resize ${ariaLabel}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        className={cn(
          "absolute inset-y-0 z-10 w-1.5 cursor-col-resize touch-none transition-colors duration-fast hover:bg-aeris-teal/25",
          isDragging && "bg-aeris-teal/40",
          side === "left" ? "right-0" : "left-0",
        )}
      />
    </GlassPanel>
  );
}

function clampWidth(width: number): number {
  return Math.max(PANEL_WIDTH_LIMITS.minimum, Math.min(PANEL_WIDTH_LIMITS.maximum, width));
}
