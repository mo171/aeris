// features/investigation/hooks/use-report.ts — the intelligence report, assembled live.
//
// what  : Opens the report stream, accumulates sections as they arrive, and builds the export links.
// where : Consumed by the report drawer only.
// how   : Sections are held in local state rather than the feature store because nothing outside the
//         drawer reads them — putting them in the store would widen the surface for no benefit.
//
//         The report is generated on demand rather than kept warm. It describes the run that just
//         happened, so caching a stale one and showing it beside newer evidence would be worse than
//         making the operator wait a moment for an accurate one.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { buildReportExportUrl, streamReport } from "../services/report.service";
import type { ReportExportFormat, ReportSection } from "../types/report.types";

interface ReportState {
  title: string | null;
  traceId: string | null;
  sections: ReportSection[];
  isGenerating: boolean;
  error: string | null;
}

interface UseReportResult extends ReportState {
  generate: () => void;
  exportUrlFor: (format: ReportExportFormat) => string;
}

export function useReport(investigationId: string): UseReportResult {
  const [state, setState] = useState<ReportState>({
    title: null,
    traceId: null,
    sections: [],
    isGenerating: false,
    error: null,
  });
  const abortControllerRef = useRef<AbortController | null>(null);

  const generate = useCallback(() => {
    if (abortControllerRef.current) {
      return;
    }

    const abortController = new AbortController();
    abortControllerRef.current = abortController;
    setState({ title: null, traceId: null, sections: [], isGenerating: true, error: null });

    void streamReport(
      investigationId,
      {
        onEvent: (event) => {
          switch (event.type) {
            case "report-start":
              setState((current) => ({
                ...current,
                title: event.title,
                traceId: event.traceId,
              }));
              break;

            case "report-section":
              setState((current) => ({
                ...current,
                sections: [...current.sections, event.section],
              }));
              break;

            case "report-complete":
              setState((current) => ({ ...current, isGenerating: false }));
              break;

            case "report-error":
              setState((current) => ({
                ...current,
                isGenerating: false,
                error: event.message,
              }));
              break;
          }
        },
      },
      abortController.signal,
    )
      .catch((error: unknown) => {
        if (!abortController.signal.aborted) {
          setState((current) => ({
            ...current,
            isGenerating: false,
            error:
              error instanceof Error
                ? `Report generation failed: ${error.message}`
                : "Report generation failed.",
          }));
        }
      })
      .finally(() => {
        abortControllerRef.current = null;
      });
  }, [investigationId]);

  // Closing the drawer mid-generation must actually stop the work, not just hide it.
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  return {
    ...state,
    generate,
    exportUrlFor: useCallback(
      (format: ReportExportFormat) => buildReportExportUrl(investigationId, format),
      [investigationId],
    ),
  };
}
