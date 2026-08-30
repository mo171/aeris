// app/(reference)/evidence/page.tsx — the Evidence Audit.
//
// what  : The claim corpus across every investigation, filterable by model, confidence and free text.
// where : Reached from the navigation rail.
// how   : In the (reference) group rather than (geospatial): it reads a table, not a map. A row that needs
//         geometry links into the Investigation Workspace, which already owns a viewer — see the group's
//         layout for why a second one is not mounted here.

import { EvidenceAuditScreen } from "@/features/evidenceAudit/components/EvidenceAuditScreen";

export default function EvidenceAuditPage() {
  return <EvidenceAuditScreen />;
}
