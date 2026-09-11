// features/evidenceAudit/types/evidence-audit.types.ts — the audited-claim types.
//
// what  : TypeScript types inferred from evidence-audit.schema.ts, plus the query the surface sends.
// where : Imported by the audit service, hook and components.
// how   : Inferred rather than hand-written, so the wire contract and the types the components consume
//         cannot drift. Same rule the other features follow.

import type { z } from "zod";

import type { ConfidenceBandId } from "@/lib/constants/evidence-audit";
import type { ModelId } from "@/lib/constants/models";

import type {
  auditedClaimPageSchema,
  auditedClaimSchema,
  auditEvidenceItemSchema,
} from "../schemas/evidence-audit.schema";

export type AuditEvidenceItem = z.infer<typeof auditEvidenceItemSchema>;

export type AuditedClaim = z.infer<typeof auditedClaimSchema>;
export type AuditedClaimPage = z.infer<typeof auditedClaimPageSchema>;

/** What the auditor is asking for. Every field is optional; omitting all of them returns the corpus. */
export interface EvidenceAuditQuery {
  /** Free text over claim wording, investigation name, area and scene id. */
  search?: string;
  modelId?: ModelId | null;
  band?: ConfidenceBandId;
  cursor?: string | null;
  limit?: number;
}
