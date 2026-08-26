// hooks/use-media-query.ts — hydration-safe media query subscription.
//
// what  : Returns whether a CSS media query currently matches, updating on change.
// where : Used for responsive shell behaviour (collapsing panels on narrow viewports).
// how   : Backed by useSyncExternalStore so React never renders a value that disagrees with the DOM.
//         The server snapshot is always false, which keeps SSR output stable and avoids hydration errors.

"use client";

import { useCallback, useSyncExternalStore } from "react";

export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      const mediaQueryList = window.matchMedia(query);
      mediaQueryList.addEventListener("change", onStoreChange);
      return () => mediaQueryList.removeEventListener("change", onStoreChange);
    },
    [query],
  );

  const getSnapshot = useCallback(() => window.matchMedia(query).matches, [query]);
  const getServerSnapshot = useCallback(() => false, []);

  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
