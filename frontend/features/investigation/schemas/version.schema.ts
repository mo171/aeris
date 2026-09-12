// features/investigation/schemas/version.schema.ts — investigation version snapshots.
//
// what  : Zod schema for a saved version of an investigation workspace.
// where : Used by use-investigation-versions.ts and version-diff.ts.
// how   : Versions are explicit saves only — the operator names the state they want to keep.
//         A version is a decision, not a side effect of running. Running never auto-saves.
//
//         parentVersionId makes branching a data fact in the schema now and a UI feature later (P3).
//         The diff engine is client-side and pure, so no round-trip is needed to compare two versions.

import { z } from "zod";

import { isoTimestampSchema } from "@/lib/schemas/geo.schema";
import { parameterValueSchema } from "@/lib/constants/parameters";
import { analysisTraceStepSchema } from "./analysis.schema";
import { investigationSceneSlotSchema } from "./investigation.schema";

/** A single metric from a claim, captured at save time for diffing. */
export const claimMetricSummarySchema = z.object({
  claimId: z.string().min(1),
  label: z.string().min(1),
  value: z.number(),
  unit: z.string(),
});

/** The full state snapshot stored inside a version. */
export const versionSnapshotSchema = z.object({
  sceneSlots: z.array(investigationSceneSlotSchema),
  timelinePair: z.object({
    baselineSceneId: z.string().nullable(),
    comparisonSceneId: z.string().nullable(),
  }),
  /**
   * The recorded workflow graph at save time, parameters and model versions included.
   * This is the primary diff surface — threshold 0.35 vs 0.45 lives here.
   */
  steps: z.array(analysisTraceStepSchema),
  resultSummary: z.object({
    claimMetrics: z.array(claimMetricSummarySchema),
    confidence: z.number().min(0).max(1).nullable(),
  }),
  layerIds: z.array(z.string()),
  traceId: z.string().min(1),
});

export const investigationVersionSchema = z.object({
  id: z.string().min(1),
  /** Human-chosen label, e.g. "Threshold 0.35 baseline". */
  label: z.string().min(1),
  createdAt: isoTimestampSchema,
  actor: z.enum(["operator", "agent"]),
  /** Null for the root version; non-null links into a tree (P3 branching). */
  parentVersionId: z.string().nullable(),
  snapshot: versionSnapshotSchema,
});

export const saveVersionRequestSchema = z.object({
  label: z.string().min(1, "Enter a label for this version."),
  snapshot: versionSnapshotSchema,
});
