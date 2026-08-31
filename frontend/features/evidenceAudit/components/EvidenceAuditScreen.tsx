// features/evidenceAudit/components/EvidenceAuditScreen.tsx

"use client";

import { 
  FileSearch, 
  ChevronDown, 
  ChevronRight, 
  AlertTriangle, 
  Layers, 
  Activity, 
  FileText, 
  Map as MapIcon,
  ExternalLink 
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { GlassPanel } from "@/components/sharedUI/dumbComponent/GlassPanel";
import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { GlowDot } from "@/components/sharedUI/dumbComponent/GlowDot";
import { EmptyState } from "@/components/sharedUI/functionalComponent/feedback/EmptyState";
import { ErrorState } from "@/components/sharedUI/functionalComponent/feedback/ErrorState";
import { PanelSkeleton } from "@/components/sharedUI/functionalComponent/feedback/PanelSkeleton";
import { Button } from "@/components/ui/button";
import { CONFIDENCE_BAND_ORDER, CONFIDENCE_BANDS } from "@/lib/constants/evidence-audit";
import { MODEL_ORDER, SPECIALIST_MODELS } from "@/lib/constants/models";
import { buildRoute } from "@/lib/constants/routes";
import { formatPercentage, formatRelativeTime, formatBytes, formatGroundSampleDistance } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import { useEvidenceAudit } from "../hooks/use-evidence-audit";
import type { AuditedClaim, AuditEvidenceItem } from "../types/evidence-audit.types";

export function EvidenceAuditScreen() {
  const audit = useEvidenceAudit();

  // Group claims by investigation
  const groupedClaims = audit.claims.reduce((groups, claim) => {
    if (!groups[claim.investigationId]) {
      groups[claim.investigationId] = {
        investigationId: claim.investigationId,
        investigationName: claim.investigationName,
        investigationStatus: claim.investigationStatus,
        areaOfInterestName: claim.areaOfInterestName,
        traceId: claim.traceStepId.split("-")[0] ?? "unknown", // Approximate trace ID for display
        claims: [],
      };
    }
    groups[claim.investigationId].claims.push(claim);
    return groups;
  }, {} as Record<string, { investigationId: string; investigationName: string; investigationStatus: "draft" | "running" | "ready" | "failed"; areaOfInterestName: string; traceId: string; claims: AuditedClaim[] }>);

  const groups = Object.values(groupedClaims);

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
            <PanelSkeleton rowCount={8} rowHeight={86} />
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
            <div className="overflow-y-auto p-3">
              <div className="flex flex-col gap-4">
                {groups.map((group) => (
                  <InvestigationGroup key={group.investigationId} group={group} />
                ))}
              </div>
            </div>
          )}
        </GlassPanel>
      </div>
    </div>
  );
}

