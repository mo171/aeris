// features/investigation/components/viewer/SceneReadout.tsx — where the camera is, how big the scene is, and what is under the pointer.
//
// what  : A single strip carrying the camera's position and altitude, a measured scale bar, a north
//         indicator, the ground position under the pointer, and — while a shape is being drawn — its
//         running area, length, bearing and vertex count.
// where : The bottom of the centre column in InvestigationScreen, under the tool cluster.
// how   : A geospatial surface that cannot state where it is asks the operator to trust it about position
//         while refusing to give one. Three separate questions live here because they are asked at the
//         same moment and answered from the same sample:
//
//         WHERE THE CAMERA IS — the view's own coordinate and altitude. Without it a shared screenshot has
//         no location and an operator has no idea what scale they are working at.
//
//         HOW BIG THINGS ARE — the scale bar, measured by picking two adjacent centre pixels against the
//         ellipsoid rather than derived from altitude, so it stays correct under tilt and in every
//         projection. Derived from altitude it would silently lie the moment the camera left nadir.
//
//         NORTH — meaningless until the camera can rotate, and the camera can now rotate. A rotated view
//         with no north indicator is a map you cannot take a bearing off.
//
//         Every value is written straight into the DOM rather than held in React state. They update at
//         pointer and camera rate, and a render per sample would spend exactly the frame budget the
//         drawing tools and the comparator need — the same reason the split handle works this way.

"use client";

import { useEffect, useRef } from "react";

import { useGeoStageStore } from "@/store/geo-stage-store";

/** Widths the scale bar is allowed to represent, so the number under it is always a round one. */
const SCALE_STEPS_METERS = [
  1, 2, 5, 10, 20, 50, 100, 200, 500, 1_000, 2_000, 5_000, 10_000, 20_000, 50_000, 100_000, 200_000,
  500_000, 1_000_000,
];
/** The bar is allowed to grow to this before the next step up is chosen. */
const SCALE_TARGET_PIXELS = 84;

function formatLatitude(latitude: number): string {
  return `${Math.abs(latitude).toFixed(5)}°${latitude >= 0 ? "N" : "S"}`;
}

function formatLongitude(longitude: number): string {
  return `${Math.abs(longitude).toFixed(5)}°${longitude >= 0 ? "E" : "W"}`;
}

function formatLength(meters: number): string {
  return meters >= 1_000 ? `${(meters / 1_000).toFixed(2)} km` : `${Math.round(meters)} m`;
}

function formatArea(hectares: number): string {
  return hectares >= 100 ? `${(hectares / 100).toFixed(2)} km²` : `${hectares.toFixed(2)} ha`;
}

function formatAltitude(meters: number): string {
  return meters >= 10_000
    ? `${(meters / 1_000).toFixed(0)} km`
    : meters >= 1_000
      ? `${(meters / 1_000).toFixed(1)} km`
      : `${Math.round(meters)} m`;
}

/** The largest round distance that still fits the target bar width. */
function chooseScale(metersPerPixel: number): { meters: number; pixels: number } | null {
  if (!Number.isFinite(metersPerPixel) || metersPerPixel <= 0) {
    return null;
  }

  const ideal = metersPerPixel * SCALE_TARGET_PIXELS;
  let chosen = SCALE_STEPS_METERS[0];
  for (const step of SCALE_STEPS_METERS) {
    if (step <= ideal) {
      chosen = step;
    }
  }

  return { meters: chosen, pixels: chosen / metersPerPixel };
}

