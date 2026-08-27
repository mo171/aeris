// features/investigation/types/evidence.types.ts — the claim and evidence graph types.
//
// what  : TypeScript types inferred from evidence.schema.ts, plus the normalised graph the store holds.
// where : Imported by the answer panel, the spotlight hook and evidence.service.ts.
// how   : NormalisedEvidenceGraph is the shape the UI actually reads. The wire format is flat arrays;
//         this is those arrays indexed by id, plus the order the panel renders them in. Building it once
//         on arrival makes hovering a claim a map lookup rather than a scan, which matters because the
//         spotlight fires on every pointer move across the answer.

import type { z } from "zod";

import type {
  claimKindSchema,
  claimMetricSchema,
  claimSchema,
  evidenceGraphSchema,
  evidenceItemSchema,
  evidenceKindSchema,
  insufficientEvidenceSchema,
  metricDirectionSchema,
} from "../schemas/evidence.schema";
import type { EvidenceLayer } from "./layer.types";

export type ClaimKind = z.infer<typeof claimKindSchema>;
export type MetricDirection = z.infer<typeof metricDirectionSchema>;
export type ClaimMetric = z.infer<typeof claimMetricSchema>;
export type Claim = z.infer<typeof claimSchema>;
export type EvidenceKind = z.infer<typeof evidenceKindSchema>;
export type EvidenceItem = z.infer<typeof evidenceItemSchema>;
export type InsufficientEvidence = z.infer<typeof insufficientEvidenceSchema>;
export type EvidenceGraph = z.infer<typeof evidenceGraphSchema>;

/** The graph as the UI reads it: indexed for lookup, ordered for rendering. */
export interface NormalisedEvidenceGraph {
  claimsById: Record<string, Claim>;
  claimOrder: string[];
  evidenceById: Record<string, EvidenceItem>;
  layersById: Record<string, EvidenceLayer>;
  layerOrder: string[];
}
