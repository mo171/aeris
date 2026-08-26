// hooks/use-webgl-support.ts — reports whether this browser can actually render WebGL.
//
// what  : Returns "unknown" during server rendering and hydration, then "supported" or "unsupported".
// where : Used by the globe viewport to decide between the canvas and the unavailable state.
// how   : Built on useSyncExternalStore rather than an effect that sets state. The server has no WebGL
//         context to probe, so it must render a neutral placeholder; useSyncExternalStore is the primitive
//         designed for exactly this split — React uses the server snapshot during hydration and swaps to
//         the client snapshot immediately afterwards, with no mismatch warning and no extra render pass.
//
//         The probe creates a real context, because a browser can advertise WebGL and still fail to
//         allocate one (blocklisted drivers, exhausted context limit). The result is cached at module
//         scope since getSnapshot must be cheap and must return a stable value.

"use client";

import { useSyncExternalStore } from "react";

export type WebGlSupport = "unknown" | "supported" | "unsupported";

let cachedSupport: WebGlSupport | null = null;

function probeWebGlSupport(): WebGlSupport {
  try {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    return context ? "supported" : "unsupported";
  } catch {
    return "unsupported";
  }
}

function getClientSnapshot(): WebGlSupport {
  cachedSupport ??= probeWebGlSupport();
  return cachedSupport;
}

function getServerSnapshot(): WebGlSupport {
  return "unknown";
}

/** WebGL availability never changes during a session, so there is nothing to subscribe to. */
function subscribe(): () => void {
  return () => {};
}

export function useWebGlSupport(): WebGlSupport {
  return useSyncExternalStore(subscribe, getClientSnapshot, getServerSnapshot);
}
