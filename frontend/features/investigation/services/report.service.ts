// features/investigation/services/report.service.ts — the intelligence report, streamed and exported.
//
// what  : Opens the report stream and builds the export URLs for PDF, JSON and GeoJSON.
// where : Called by use-report.ts only.
// how   : Sections stream so the drawer assembles in front of the operator. A report that appears whole
//         reads as a template being filled; one that builds section by section reads as a document being
//         written from the run that just happened, which is what it is.
//
//         Exports are plain URLs rather than blobs fetched through the client. The file is generated
//         server-side with the trace id embedded, and letting the browser download it directly keeps a
//         potentially large PDF out of the page memory entirely.

import { env } from "@/lib/env";
import { REST_API } from "@/lib/constants/rest.api";
import { openStream } from "@/lib/streaming/stream-client";

import { reportStreamEventSchema } from "../schemas/report.schema";
import type { ReportExportFormat, ReportStreamEvent } from "../types/report.types";

export interface ReportStreamHandlers {
  onEvent: (event: ReportStreamEvent) => void;
}

export async function streamReport(
  investigationId: string,
  handlers: ReportStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  await openStream({
    path: REST_API.investigations.report(investigationId),
    body: { investigationId },
    signal,
    onMessage: (rawData) => {
      const event = safeParseStreamFrame(rawData);
      if (event) {
        handlers.onEvent(event);
      }
    },
  });
}

export function buildReportExportUrl(
  investigationId: string,
  format: ReportExportFormat,
): string {
  return `${env.NEXT_PUBLIC_API_URL}${REST_API.investigations.report(investigationId)}.${format}`;
}

function safeParseStreamFrame(rawData: string): ReportStreamEvent | null {
  try {
    const parsed = reportStreamEventSchema.safeParse(JSON.parse(rawData));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}
