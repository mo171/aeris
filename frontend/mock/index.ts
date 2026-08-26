// mock/index.ts — the single entry point of the Phase 1 mock layer. Deleting this folder removes all of it.
//
// what  : Installs the in-memory axios adapter and the scripted assistant stream transport.
// where : Called exactly once, from lib/providers/app-providers.tsx, guarded by NEXT_PUBLIC_USE_MOCK_DATA.
// how   : This is the only seam between the application and its mock data. Services, hooks, stores and
//         components contain zero references to anything in this folder — they always write the real call.
//
// ────────────────────────────────────────────────────────────────────────────────────────────────────
//  PHASE 2 REMOVAL — two steps, and TypeScript enforces that you finish them:
//    1. Delete the /mock folder.
//    2. Delete the marked import and call block in lib/providers/app-providers.tsx.
//  After step 1 the compiler fails on exactly one line, so there is no way to leave mock data behind.
//  Nothing else in the codebase needs to change; the axios instance falls back to its default HTTP
//  adapter and lib/streaming falls back to its real fetch transport.
// ────────────────────────────────────────────────────────────────────────────────────────────────────

import type { AxiosInstance } from "axios";

import { setStreamTransport } from "@/lib/streaming/stream-client";

import { mockAssistantStreamTransport } from "./streams/assistant-stream";
import { mockAxiosAdapter } from "./transport/mock-adapter";

let isInstalled = false;

export function installMockTransport(client: AxiosInstance): void {
  if (isInstalled) {
    return;
  }

  client.defaults.adapter = mockAxiosAdapter;
  setStreamTransport(mockAssistantStreamTransport);
  isInstalled = true;

  if (typeof window !== "undefined") {
    // Loud and unmissable: no one should ever mistake mock output for live backend output.
    console.info(
      "%cAERIS · Phase 1 mock transport active",
      "color:#00E5FF;font-weight:600;",
      "All API and stream responses are generated locally.",
    );
  }
}
