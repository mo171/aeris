// features/investigation/components/answerPanel/AnswerPanel.tsx — the AERIS zone of the workspace.
//
// what  : Shows the current answer, its claims, its confidence and the evidence behind it, plus the
//         composer that asks the next question.
// where : The right zone of InvestigationScreen.
// how   : This is an answer SURFACE, not a transcript — a deliberate departure from Mission Command. On
//         page 1 the conversation is the subject; here the current answer is, because the operator is
//         looking at the scene it describes. Burying it under scrollback would make them hunt for the
//         thing the whole page is about, so prior runs collapse to a single line each and can be
//         reopened.
//
//         The claims carry the spotlight interaction, so hovering an answer dims the scene and raises the
//         geometry supporting it. That is the evidence-first principle made operable rather than stated.
//
//         A drawn region appears as a chip above the composer. The operator must be able to see that the
//         next question is scoped before they ask it — discovering it afterwards, from a surprisingly
//         narrow answer, is the kind of thing that destroys trust in a tool like this.

"use client";

import { Search, Sparkles } from "lucide-react";
import { useState } from "react";

import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { TypewriterText } from "@/components/sharedUI/dumbComponent/TypewriterText";
import { EmptyState } from "@/components/sharedUI/functionalComponent/feedback/EmptyState";
import { PromptComposer } from "@/components/sharedUI/functionalComponent/input/PromptComposer";
import { SectionHeader } from "@/components/sharedUI/dumbComponent/SectionHeader";
import { Button } from "@/components/ui/button";
import { formatDurationMs } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import { useInvestigationStore } from "../../store/investigation-store";
import type { AnalysisPlan, AnalysisRun } from "../../types/analysis.types";
import type { Claim, EvidenceItem } from "../../types/evidence.types";
import { ClaimCard } from "./ClaimCard";
import { InsufficientEvidenceCard } from "./InsufficientEvidenceCard";
import { InvestigatePlanSheet } from "./InvestigatePlanSheet";

const STARTER_PROMPTS: readonly string[] = [
  "What changed between these two observations?",
  "Has the built-up area increased?",
  "How much vegetation was lost?",
  "Does the SAR observation support this?",
];

interface AnswerPanelProps {
  runs: AnalysisRun[];
  isRunning: boolean;
  claimsById: Record<string, Claim>;
  evidenceById: Record<string, EvidenceItem>;
  activePlan: AnalysisPlan | null;
  onAsk: (query: string) => void;
  onStop: () => void;
  onInvestigate: (claimId: string) => void;
  onFocusEvidence: (claim: Claim) => void;
  onTogglePlanStep: (stepId: string) => void;
  onExecutePlan: () => void;
  onDismissPlan: () => void;
}

export function AnswerPanel({
  runs,
  isRunning,
  claimsById,
  evidenceById,
  activePlan,
  onAsk,
  onStop,
  onInvestigate,
  onFocusEvidence,
  onTogglePlanStep,
  onExecutePlan,
  onDismissPlan,
}: AnswerPanelProps) {
  const [draft, setDraft] = useState("");
  const spotlightClaimId = useInvestigationStore((state) => state.spotlightClaimId);
  const setSpotlightClaimId = useInvestigationStore((state) => state.setSpotlightClaimId);
  const drawnRegion = useInvestigationStore((state) => state.drawnRegion);
  const clearRegion = useInvestigationStore((state) => state.setDrawnRegion);

  const currentRun = runs.at(-1) ?? null;
  const priorRuns = runs.slice(0, -1);

  const submit = (prompt: string) => {
    const trimmed = prompt.trim();
    if (trimmed.length === 0) {
      return;
    }
    onAsk(trimmed);
    setDraft("");
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <SectionHeader
        title="AERIS"
        trailing={
          currentRun?.totalDurationMs != null ? (
            <span className="font-mono text-[10px] text-muted-foreground">
              {formatDurationMs(currentRun.totalDurationMs)}
            </span>
          ) : null
        }
      />

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {priorRuns.length > 0 ? (
          <ol className="mb-3 flex flex-col gap-1 border-b border-border-soft pb-2">
            {priorRuns.map((run) => (
              <li key={run.id}>
                <button
                  type="button"
                  onClick={() => submit(run.query)}
                  title="Ask this again"
                  className="w-full truncate rounded-sm text-left font-mono text-[11px] text-muted-foreground transition-colors duration-fast hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {run.query}
                </button>
              </li>
            ))}
          </ol>
        ) : null}

        {currentRun === null ? (
          <EmptyState
            icon={Sparkles}
            title="Ask about this scene"
            description="Draw a region to scope a question, or start with one of these."
            action={
              <div className="flex flex-col gap-1.5">
                {STARTER_PROMPTS.map((prompt) => (
                  <Button
                    key={prompt}
                    type="button"
                    size="sm"
                    variant="outline"
                    className="justify-start text-left"
                    onClick={() => submit(prompt)}
                  >
                    <Search />
                    <span className="truncate">{prompt}</span>
                  </Button>
                ))}
              </div>
            }
          />
        ) : (
          <div className="flex flex-col gap-3">
            {currentRun.answerText.length > 0 ? (
              <p className="text-sm leading-relaxed text-foreground">
                <TypewriterText
                  text={currentRun.answerText}
                  isStreaming={currentRun.status === "running"}
                />
              </p>
            ) : null}

            {currentRun.insufficientEvidence ? (
              <InsufficientEvidenceCard
                insufficientEvidence={currentRun.insufficientEvidence}
                onRemedy={submit}
              />
            ) : null}

            {currentRun.claimIds.map((claimId) => {
              const claim = claimsById[claimId];
              if (!claim) {
                return null;
              }

              return (
                <ClaimCard
                  key={claim.id}
                  claim={claim}
                  evidence={claim.evidenceIds
                    .map((evidenceId) => evidenceById[evidenceId])
                    .filter((item): item is EvidenceItem => Boolean(item))}
                  isSpotlit={spotlightClaimId === claim.id}
                  onSpotlight={setSpotlightClaimId}
                  onFocusEvidence={onFocusEvidence}
                />
              );
            })}

            {activePlan ? (
              <InvestigatePlanSheet
                plan={activePlan}
                onToggleStep={onTogglePlanStep}
                onExecute={onExecutePlan}
                onDismiss={onDismissPlan}
              />
            ) : currentRun.status === "complete" && currentRun.claimIds.length > 0 ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => onInvestigate(currentRun.claimIds[0])}
              >
                <Search />
                Investigate further
              </Button>
            ) : null}
          </div>
        )}
      </div>

      <div className="border-t border-border-soft p-2">
        <PromptComposer
          value={draft}
          onValueChange={setDraft}
          onSubmit={() => submit(draft)}
          onStop={onStop}
          isStreaming={isRunning}
          placeholder="Ask anything about this scene…"
          contextSlot={
            drawnRegion ? (
              <button
                type="button"
                onClick={() => clearRegion(null)}
                title="Clear the drawn region"
                className={cn("rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none")}
              >
                <Chip tone="teal">Scoped to drawn region · clear</Chip>
              </button>
            ) : null
          }
        />
      </div>
    </div>
  );
}
