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
//         THE LOADING STATE IS PLAIN MARKUP, NOT PanelSkeleton — see ModelObservatoryScreen for the
//         reproduction. That skeleton stops these pages hydrating at all.
//
//         Every row states its model, its confidence and how much evidence stands behind it — including
//         zero, which is a claim resting on nothing and the single most important thing an audit can
//         surface. Rows link out rather than expanding: the place to examine a claim is the workspace with
//         the scene under it, and duplicating that here would be a second, worse inspector.

"use client";

import { FileSearch, LoaderCircle } from "lucide-react";
import Link from "next/link";

import { GlassPanel } from "@/components/sharedUI/dumbComponent/GlassPanel";
import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { VirtualizedList } from "@/components/sharedUI/functionalComponent/dataDisplay/VirtualizedList";
import { EmptyState } from "@/components/sharedUI/functionalComponent/feedback/EmptyState";
import { ErrorState } from "@/components/sharedUI/functionalComponent/feedback/ErrorState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CONFIDENCE_BAND_ORDER, CONFIDENCE_BANDS } from "@/lib/constants/evidence-audit";
import { MODEL_ORDER, SPECIALIST_MODELS, type ModelId } from "@/lib/constants/models";
import { buildRoute } from "@/lib/constants/routes";
import { formatPercentage, formatRelativeTime } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import { useEvidenceAudit } from "../hooks/use-evidence-audit";
import type { AuditedClaim } from "../types/evidence-audit.types";

const ESTIMATED_ROW_HEIGHT = 84;

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
            <Input
              type="search"
              value={audit.search}
              onChange={(event) => audit.setSearch(event.target.value)}
              placeholder="Filter by claim wording, area or scene id"
              aria-label="Filter claims"
              className="h-7 text-xs"
            />

            <FilterRow label="Model">
              <FilterChip
                isActive={audit.modelId === null}
                onClick={() => audit.setModelId(null)}
              >
                Any
              </FilterChip>
              {MODEL_ORDER.map((modelId) => (
                <FilterChip
                  key={modelId}
                  isActive={audit.modelId === modelId}
                  onClick={() => audit.setModelId(toggle(audit.modelId, modelId))}
                  title={SPECIALIST_MODELS[modelId].selectionRationale}
                >
                  {SPECIALIST_MODELS[modelId].name}
                </FilterChip>
              ))}
            </FilterRow>

            <FilterRow label="Confidence">
              {CONFIDENCE_BAND_ORDER.map((bandId) => (
                <FilterChip
                  key={bandId}
                  isActive={audit.band === bandId}
                  onClick={() => audit.setBand(bandId)}
                  title={CONFIDENCE_BANDS[bandId].guidance}
                >
                  {CONFIDENCE_BANDS[bandId].label}
                </FilterChip>
              ))}
            </FilterRow>

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
            <VirtualizedList
              items={audit.claims}
              estimateItemHeight={ESTIMATED_ROW_HEIGHT}
              getItemKey={(claim) => claim.claimId}
              renderItem={(claim) => <ClaimRow claim={claim} />}
              onEndReached={audit.fetchNextPage}
              className="p-2"
              footer={
                audit.isFetchingNextPage ? (
                  <div className="flex items-center justify-center py-2">
                    <LoaderCircle
                      className="size-3 animate-spin text-aeris-teal"
                      aria-hidden="true"
                    />
                  </div>
                ) : null
              }
            />
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

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <span className="w-16 shrink-0 pt-1 font-mono text-[9px] tracking-wide text-muted-foreground/50 uppercase">
        {label}
      </span>
      <div className="flex min-w-0 flex-1 flex-wrap gap-1">{children}</div>
    </div>
  );
}

function FilterChip({
  isActive,
  onClick,
  title,
  children,
}: {
  isActive: boolean;
  onClick: () => void;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={isActive}
      title={title}
      className={cn(
        "rounded-[3px] border px-1.5 py-0.5 font-mono text-[9px] tracking-wide uppercase transition-colors duration-fast focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
        isActive
          ? "border-aeris-teal/55 bg-aeris-teal/12 text-aeris-teal"
          : "border-border-soft text-muted-foreground hover:border-aeris-teal/35 hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/** Pressing the active model chip clears it, so the filter row needs no separate reset per model. */
function toggle(current: ModelId | null, pressed: ModelId): ModelId | null {
  return current === pressed ? null : pressed;
}
