// lib/providers/query-provider.tsx — mounts TanStack Query for the browser session.
//
// what  : Creates exactly one QueryClient per browser session and provides it to the tree.
// where : Composed by lib/providers/app-providers.tsx, which app/layout.tsx renders once.
// how   : The client is created inside useState so a React re-render (or a Fast Refresh) never discards
//         the cache, and so server rendering never shares a cache between requests.

"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { createQueryClient } from "@/lib/query/query-client";

export function QueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
