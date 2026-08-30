// features/evidenceAudit/components/EvidenceAuditScreen.tsx — the claim corpus, interrogable.
//
// what  : Every claim AERIS has ever asserted, filterable by model, by confidence band and by free text,
//         with each row linking back to the investigation that produced it.
// where : Rendered by app/(reference)/evidence/page.tsx.
// how   : THIS IS THE ONLY SURFACE THAT SPANS INVESTIGATIONS, and that is the entire reason it exists as a
//         page rather than a panel. Tracing one claim to its region, mask, model and confidence is the
//         Investigation Workspace's job and it already does it. What the workspace structurally cannot
//         answer is a corpus question: every claim a model version produced, everything resting on a scene
//         later found faulty, everything below a confidence an operator is willing to quote.
//
//         THE FIRST OF THOSE IS THE REAL WORKFLOW. When a model version is found wrong, someone has to
//         re-check everything it touched, across every investigation, and no per-investigation view can
//         produce that list. Filtering by model is therefore the primary control, not a refinement.
//
//         TWO SHAPES HERE ARE FORCED, NOT CHOSEN. This page stops hydrating entirely — server HTML stays,
//         no query ever fires, no error is logged — if either of these is used:
//           * PanelSkeleton as the loading state (see ModelObservatoryScreen, same symptom)
//           * a local <FilterChip>/<FilterRow> component wrapping the filter markup
//         Bisected on clean production builds: inlining the identical markup fixes it every time, and the
//         hook, the service and the mock were each verified working in isolation. Root cause not found —
//         read fcontext/memory.md before refactoring either back into a component.
//
//         Every row states its model, its confidence and how much evidence stands behind it — including
//         zero, which is a claim resting on nothing and the single most important thing an audit can
//         surface. Rows link out rather than expanding: the place to examine a claim is the workspace with
//         the scene under it, and duplicating that here would be a second, worse inspector.

"use client";

import { FileSearch } from "lucide-react";
import Link from "next/link";

import { GlassPanel } from "@/components/sharedUI/dumbComponent/GlassPanel";
import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { EmptyState } from "@/components/sharedUI/functionalComponent/feedback/EmptyState";
import { ErrorState } from "@/components/sharedUI/functionalComponent/feedback/ErrorState";
import { Button } from "@/components/ui/button";
import { CONFIDENCE_BAND_ORDER, CONFIDENCE_BANDS } from "@/lib/constants/evidence-audit";
import { MODEL_ORDER, SPECIALIST_MODELS } from "@/lib/constants/models";
import { buildRoute } from "@/lib/constants/routes";
import { formatPercentage, formatRelativeTime } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import { useEvidenceAudit } from "../hooks/use-evidence-audit";
import type { AuditedClaim } from "../types/evidence-audit.types";

