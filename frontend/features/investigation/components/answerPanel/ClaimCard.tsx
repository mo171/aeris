// features/investigation/components/answerPanel/ClaimCard.tsx — one claim, with its numbers, confidence and evidence.
//
// what  : Renders a claim as a card: the statement, its computed metrics, its confidence, and chips for
//         the evidence supporting it.
// where : Rendered by AnswerPanel, once for the primary claim and once per supporting claim.
// how   : Hovering anywhere on the card spotlights its evidence on the scene, and leaving clears it. That
//         is the product thesis made operable — the claim and the pixels behind it are one gesture apart,
//         so an operator can check the answer rather than trusting it.
//
//         Hover rather than click for the spotlight, because checking should cost nothing. Click is
//         reserved for framing the camera, which is a bigger commitment and should be deliberate.
//
//         A claim with no evidence says so explicitly instead of rendering an empty row. An unsupported
//         claim is a meaningful state in an evidence-first system and hiding it would defeat the point.

"use client";

import { Crosshair } from "lucide-react";

import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { ConfidenceMeter } from "@/components/sharedUI/functionalComponent/dataDisplay/ConfidenceMeter";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { Claim, EvidenceItem } from "../../types/evidence.types";
import { MetricStat } from "./MetricStat";

interface ClaimCardProps {
  claim: Claim;
  evidence: EvidenceItem[];
  isSpotlit: boolean;
  onSpotlight: (claimId: string | null) => void;
  onFocusEvidence: (claim: Claim) => void;
  className?: string;
}

export function ClaimCard({
  claim,
  evidence,
  isSpotlit,
  onSpotlight,
  onFocusEvidence,
  className,
}: ClaimCardProps) {
  return (
    <article
      onPointerEnter={() => onSpotlight(claim.id)}
      onPointerLeave={() => onSpotlight(null)}
      onFocus={() => onSpotlight(claim.id)}
      onBlur={() => onSpotlight(null)}
      className={cn(
        "rounded-md border bg-surface-2/60 p-3 transition-colors duration-base ease-expo",
        isSpotlit ? "border-aeris-teal/60 bg-surface-2" : "border-border-soft",
        className,
      )}
    >
      <header className="flex items-start justify-between gap-2">
        <p
          className={cn(
            "text-sm leading-snug",
            claim.isPrimary ? "font-medium text-foreground" : "text-muted-foreground",
          )}
        >
          {claim.text}
        </p>

        {evidence.length > 0 ? (
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            aria-label="Frame this evidence on the scene"
            onClick={() => onFocusEvidence(claim)}
            className="shrink-0"
          >
            <Crosshair />
          </Button>
        ) : null}
      </header>

      {claim.metrics.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-3">
          {claim.metrics.map((metric) => (
            <MetricStat key={metric.label} metric={metric} />
          ))}
        </div>
      ) : null}

      <footer className="mt-3 flex flex-col gap-2 border-t border-border-soft pt-2">
        <ConfidenceMeter value={claim.confidence} />

        <div className="flex flex-wrap items-center gap-1">
          {evidence.length === 0 ? (
            <span className="aeris-technical text-aeris-amber">No supporting evidence</span>
          ) : (
            evidence.map((item) => (
              <Chip key={item.id} tone="blue" title={item.title}>
                {item.title}
              </Chip>
            ))
          )}
        </div>

        <span
          className="font-mono text-[10px] text-muted-foreground/70"
          title="The model and version that produced this claim"
        >
          {claim.modelId}@{claim.modelVersion}
        </span>
      </footer>
    </article>
  );
}
