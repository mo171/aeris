// features/investigation/components/viewer/SceneReadout.tsx — the live coordinate and measurement strip.
//
// what  : Shows the ground position under the pointer at all times, and — while a shape is being drawn —
//         its running area, length, bearing and vertex count.
// where : Rendered at the bottom of the centre column in InvestigationScreen, under the tool cluster.
// how   : Live area is not a nicety. An analyst sizing an area of interest is deciding whether it is the
//         right scope, and discovering the size only after committing means drawing it twice. The same
//         goes for coordinates: a geospatial surface that cannot tell you where the pointer is asks you
//         to trust it about position while refusing to state one.
//
//         The values are written straight into the DOM rather than held in React state. They update at
//         pointer rate, and a render per pointer move would spend exactly the frame budget the drawing
//         tools need to feel responsive — the same reason the comparator handle works this way.

"use client";

import { useEffect, useRef } from "react";

import { useGeoStageStore } from "@/store/geo-stage-store";

/** Degrees to a signed degrees-minutes-seconds string, which is what an analyst reads off a map. */
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

export function SceneReadout() {
  const stage = useGeoStageStore((state) => state.handle);
  const cursorRef = useRef<HTMLSpanElement | null>(null);
  const measureRef = useRef<HTMLSpanElement | null>(null);

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
    <div className="pointer-events-none flex items-center gap-3 rounded-md border border-border bg-surface-2/70 px-2.5 py-1 backdrop-blur-md">
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
