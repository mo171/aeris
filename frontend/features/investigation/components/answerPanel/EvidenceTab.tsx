"use client";

import { useMemo } from "react";
import { Link2, Sparkles, Layers, Fingerprint, Database, GitBranch } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Claim, EvidenceItem } from "../../types/evidence.types";
import type { AnalysisRun } from "../../types/analysis.types";

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
  if (!currentRun || currentRun.claimIds.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-6 text-center">
        <Sparkles className="mb-2 size-6 text-muted-foreground/30" />
        <p className="text-xs text-muted-foreground">
          No claims to show evidence for yet. Run an analysis to see its provenance chain.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {currentRun.claimIds.map((claimId) => {
        const claim = claimsById[claimId];
        if (!claim) return null;

        const evidences = claim.evidenceIds
          .map((id) => evidenceById[id])
          .filter((e): e is EvidenceItem => Boolean(e));

        return (
          <div key={claim.id} className="flex flex-col gap-2 rounded-md border border-border-soft p-3">
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-medium text-foreground">{claim.text}</span>
            </div>

            <div className="mt-2 flex flex-col gap-2 border-l-2 border-aeris-teal/20 pl-3">
              <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                <GitBranch className="size-3" />
                <button
                  type="button"
                  className="hover:text-aeris-teal hover:underline transition-colors"
                  onClick={() => onInspectStep?.(claim.traceStepId)}
                >
                  Step {claim.traceStepId}
                </button>
                <span className="text-muted-foreground/50">·</span>
                <span>{claim.modelId}@{claim.modelVersion}</span>
              </div>

              {evidences.length > 0 ? (
                <div className="flex flex-col gap-1.5">
                  {evidences.map((evidence) => (
                    <div key={evidence.id} className="flex flex-col gap-1 rounded bg-surface-2/40 p-2">
                      <div className="flex items-center gap-2 text-[10px]">
                        <Fingerprint className="size-3 text-muted-foreground" />
                        <span className="font-medium text-foreground/80">{evidence.title}</span>
                      </div>
                      
                      {evidence.layerId && (
                        <div className="flex items-center gap-2 text-[10px] text-muted-foreground mt-1">
                          <Layers className="size-3" />
                          <button
                            type="button"
                            className="hover:text-aeris-teal hover:underline transition-colors"
                            onClick={() => onFocusLayer?.(evidence.layerId!)}
                          >
                            Layer {evidence.layerId}
                          </button>
                        </div>
                      )}

                      {evidence.sourceSceneIds.length > 0 && (
                        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                          <Database className="size-3" />
                          <span>Sources: {evidence.sourceSceneIds.join(", ")}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-[10px] text-muted-foreground italic">No direct evidence items attached.</div>
              )}
            </div>
            
            <div className="mt-2 flex justify-end">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-[10px]"
                onClick={() => onFocusEvidence?.(claim)}
              >
                <Link2 className="mr-1 size-3" />
                Locate Evidence
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
