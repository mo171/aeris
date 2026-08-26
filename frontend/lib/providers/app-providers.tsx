// lib/providers/app-providers.tsx — the single provider composition the root layout renders.
//
// what  : Wraps the application in server-state, toast and (during Phase 1) mock-transport infrastructure.
// where : Rendered once by app/layout.tsx. Adding a new global provider means editing this file only.
// how   : Providers are composed here rather than in the layout so app/layout.tsx stays a routing concern.
//         The mock bridge below runs at module scope, before any component renders, so the adapter is
//         guaranteed to be installed before the first query fires — an async import would race the first
//         request and produce an intermittent 404 on load.

"use client";

import type { ReactNode } from "react";

import { Toaster } from "@/components/ui/sonner";
import { apiClient } from "@/lib/axios/axios-client";
import { env } from "@/lib/env";

import { QueryProvider } from "./query-provider";

// ─────────────────────────────────────────────────────────────────────────────────────────────────────
//  PHASE 1 MOCK BRIDGE — DELETE THIS BLOCK TOGETHER WITH THE /mock FOLDER IN PHASE 2.
//  This import and the call below are the ONLY references to mock data anywhere in the application.
//  Deleting /mock makes the next line a compile error, which is deliberate: it is impossible to ship
//  with mock data still wired in, and impossible to forget a second removal step somewhere else.
import { installMockTransport } from "@/mock";

if (env.NEXT_PUBLIC_USE_MOCK_DATA) {
  installMockTransport(apiClient);
}
// ─────────────────────────────────────────────────────────────────────────────────────────────────────

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryProvider>
      {children}
      <Toaster
        position="bottom-right"
        toastOptions={{
          classNames: {
            toast: "aeris-glass !rounded-md !text-foreground",
            description: "!text-muted-foreground",
          },
        }}
      />
    </QueryProvider>
  );
}
