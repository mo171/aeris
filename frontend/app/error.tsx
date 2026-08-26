// app/error.tsx — the route-level error boundary.
//
// what  : Catches any error that escapes a panel boundary and offers a recovery path.
// where : Applies to every route in the application.
// how   : This is the last line of defence. Each zone of a surface already has its own PanelErrorBoundary,
//         so reaching this screen means something broke outside a panel — the shell itself, or the route.
//         It stays branded and calm rather than showing a stack trace, and reset() re-renders the route
//         without a full page reload, so cached data and the operator's session survive.

"use client";

import { RotateCcw } from "lucide-react";
import { useEffect } from "react";

import { BrandLogo } from "@/components/sharedUI/dumbComponent/BrandLogo";
import { Button } from "@/components/ui/button";

export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[AERIS] route error", error);
  }, [error]);

  return (
    <div className="flex h-dvh w-full flex-col items-center justify-center gap-5 bg-background px-6">
      <BrandLogo />

      <div className="flex max-w-sm flex-col items-center gap-2 text-center">
        <h1 className="text-sm font-semibold text-foreground">This surface failed to render</h1>
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {error.message || "An unexpected error interrupted the command centre."}
        </p>
        {error.digest ? (
          <p className="font-mono text-[10px] tracking-wide text-muted-foreground/70 uppercase">
            Trace {error.digest}
          </p>
        ) : null}
      </div>

      <Button size="sm" variant="outline" onClick={reset}>
        <RotateCcw />
        Reload surface
      </Button>
    </div>
  );
}
