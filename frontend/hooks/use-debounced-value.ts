// hooks/use-debounced-value.ts — trailing-edge debounce for fast-changing values.
//
// what  : Returns a copy of a value that only updates after it has been stable for `delayMs`.
// where : Used by the imagery catalogue search field so keystrokes do not each trigger a query.
// how   : Debouncing the value rather than the callback keeps the input fully controlled and instantly
//         responsive while the expensive downstream work runs at most once per pause.

"use client";

import { useEffect, useState } from "react";

export function useDebouncedValue<TValue>(value: TValue, delayMs: number): TValue {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => setDebouncedValue(value), delayMs);
    return () => window.clearTimeout(timeoutId);
  }, [value, delayMs]);

  return debouncedValue;
}
