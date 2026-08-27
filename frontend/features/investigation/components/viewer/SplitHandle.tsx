// features/investigation/components/viewer/SplitHandle.tsx — the before/after handle over the scene.
//
// what  : A draggable vertical divider that sets the comparator position, and follows it when something
//         else moves it.
// where : Rendered by InvestigationScreen across the full width of the scene, beneath the floating panels.
// how   : The position is NOT React state. It changes every frame while dragging or during a commanded
//         sweep, and a render per frame would spend exactly the budget this interaction exists to
//         showcase. The handle writes straight to the stage and reads back through a subscription, moving
//         itself by mutating its own transform — so the whole drag costs zero React renders.
//
//         Subscribing rather than owning is what lets AERIS drive it. When the assistant sweeps the
//         comparator while narrating an answer, this handle follows along, because it was never the source
//         of truth.
//
//         Pointer capture is used so a fast drag that leaves the element still tracks. Without it the
//         handle sticks the moment the pointer outruns it, which is exactly when someone is trying to
//         compare quickly.

"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef } from "react";

import { INVESTIGATION_COMPARATOR } from "@/lib/constants/investigation";
import { useGeoStageStore } from "@/store/geo-stage-store";

export function SplitHandle() {
  const stage = useGeoStageStore((state) => state.handle);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const handleRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!stage) {
      return;
    }

    return stage.comparator.subscribe((position) => {
      const element = handleRef.current;
      if (element) {
        element.style.left = `${position * 100}%`;
      }
    });
  }, [stage]);

  const applyPointerPosition = (clientX: number) => {
    const track = trackRef.current;
    if (!track || !stage) {
      return;
    }

    const bounds = track.getBoundingClientRect();
    if (bounds.width === 0) {
      return;
    }

    const ratio = (clientX - bounds.left) / bounds.width;
    stage.comparator.setPosition(
      Math.max(
        INVESTIGATION_COMPARATOR.minimumPosition,
        Math.min(INVESTIGATION_COMPARATOR.maximumPosition, ratio),
      ),
    );
  };

  const nudge = (delta: number) => {
    if (stage) {
      stage.comparator.setPosition(stage.comparator.getPosition() + delta);
    }
  };

  if (!stage) {
    return null;
  }

  return (
    <div ref={trackRef} className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        ref={handleRef}
        role="slider"
        tabIndex={0}
        aria-label="Before and after comparison position"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(stage.comparator.getPosition() * 100)}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          applyPointerPosition(event.clientX);
        }}
        onPointerMove={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            applyPointerPosition(event.clientX);
          }
        }}
        onPointerUp={(event) => event.currentTarget.releasePointerCapture(event.pointerId)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") {
            event.preventDefault();
            nudge(-0.02);
          }
          if (event.key === "ArrowRight") {
            event.preventDefault();
            nudge(0.02);
          }
        }}
        style={{ left: `${INVESTIGATION_COMPARATOR.defaultPosition * 100}%` }}
        className="pointer-events-auto absolute top-0 bottom-0 flex w-6 -translate-x-1/2 cursor-ew-resize touch-none items-center justify-center focus-visible:outline-none"
      >
        <span
          className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-aeris-teal/70 shadow-[0_0_12px_rgba(0,229,255,0.55)]"
          aria-hidden="true"
        />
        <span className="relative flex size-7 items-center justify-center rounded-full border border-aeris-teal/60 bg-surface-2/90 backdrop-blur-md">
          <ChevronLeft className="size-3 text-aeris-teal" aria-hidden="true" />
          <ChevronRight className="size-3 text-aeris-teal" aria-hidden="true" />
        </span>
      </div>
    </div>
  );
}
