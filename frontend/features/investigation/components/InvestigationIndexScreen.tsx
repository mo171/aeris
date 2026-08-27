// features/investigation/components/InvestigationIndexScreen.tsx — the investigation launcher.
//
// what  : Lists saved investigations and routes to Mission Command for starting a new one.
// where : Rendered by app/(geospatial)/investigation/page.tsx.
// how   : A deliberately thin surface. Choosing imagery belongs on Mission Command, where the catalogue
//         and the globe already are, so this page does not duplicate the picker — it exists so the
//         navigation rail has somewhere real to send an operator who has not opened a specific
//         investigation yet.
//
//         The stage is still rendered underneath by the route group layout, so arriving here shows the
//         globe rather than an empty panel over a black rectangle.

"use client";

import { Globe, ScanSearch } from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { GlassPanel } from "@/components/sharedUI/dumbComponent/GlassPanel";
import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { EmptyState } from "@/components/sharedUI/functionalComponent/feedback/EmptyState";
import { Button } from "@/components/ui/button";
import { QUERY_KEYS } from "@/lib/constants/query-keys";
import { buildRoute, ROUTES } from "@/lib/constants/routes";
import { formatRelativeTime } from "@/lib/formatters";

import { fetchInvestigations } from "../services/investigation.service";

export function InvestigationIndexScreen() {
  const { data } = useQuery({
    queryKey: QUERY_KEYS.investigations.all,
    queryFn: ({ signal }) => fetchInvestigations(signal),
  });

  const investigations = data ?? [];

  return (
    <div className="pointer-events-none absolute inset-0 flex items-start justify-center p-6">
      <GlassPanel className="pointer-events-auto flex w-full max-w-xl flex-col overflow-hidden">
        <SectionHeader
          title="Investigations"
          trailing={
            <span className="font-mono text-[10px] text-muted-foreground">
              {investigations.length}
            </span>
          }
        />

        <div className="max-h-[60vh] overflow-y-auto px-2 pb-2">
          {investigations.length === 0 ? (
            <EmptyState
              icon={ScanSearch}
              title="No investigations yet"
              description="Select imagery on Mission Command and press Investigate to open a workspace."
              action={
                <Button asChild size="sm" variant="outline">
                  <Link href={ROUTES.MISSION_COMMAND}>
                    <Globe />
                    Go to Mission Command
                  </Link>
                </Button>
              }
            />
          ) : (
            <ul className="flex flex-col gap-1">
              {investigations.map((investigation) => (
                <li key={investigation.id}>
                  <Link
                    href={buildRoute.investigationDetail(investigation.id)}
                    className="flex items-center gap-2 rounded-md border border-border-soft bg-surface-2/50 px-2 py-1.5 transition-colors duration-fast hover:border-aeris-teal/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  >
                    <Chip tone={investigation.status === "failed" ? "red" : "teal"}>
                      {investigation.status}
                    </Chip>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-medium text-foreground">
                        {investigation.name}
                      </span>
                      <span className="block truncate font-mono text-[10px] text-muted-foreground">
                        {investigation.areaOfInterestName} · trace {investigation.traceId}
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                      {formatRelativeTime(investigation.updatedAt)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </GlassPanel>
    </div>
  );
}
