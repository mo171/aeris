// features/investigation/types/version.types.ts — investigation version types.
//
// what  : TypeScript types inferred from version.schema.ts.
// where : Imported by the version hook, the diff engine, and the compare UI.

import type { z } from "zod";

import type {
  investigationVersionSchema,
  versionSnapshotSchema,
  claimMetricSummarySchema,
  saveVersionRequestSchema,
} from "../schemas/version.schema";

export type InvestigationVersion = z.infer<typeof investigationVersionSchema>;
export type VersionSnapshot = z.infer<typeof versionSnapshotSchema>;
export type ClaimMetricSummary = z.infer<typeof claimMetricSummarySchema>;
export type SaveVersionRequest = z.infer<typeof saveVersionRequestSchema>;

// ── Diff output types ─────────────────────────────────────────────────────────────────────────────

export type DiffSectionKind =
  | "inputs"
  | "workflow"
  | "parameters"
  | "models"
  | "result"
  | "confidence";

export interface DiffRow {
  label: string;
  before: string;
  after: string;
}

export interface DiffSection {
  kind: DiffSectionKind;
  title: string;
  rows: DiffRow[];
}
