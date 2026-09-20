"use client";

import { useMemo, useState } from "react";
import {
  Sparkles,
  Layers,
  Fingerprint,
  Database,
  GitBranch,
  ExternalLink,
  Maximize2,
  X,
  Link2,
  Microscope,
  CheckCircle2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Chip, type ChipTone } from "@/components/sharedUI/dumbComponent/Chip";
import { cn } from "@/lib/utils";
import type { Claim, EvidenceItem } from "../../types/evidence.types";
import type { AnalysisRun } from "../../types/analysis.types";
import mumbaiRunData from "@/mock/data/mumbai-run-data.json";

interface EvidenceFigure {
  id: string;
  title: string;
  caption: string;
  imageUrl: string;
  kind: "index-map" | "mask-overlay" | "sar-backscatter" | "cross-modal";
  traceStepId: string;
  layerId: string | null;
  areaHectares: number | null;
  model: string;
  stage: string;
}

const KIND_TONE: Record<EvidenceFigure["kind"], ChipTone> = {
  "index-map": "green",
  "mask-overlay": "amber",
  "sar-backscatter": "blue",
  "cross-modal": "teal",
};

const KIND_LABEL: Record<EvidenceFigure["kind"], string> = {
  "index-map": "Index Map",
  "mask-overlay": "Mask Overlay",
  "sar-backscatter": "SAR Backscatter",
  "cross-modal": "Late Fusion",
};

interface EvidenceTabProps {
  currentRun: AnalysisRun | null;
  claimsById: Record<string, Claim>;
  evidenceById: Record<string, EvidenceItem>;
  onFocusEvidence?: (claim: Claim) => void;
  onInspectStep?: (stepId: string) => void;
  onFocusLayer?: (layerId: string) => void;
}