export function SceneReadout() {
  const stage = useGeoStageStore((state) => state.handle);

  const cursorRef = useRef<HTMLSpanElement | null>(null);
  const measureRef = useRef<HTMLSpanElement | null>(null);
  const viewRef = useRef<HTMLSpanElement | null>(null);
  const scaleBarRef = useRef<HTMLSpanElement | null>(null);
  const scaleLabelRef = useRef<HTMLSpanElement | null>(null);
  const northRef = useRef<SVGGElement | null>(null);

  // ── Camera ───────────────────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!stage) {
      return;
    }

    return stage.camera.subscribeState((state) => {
      const viewElement = viewRef.current;
      if (viewElement) {
        viewElement.textContent = `${formatLatitude(state.latitude)}  ${formatLongitude(state.longitude)}  ·  ${formatAltitude(state.altitudeMeters)}`;
      }

      // The needle points at true north, so it counter-rotates against the camera heading.
      northRef.current?.setAttribute("transform", `rotate(${-state.headingDegrees} 8 8)`);

      const bar = scaleBarRef.current;
      const label = scaleLabelRef.current;
      if (!bar || !label) {
        return;
      }

      const scale =
        state.groundMetersPerPixel === null ? null : chooseScale(state.groundMetersPerPixel);

      if (!scale) {
        // Off the globe entirely — no ground under the centre pixel, so there is no scale to state.
        bar.style.width = "0px";
        label.textContent = "—";
        return;
      }

      bar.style.width = `${Math.round(scale.pixels)}px`;
      label.textContent = formatLength(scale.meters);
    });
  }, [stage]);

  // ── Pointer and measurement ──────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!stage) {
      return;
    }

    return stage.draw.subscribeLive((live) => {
      const cursorElement = cursorRef.current;
      if (cursorElement) {
        cursorElement.textContent = live.cursor
          ? `${formatLatitude(live.cursor.latitude)}  ${formatLongitude(live.cursor.longitude)}`
          : "— off globe —";
      }

      const measureElement = measureRef.current;
      if (!measureElement) {
        return;
      }

      if (!live.tool || live.vertexCount === 0) {
        measureElement.textContent = "";
        return;
      }

      const parts: string[] = [];
      if (live.bearingDegrees !== null) {
        parts.push(`${live.bearingDegrees.toFixed(1)}°`);
      }
      if (live.areaHectares > 0) {
        parts.push(formatArea(live.areaHectares));
      }
      if (live.lengthMeters > 0) {
        parts.push(formatLength(live.lengthMeters));
      }
      parts.push(`${live.vertexCount} pts`);

      measureElement.textContent = parts.join("  ·  ");
    });
  }, [stage]);

  if (!stage) {
    return null;
  }

  return (
    <div className="pointer-events-none flex items-center gap-2.5 rounded-md border border-border bg-surface-2/70 px-2.5 py-1 backdrop-blur-md">
      <svg width="16" height="16" viewBox="0 0 16 16" aria-label="North" role="img" className="shrink-0">
        <circle cx="8" cy="8" r="6.5" className="fill-none stroke-border" strokeWidth="1" />
        <g ref={northRef}>
          <path d="M8 2.4 L10 8 L8 6.9 L6 8 Z" className="fill-aeris-teal" />
          <path d="M8 13.6 L6 8 L8 9.1 L10 8 Z" className="fill-muted-foreground/45" />
        </g>
      </svg>

      <span
        ref={viewRef}
        className="font-mono text-[10px] tabular-nums whitespace-nowrap text-foreground"
      >
        —
      </span>

      <span className="h-3 w-px bg-border" aria-hidden="true" />

      {/* Scale bar: a measured length with a round number under it, not a ratio nobody can picture. */}
      <span className="flex shrink-0 items-center gap-1.5">
        <span className="relative flex h-2.5 items-end" aria-hidden="true">
          <span
            ref={scaleBarRef}
            className="block h-full border-x border-b border-foreground/60"
            style={{ width: 0 }}
          />
        </span>
        <span
          ref={scaleLabelRef}
          className="font-mono text-[10px] tabular-nums whitespace-nowrap text-muted-foreground"
        >
          —
        </span>
      </span>

      <span className="h-3 w-px bg-border" aria-hidden="true" />

      <span
        ref={cursorRef}
        className="font-mono text-[10px] tabular-nums whitespace-nowrap text-muted-foreground"
      >
        — off globe —
      </span>
      <span
        ref={measureRef}
        className="font-mono text-[10px] tabular-nums whitespace-nowrap text-aeris-teal"
      />
    </div>
  );
}