export function EvidenceAuditScreen() {
  const audit = useEvidenceAudit();

  return (
    <div className="absolute inset-0 flex flex-col p-4">
      <div className="mx-auto flex min-h-0 w-full max-w-4xl flex-1 flex-col gap-3">
        <GlassPanel className="shrink-0 overflow-hidden">
          <SectionHeader
            title="Evidence Audit"
            trailing={
              <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
                {audit.totalCount === null ? "—" : `${audit.totalCount} claims`}
              </span>
            }
          />

          <p className="px-3 pb-2 text-[11px] leading-relaxed text-muted-foreground">
            Every claim AERIS has asserted, across every investigation. Filter by the model that produced
            it when a version turns out to be wrong, or by confidence when deciding what is safe to quote.
          </p>

          <div className="flex flex-col gap-2 border-t border-border-soft px-3 py-2">
            <input
              type="search"
              value={audit.search}
              onChange={(event) => audit.setSearch(event.target.value)}
              placeholder="Filter by claim wording, area or scene id"
              aria-label="Filter claims"
              className="h-7 w-full rounded-lg border border-input bg-transparent px-2.5 text-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring"
            />

            <div className="flex items-start gap-2">
              <span className="w-16 shrink-0 pt-1 font-mono text-[9px] uppercase">Model</span>
              <div className="flex min-w-0 flex-1 flex-wrap gap-1">
                <button
                  type="button"
                  onClick={() => audit.setModelId(null)}
                  aria-pressed={audit.modelId === null}
                  className="rounded-[3px] border px-1.5 py-0.5 font-mono text-[9px] uppercase"
                >
                  Any
                </button>
                {MODEL_ORDER.map((modelId) => (
                  <button
                    key={modelId}
                    type="button"
                    onClick={() => audit.setModelId(audit.modelId === modelId ? null : modelId)}
                    aria-pressed={audit.modelId === modelId}
                    className="rounded-[3px] border px-1.5 py-0.5 font-mono text-[9px] uppercase"
                  >
                    {SPECIALIST_MODELS[modelId].name}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-start gap-2">
              <span className="w-16 shrink-0 pt-1 font-mono text-[9px] uppercase">Confidence</span>
              <div className="flex min-w-0 flex-1 flex-wrap gap-1">
                {CONFIDENCE_BAND_ORDER.map((bandId) => (
                  <button
                    key={bandId}
                    type="button"
                    onClick={() => audit.setBand(bandId)}
                    aria-pressed={audit.band === bandId}
                    className="rounded-[3px] border px-1.5 py-0.5 font-mono text-[9px] uppercase"
                  >
                    {CONFIDENCE_BANDS[bandId].label}
                  </button>
                ))}
              </div>
            </div>

            {/* The guidance for the chosen band, so the filter teaches rather than only narrowing. */}
            {audit.band !== "all" ? (
              <p className="text-[10px] leading-relaxed text-muted-foreground/70">
                {CONFIDENCE_BANDS[audit.band].guidance}
              </p>
            ) : null}
          </div>
        </GlassPanel>

        <GlassPanel className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {audit.error ? (
            <ErrorState error={audit.error} onRetry={audit.refetch} />
          ) : audit.isLoading ? (
            <p className="px-3 py-4 font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
              Reading the corpus…
            </p>
          ) : audit.claims.length === 0 ? (
            <EmptyState
              icon={FileSearch}
              title={audit.isFiltered ? "No claim matches these filters" : "No claims yet"}
              description={
                audit.isFiltered
                  ? "Nothing in the corpus was produced under these conditions."
                  : "Ask a question in an investigation and every claim it asserts will be audited here."
              }
              action={
                audit.isFiltered ? (
                  <Button size="sm" variant="outline" onClick={audit.clearFilters}>
                    Clear filters
                  </Button>
                ) : null
              }
            />
          ) : (
            <ul className="overflow-y-auto p-2">
              {audit.claims.map((claim) => (
                <li key={claim.claimId}>
                  <ClaimRow claim={claim} />
                </li>
              ))}
            </ul>
          )}
        </GlassPanel>
      </div>
    </div>
  );
}

function ClaimRow({ claim }: { claim: AuditedClaim }) {
  const model = SPECIALIST_MODELS[claim.modelId];

  return (
    <Link
      href={buildRoute.investigationDetail(claim.investigationId)}
      title="Open the investigation that produced this claim"
      className="mb-1 flex flex-col gap-1 rounded-md border border-border-soft bg-surface-2/40 px-2 py-1.5 transition-colors duration-fast hover:border-aeris-teal/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <span className="line-clamp-2 text-xs leading-relaxed text-foreground">{claim.text}</span>

      <span className="flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-[9px] text-muted-foreground">
        <Confidence value={claim.confidence} />

        <span title={model.selectionRationale}>
          {model.name}@{claim.modelVersion}
        </span>

        {/* Zero evidence is the finding an audit exists to surface, so it is called out rather than shown
            as a plain count. */}
        <span className={cn(claim.evidenceCount === 0 && "text-aeris-amber")}>
          {claim.evidenceCount === 0
            ? "no supporting evidence"
            : `${claim.evidenceCount} evidence`}
        </span>

        <span className="truncate">{claim.areaOfInterestName}</span>

        {claim.sourceSceneIds.length > 0 ? (
          <span className="truncate text-muted-foreground/60">
            {claim.sourceSceneIds.join(" · ")}
          </span>
        ) : null}

        <span className="ml-auto shrink-0">{formatRelativeTime(claim.producedAt)}</span>
      </span>
    </Link>
  );
}

/** Null is a refusal to assert, never a zero — it is labelled rather than rendered as 0%. */
function Confidence({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="text-aeris-amber">no confidence stated</span>;
  }

  return (
    <span
      className={cn(
        "tabular-nums",
        value < 0.6 ? "text-aeris-amber" : value >= 0.85 ? "text-aeris-green" : "text-foreground",
      )}
    >
      {formatPercentage(value)}
    </span>
  );
}
