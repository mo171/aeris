// mock/streams/report-stream.ts — replays report generation as server-sent-event frames.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : Emits report-start, one report-section per section, and report-complete.
// where : Installed onto lib/streaming by mock/streams/index.ts.
// how   : Sections are paced so the drawer visibly assembles rather than appearing whole. That pacing is
//         the feature being mocked — a report that materialises instantly reads as a template being
//         filled, and testing against an instant mock would never surface that.

import type { StreamRequestConfig } from "@/lib/streaming/stream-client";

import { getMockInvestigation, getMockReportSections } from "../data/investigation.data";

const SECTION_DELAY_MS = 420;

export async function mockReportStream({
  body,
  signal,
  onMessage,
}: StreamRequestConfig): Promise<void> {
  const { investigationId } = body as { investigationId: string };
  const reportId = `rep_${Date.now().toString(36)}`;
  const investigation = getMockInvestigation(investigationId);
  const emit = (payload: unknown) => onMessage(JSON.stringify(payload));

  if (!investigation) {
    emit({ type: "report-error", reportId, message: "That investigation no longer exists." });
    return;
  }

  emit({
    type: "report-start",
    reportId,
    title: `${investigation.name} — intelligence report`,
    traceId: investigation.traceId,
    generatedAt: new Date().toISOString(),
  });

  for (const section of getMockReportSections(investigationId)) {
    if (await isCancelled(signal, SECTION_DELAY_MS)) {
      return;
    }
    emit({ type: "report-section", reportId, section });
  }

  emit({ type: "report-complete", reportId });
}

function isCancelled(signal: AbortSignal | undefined, delayMs: number): Promise<boolean> {
  if (signal?.aborted) {
    return Promise.resolve(true);
  }

  return new Promise((resolve) => {
    const timeoutId = window.setTimeout(() => {
      signal?.removeEventListener("abort", handleAbort);
      resolve(Boolean(signal?.aborted));
    }, delayMs);

    function handleAbort() {
      window.clearTimeout(timeoutId);
      resolve(true);
    }

    signal?.addEventListener("abort", handleAbort, { once: true });
  });
}
