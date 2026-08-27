// features/investigation/schemas/report.schema.ts — the intelligence report and its export handles.
//
// what  : Zod schemas for a report section, the assembled report, and the streamed events that build it.
// where : Parsed by report.service.ts; drives the report drawer.
// how   : Sections stream rather than arriving whole, so the drawer assembles in front of the operator.
//         That is not decoration: a report that appears instantly reads as a template being filled, while
//         one that builds section by section reads as a document being written from the run that just
//         happened — which is what it actually is.
//
//         Every export embeds the trace id. That is the whole claim of the product: any number in the PDF
//         walks back to pixels, parameters and a model version.

import { z } from "zod";

import { isoTimestampSchema } from "@/lib/schemas/geo.schema";

export const reportSectionKindSchema = z.enum([
  "summary",
  "inputs",
  "findings",
  "evidence",
  "models",
  "confidence",
  "limitations",
  "conclusion",
]);

export const reportSectionSchema = z.object({
  id: z.string().min(1),
  kind: reportSectionKindSchema,
  heading: z.string().min(1),
  body: z.string(),
  /** Layers this section illustrates, so a figure can be pulled from what is already on screen. */
  layerIds: z.array(z.string()),
});

export const reportSchema = z.object({
  id: z.string().min(1),
  investigationId: z.string().min(1),
  traceId: z.string().min(1),
  title: z.string().min(1),
  generatedAt: isoTimestampSchema,
  sections: z.array(reportSectionSchema),
});

export const reportStreamEventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("report-start"),
    reportId: z.string().min(1),
    title: z.string().min(1),
    traceId: z.string().min(1),
    generatedAt: isoTimestampSchema,
  }),
  z.object({
    type: z.literal("report-section"),
    reportId: z.string().min(1),
    section: reportSectionSchema,
  }),
  z.object({ type: z.literal("report-complete"), reportId: z.string().min(1) }),
  z.object({
    type: z.literal("report-error"),
    reportId: z.string().min(1),
    message: z.string().min(1),
  }),
]);

export const reportExportFormatSchema = z.enum(["pdf", "json", "geojson"]);
