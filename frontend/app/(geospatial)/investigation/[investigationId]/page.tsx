// app/(geospatial)/investigation/[investigationId]/page.tsx — the Investigation Workspace route.
//
// what  : Routes "/investigation/:investigationId" to the workspace surface and names the browser tab.
// where : Reached from Mission Command via the investigation.create command, or directly by URL.
// how   : Deliberately thin. Pages are route entry points and nothing else — all composition, state and
//         data belong to the feature module, which is what lets the same surface be reused by the
//         Cross-Modal Lab and the Temporal Explorer with a different comparator binding and no new code.
//
//         `params` is a promise in this version of Next.js and must be awaited before the id is read.
//
//         The tab title carries the investigation id rather than a generic label: an analyst working
//         several investigations at once picks the right tab from the title, and "Mission Command Center"
//         on every one of them defeats that.

import type { Metadata } from "next";

import { InvestigationScreen } from "@/features/investigation/components/InvestigationScreen";

interface InvestigationPageProps {
  params: Promise<{ investigationId: string }>;
}

export async function generateMetadata({ params }: InvestigationPageProps): Promise<Metadata> {
  const { investigationId } = await params;

  return {
    title: `Investigation ${investigationId}`,
    description: "Scene analysis with evidence layers, claim-linked overlays and a full execution trace.",
  };
}

export default async function InvestigationPage({ params }: InvestigationPageProps) {
  const { investigationId } = await params;

  return <InvestigationScreen investigationId={investigationId} />;
}
