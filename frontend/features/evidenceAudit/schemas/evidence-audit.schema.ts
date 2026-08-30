// features/evidenceAudit/schemas/evidence-audit.schema.ts — the cross-investigation claim corpus contract.
//
// what  : Zod schema for one audited claim — the claim itself, the investigation it belongs to, the model
//         that produced it, and the acquisitions it rests on — plus the cursor page that carries them.
// where : Parsed by evidence-audit.service.ts; the inferred types drive the audit surface.
// how   : A FLATTENED PROJECTION, not the evidence graph. The workspace's graph is normalised because the
//         spotlight needs to traverse it; this surface only ever reads rows and links out, so joining
//         claim to investigation on the client would mean fetching every investigation to render a list.
//         The backend already has both sides of the join.
//
//         `modelId` is the catalogue enum rather than a free string, which is what makes "every claim this
//         model version produced" a reliable query — the whole reason the surface exists. A claim naming a
//         model the catalogue does not know fails here rather than quietly dropping out of the filter.

import { z } from "zod";

import { claimKindSchema } from "@/features/investigation/schemas/evidence.schema";
import { modelIdSchema } from "@/features/missionCommand/schemas/model.schema";
import { createCursorPageSchema, isoTimestampSchema } from "@/lib/schemas/geo.schema";

export const auditedClaimSchema = z.object({
  claimId: z.string().min(1),
  runId: z.string().min(1),
  text: z.string().min(1),
  kind: claimKindSchema,
  /** Null means AERIS declined to assert one — a refusal, never a zero. */
  confidence: z.number().min(0).max(1).nullable(),

  modelId: modelIdSchema,
  modelVersion: z.string().min(1),
  /** The pipeline step that produced it, so the row can point back into the workspace's trace. */
  traceStepId: z.string().min(1),

  investigationId: z.string().min(1),
  investigationName: z.string().min(1),
  areaOfInterestName: z.string().min(1),

  /** How many evidence records support it. Zero is a claim standing on nothing, and must be visible. */
  evidenceCount: z.number().int().nonnegative(),
  /** The acquisitions it was computed from, so a scene found faulty can be traced to what it touched. */
  sourceSceneIds: z.array(z.string()),
  producedAt: isoTimestampSchema,
});

export const auditedClaimPageSchema = createCursorPageSchema(auditedClaimSchema);