export function EvidenceTab({
  currentRun,
  claimsById,
  evidenceById,
  onFocusEvidence,
  onInspectStep,
  onFocusLayer,
}: EvidenceTabProps) {
  const [selectedFigure, setSelectedFigure] = useState<EvidenceFigure | null>(null);

  const figures: EvidenceFigure[] = useMemo(() => {
    return (mumbaiRunData.figures as EvidenceFigure[]) ?? [];
  }, []);

  if (!currentRun || currentRun.claimIds.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-6 text-center">
        <Microscope className="mb-2 size-8 text-aeris-teal/40 animate-pulse" />
        <h4 className="text-xs font-semibold text-foreground">No Analysis Evidence Generated Yet</h4>
        <p className="mt-1 max-w-xs text-[11px] text-muted-foreground leading-relaxed">
          Select satellite acquisitions and run an investigation. AERIS will stream multi-modal evidence products, index maps, and cross-sensor agreement partitions here.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 pb-6">
      {/* ── Section 1: System-Generated Evidence Products Gallery ───────────────────────── */}
      <section className="flex flex-col gap-2.5">
        <div className="flex items-center justify-between border-b border-border-soft pb-1.5">
          <div className="flex items-center gap-1.5">
            <Microscope className="size-3.5 text-aeris-teal" />
            <h3 className="text-[11px] font-semibold tracking-wide text-foreground uppercase">
              Generated Evidence Products
            </h3>
          </div>
          <span className="rounded-full bg-aeris-teal/10 px-1.5 py-0.5 font-mono text-[9px] font-medium text-aeris-teal">
            {figures.length} figures
          </span>
        </div>

        <p className="text-[10px] text-muted-foreground">
          Analytical raster figures and classification masks generated from raw Sentinel-1A and Sentinel-2B passes.
        </p>

        <div className="flex flex-col gap-2">
          {figures.map((figure) => {
            const tone = KIND_TONE[figure.kind] ?? "neutral";
            const kindLabel = KIND_LABEL[figure.kind] ?? figure.kind;

            return (
              <div
                key={figure.id}
                className="group/card flex flex-col gap-2 rounded-md border border-border-soft bg-surface-2/40 p-2.5 transition-colors hover:border-border hover:bg-surface-2/70"
              >
                <div className="flex items-start gap-2.5">
                  {/* Thumbnail with click-to-enlarge */}
                  <button
                    type="button"
                    onClick={() => setSelectedFigure(figure)}
                    title="Click to enlarge figure"
                    className="relative size-14 shrink-0 overflow-hidden rounded-sm border border-border-soft bg-surface-3 transition-transform hover:scale-[1.02] focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  >
                    <img
                      src={figure.imageUrl}
                      alt={figure.title}
                      className="size-full object-cover"
                      loading="lazy"
                    />
                    <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover/card:opacity-100">
                      <Maximize2 className="size-3.5 text-white" />
                    </div>
                  </button>

                  {/* Figure metadata */}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Chip tone={tone}>{kindLabel}</Chip>
                      <button
                        type="button"
                        onClick={() => onInspectStep?.(figure.traceStepId)}
                        className="rounded-xs bg-surface-3 px-1 font-mono text-[9px] text-muted-foreground hover:text-aeris-teal transition-colors"
                      >
                        Step {figure.stage}
                      </button>
                    </div>

                    <h4 className="mt-1 truncate text-[11px] font-medium text-foreground">
                      {figure.title}
                    </h4>

                    {figure.areaHectares !== null ? (
                      <span className="mt-0.5 block font-mono text-[10px] text-aeris-teal font-medium">
                        {figure.areaHectares.toFixed(1)} ha detected
                      </span>
                    ) : null}

                    <p className="mt-0.5 line-clamp-2 text-[10px] text-muted-foreground leading-snug">
                      {figure.caption}
                    </p>
                  </div>
                </div>

                {/* Card Action footer */}
                <div className="flex items-center justify-between border-t border-border-soft/60 pt-1.5">
                  <span className="font-mono text-[9px] text-muted-foreground/80 truncate">
                    {figure.model}
                  </span>

                  <div className="flex items-center gap-1">
                    {figure.layerId ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-5 px-1.5 text-[9px] text-aeris-teal hover:bg-aeris-teal/10 hover:text-aeris-teal"
                        onClick={() => onFocusLayer?.(figure.layerId!)}
                      >
                        <Layers className="mr-1 size-2.5" />
                        Focus Layer
                      </Button>
                    ) : null}

                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-5 px-1.5 text-[9px] text-muted-foreground hover:text-foreground"
                      onClick={() => setSelectedFigure(figure)}
                    >
                      <Maximize2 className="mr-1 size-2.5" />
                      Inspect
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── Section 2: Asserted Claims & Provenance Ledger ──────────────────────────────── */}
      <section className="flex flex-col gap-2.5 border-t border-border-soft pt-4">
        <div className="flex items-center justify-between border-b border-border-soft pb-1.5">
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="size-3.5 text-aeris-teal" />
            <h3 className="text-[11px] font-semibold tracking-wide text-foreground uppercase">
              Asserted Claims &amp; Provenance
            </h3>
          </div>
          <span className="font-mono text-[9px] text-muted-foreground">
            {currentRun.claimIds.length} claims
          </span>
        </div>

        <div className="flex flex-col gap-3">
          {currentRun.claimIds.map((claimId) => {
            const claim = claimsById[claimId];
            if (!claim) return null;

            const evidences = claim.evidenceIds
              .map((id) => evidenceById[id])
              .filter((e): e is EvidenceItem => Boolean(e));

            return (
              <div
                key={claim.id}
                className="flex flex-col gap-2 rounded-md border border-border-soft bg-surface-1/40 p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-[11px] font-medium text-foreground leading-snug">
                    {claim.text}
                  </span>
                </div>

                <div className="mt-1 flex flex-col gap-2 border-l-2 border-aeris-teal/30 pl-2.5">
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    <GitBranch className="size-3 text-aeris-teal" />
                    <button
                      type="button"
                      className="hover:text-aeris-teal hover:underline transition-colors font-mono"
                      onClick={() => onInspectStep?.(claim.traceStepId)}
                    >
                      Step {claim.traceStepId}
                    </button>
                    <span className="text-muted-foreground/50">·</span>
                    <span className="font-mono">{claim.modelId}@{claim.modelVersion}</span>
                  </div>

                  {evidences.length > 0 ? (
                    <div className="flex flex-col gap-1.5">
                      {evidences.map((evidence) => (
                        <div
                          key={evidence.id}
                          className="flex items-start gap-2 rounded bg-surface-2/50 p-1.5"
                        >
                          {evidence.figureUrl ? (
                            <img
                              src={evidence.figureUrl}
                              alt=""
                              className="size-8 shrink-0 rounded border border-border-soft object-cover"
                              loading="lazy"
                            />
                          ) : (
                            <Fingerprint className="mt-0.5 size-3 shrink-0 text-muted-foreground" />
                          )}

                          <div className="min-w-0 flex-1">
                            <span className="block truncate text-[10px] font-medium text-foreground/90">
                              {evidence.title}
                            </span>

                            {evidence.areaHectares !== null ? (
                              <span className="font-mono text-[9px] text-aeris-teal">
                                {evidence.areaHectares.toFixed(1)} ha
                              </span>
                            ) : null}

                            {evidence.layerId && (
                              <div className="mt-0.5 flex items-center gap-1 text-[9px] text-muted-foreground">
                                <Layers className="size-2.5" />
                                <button
                                  type="button"
                                  className="hover:text-aeris-teal hover:underline transition-colors font-mono"
                                  onClick={() => onFocusLayer?.(evidence.layerId!)}
                                >
                                  {evidence.layerId}
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[10px] text-muted-foreground italic">
                      No direct evidence items attached.
                    </div>
                  )}
                </div>

                <div className="mt-1 flex justify-end">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-5 px-2 text-[9px] text-aeris-teal hover:bg-aeris-teal/10 hover:text-aeris-teal"
                    onClick={() => onFocusEvidence?.(claim)}
                  >
                    <Link2 className="mr-1 size-2.5" />
                    Locate Evidence
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── Modal Lightbox for Figure Inspection ────────────────────────────────────────── */}
      {selectedFigure ? (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
          onClick={() => setSelectedFigure(null)}
        >
          <div
            className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-lg border border-border-soft bg-zinc-950 p-4 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-start justify-between gap-3 border-b border-border-soft pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <Chip tone={KIND_TONE[selectedFigure.kind] ?? "neutral"}>
                    {KIND_LABEL[selectedFigure.kind] ?? selectedFigure.kind}
                  </Chip>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    Step {selectedFigure.stage} · {selectedFigure.model}
                  </span>
                </div>
                <h3 className="mt-1 text-sm font-semibold text-zinc-100">
                  {selectedFigure.title}
                </h3>
              </div>

              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                onClick={() => setSelectedFigure(null)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </Button>
            </div>

            {/* Modal Body: Image Preview */}
            <div className="my-3 flex flex-1 items-center justify-center overflow-hidden rounded border border-zinc-800 bg-zinc-900/60 p-2">
              <img
                src={selectedFigure.imageUrl}
                alt={selectedFigure.title}
                className="max-h-[55vh] w-auto max-w-full rounded object-contain"
              />
            </div>

            {/* Modal Footer: Caption & Actions */}
            <div className="flex flex-col gap-2 pt-2 text-[11px] text-zinc-300">
              <p className="leading-relaxed">{selectedFigure.caption}</p>

              <div className="flex items-center justify-between border-t border-border-soft pt-2">
                {selectedFigure.areaHectares !== null ? (
                  <span className="font-mono text-xs font-semibold text-aeris-teal">
                    Area Extent: {selectedFigure.areaHectares.toFixed(1)} hectares
                  </span>
                ) : (
                  <span className="font-mono text-xs text-muted-foreground">
                    Cross-Modal Analytical Consensus
                  </span>
                )}

                <div className="flex items-center gap-2">
                  {selectedFigure.layerId ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs border-aeris-teal/40 text-aeris-teal hover:bg-aeris-teal/10"
                      onClick={() => {
                        onFocusLayer?.(selectedFigure.layerId!);
                        setSelectedFigure(null);
                      }}
                    >
                      <Layers className="mr-1 size-3" />
                      Highlight on Globe
                    </Button>
                  ) : null}

                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs text-zinc-300 hover:text-white"
                    onClick={() => {
                      const features = "width=1000,height=800,menubar=no,toolbar=no,location=no,status=no";
                      window.open(`/figures?figureId=${selectedFigure.id}`, `aeris-figure-${selectedFigure.id}`, features);
                    }}
                  >
                    <ExternalLink className="mr-1 size-3" />
                    Popout Window
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
