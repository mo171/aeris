// app/(geospatial)/investigation/page.tsx — the investigation index.
//
// what  : Lists existing investigations and points at Mission Command for starting a new one.
// where : Reached from the navigation rail, which links to the surface rather than to a specific record.
// how   : The rail links to a surface, so the surface has to exist — sending an operator to a 404 because
//         they have not picked a scene yet would be worse than a short list. Starting a new investigation
//         genuinely belongs on Mission Command, where the imagery catalogue is, so this page points there
//         rather than duplicating the picker.

import { InvestigationIndexScreen } from "@/features/investigation/components/InvestigationIndexScreen";

export default function InvestigationIndexPage() {
  return <InvestigationIndexScreen />;
}