function InvestigationGroup({ group }: { group: { investigationId: string; investigationName: string; investigationStatus: "draft" | "running" | "ready" | "failed"; areaOfInterestName: string; traceId: string; claims: AuditedClaim[] } }) {
  const [isExpanded, setIsExpanded] = useState(true);

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 rounded-md bg-surface-2/30 px-3 py-2 text-left transition-colors hover:bg-surface-2/60"
      >
        {isExpanded ? <ChevronDown className="size-4 opacity-50" /> : <ChevronRight className="size-4 opacity-50" />}
        <div className="flex flex-1 items-center gap-3">
          <span className="font-semibold text-sm">{group.investigationName}</span>
          <GlowDot 
            tone={group.investigationStatus === "ready" ? "green" : group.investigationStatus === "failed" ? "red" : group.investigationStatus === "running" ? "blue" : "neutral"} 
            isPulsing={group.investigationStatus === "running"} 
          />
          <span className="text-xs text-muted-foreground uppercase tracking-widest">{group.investigationStatus}</span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[10px] text-muted-foreground">
          <span>{group.areaOfInterestName}</span>
          <span>·</span>
          <span>{group.claims.length} {group.claims.length === 1 ? "claim" : "claims"}</span>
          <span>·</span>
          <span>trace {group.traceId.slice(0, 6)}</span>
        </div>
      </button>

      {isExpanded ? (
        <div className="flex flex-col gap-3 pl-6 pr-2">
          {/* Primary claims first */}
          {group.claims.filter(c => c.isPrimary).map(claim => (
            <ClaimCard key={claim.claimId} claim={claim} />
          ))}
          {/* Then supporting claims */}
          {group.claims.filter(c => !c.isPrimary).map(claim => (
            <ClaimCard key={claim.claimId} claim={claim} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ClaimCard({ claim }: { claim: AuditedClaim }) {
  const [isExpanded, setIsExpanded] = useState(claim.isPrimary);
  const model = SPECIALIST_MODELS[claim.modelId];
  
  const hasEvidence = claim.evidenceCount > 0;
  
  const confidenceTone = claim.confidence === null ? "neutral" : claim.confidence >= 0.85 ? "green" : claim.confidence >= 0.6 ? "amber" : "red";
  const confidenceColor = claim.confidence === null ? "bg-muted" : claim.confidence >= 0.85 ? "bg-aeris-green" : claim.confidence >= 0.6 ? "bg-aeris-amber" : "bg-aeris-red";

  return (
    <div className={cn("flex flex-col rounded-md border bg-surface/50 transition-colors duration-fast", 
      claim.isPrimary ? "border-aeris-teal/20" : "border-border-soft",
      isExpanded ? "shadow-md" : "hover:border-border"
    )}>
      <button 
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-start gap-3 p-3 text-left w-full"
      >
        <div className="pt-0.5">
          {isExpanded ? <ChevronDown className="size-4 opacity-50" /> : <ChevronRight className="size-4 opacity-50" />}
        </div>
        
        <div className="flex-1 flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            {claim.isPrimary && (
              <Chip tone="teal" className="text-[9px]">PRIMARY</Chip>
            )}
            {!hasEvidence && (
              <Chip tone="amber" className="text-[9px] flex items-center gap-1">
                <AlertTriangle className="size-3" /> NO EVIDENCE
              </Chip>
            )}
            <span className={cn("text-sm font-medium leading-snug", claim.isPrimary ? "text-foreground" : "text-muted-foreground")}>
              {claim.text}
            </span>
          </div>
          
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className="h-1.5 w-16 rounded-full bg-muted overflow-hidden">
                <div className={cn("h-full", confidenceColor)} style={{ width: claim.confidence ? `${claim.confidence * 100}%` : "0%" }} />
              </div>
              <span className={cn("font-mono text-[10px] tabular-nums", 
                claim.confidence === null ? "text-muted-foreground" : 
                claim.confidence >= 0.85 ? "text-aeris-green" : 
                claim.confidence >= 0.6 ? "text-aeris-amber" : "text-aeris-red"
              )}>
                {claim.confidence === null ? "N/A" : formatPercentage(claim.confidence)}
              </span>
            </div>
            
            <span className="font-mono text-[10px] text-muted-foreground/60">·</span>
            <span className="font-mono text-[10px] text-muted-foreground" title={model.selectionRationale}>
              {model.name} v{claim.modelVersion}
            </span>
            
            {!isExpanded && claim.evidenceCount > 0 && (
              <>
                <span className="font-mono text-[10px] text-muted-foreground/60">·</span>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {claim.evidenceCount} evidence items
                </span>
              </>
            )}
          </div>
        </div>
      </button>

      {isExpanded && (
        <div className="flex flex-col gap-4 p-4 pt-0 border-t border-border-soft ml-7 mt-1">
          {/* Metrics */}
          {claim.metrics && claim.metrics.length > 0 && (
            <div className="flex flex-wrap gap-6 pt-3">
              {claim.metrics.map(metric => (
                <div key={metric.label} className="flex flex-col">
                  <div className="flex items-baseline gap-1">
                    <span className="text-xl font-mono tabular-nums tracking-tight">
                      {metric.direction === "increase" ? "+" : metric.direction === "decrease" ? "-" : ""}
                      {metric.value.toFixed(metric.precision)}
                    </span>
                    <span className="text-xs text-muted-foreground font-mono">{metric.unit}</span>
                  </div>
                  <span className="text-[10px] text-muted-foreground uppercase tracking-widest">{metric.label}</span>
                </div>
              ))}
            </div>
          )}

          {/* Evidence List */}
          {claim.evidenceItems && claim.evidenceItems.length > 0 && (
            <div className="flex flex-col gap-2 pt-2">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground/80 font-mono">Supporting Evidence</span>
              <div className="flex flex-col gap-1.5">
                {claim.evidenceItems.map(item => (
                  <EvidenceItemRow key={item.id} item={item} />
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4 pt-2">
            {/* Model Reasoning */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground/80 font-mono">Why This Model</span>
              <p className="text-[11px] leading-relaxed text-muted-foreground italic border-l-2 border-border-soft pl-2">
                "{model.selectionRationale}"
              </p>
            </div>
            
            {/* Model Limitations */}
            <div className="flex flex-col gap-1.5">
              <span className="text-[10px] uppercase tracking-widest text-aeris-amber/80 font-mono flex items-center gap-1">
                <AlertTriangle className="size-3" /> Limitations
              </span>
              <p className="text-[11px] leading-relaxed text-muted-foreground border-l-2 border-aeris-amber/20 pl-2">
                {model.limitations}
              </p>
            </div>
          </div>

          <div className="flex items-end justify-between pt-2">
            <div className="flex flex-col gap-1.5">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground/80 font-mono">Source Scenes</span>
              <div className="flex flex-wrap gap-1.5">
                {claim.sourceSceneIds.map(sceneId => (
                  <Chip key={sceneId} tone="neutral" className="bg-surface/50">{sceneId}</Chip>
                ))}
              </div>
            </div>
            
            <Button asChild size="sm" variant="secondary" className="h-7 text-xs font-mono">
              <Link href={buildRoute.investigationDetail(claim.investigationId)}>
                <ExternalLink className="mr-2 size-3" />
                Open Investigation
              </Link>
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function EvidenceItemRow({ item }: { item: AuditEvidenceItem }) {
  const Icon = getEvidenceIcon(item.kind);
  
  return (
    <div className="flex items-center justify-between rounded-sm border border-border-soft bg-surface-2/20 px-2.5 py-1.5">
      <div className="flex items-center gap-2.5">
        <Icon className="size-3.5 text-muted-foreground/70" />
        <span className="text-xs font-medium text-muted-foreground">{item.title}</span>
      </div>
      <div className="flex items-center gap-4 font-mono text-[10px] text-muted-foreground/70 tabular-nums">
        {item.areaHectares !== null && (
          <span>{item.areaHectares.toFixed(1)} ha</span>
        )}
        {item.confidence !== null && (
          <span>conf {formatPercentage(item.confidence)}</span>
        )}
      </div>
    </div>
  );
}

function getEvidenceIcon(kind: string) {
  switch (kind) {
    case "change-mask":
      return Layers;
    case "detection":
      return MapIcon;
    case "statistic":
      return Activity;
    case "cross-modal":
      return FileText;
    default:
      return Layers;
  }
}
