// features/investigation/types/report.types.ts — the report types.
//
// what  : TypeScript types inferred from report.schema.ts.
// where : Imported by the report drawer and report.service.ts.
// how   : See investigation.types.ts — every domain type on this surface is inferred from its Zod schema
//         so the validator and the type can never disagree.

import type { z } from "zod";

import type {
  reportExportFormatSchema,
  reportSchema,
  reportSectionKindSchema,
  reportSectionSchema,
  reportStreamEventSchema,
} from "../schemas/report.schema";

export type ReportSectionKind = z.infer<typeof reportSectionKindSchema>;
export type ReportSection = z.infer<typeof reportSectionSchema>;
export type InvestigationReport = z.infer<typeof reportSchema>;
export type ReportStreamEvent = z.infer<typeof reportStreamEventSchema>;
export type ReportExportFormat = z.infer<typeof reportExportFormatSchema>;
