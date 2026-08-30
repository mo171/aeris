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
//         Prior runs are REOPENABLE, not merely re-askable. Re-asking reruns the models, which costs time
//         and may not reproduce the same numbers; for a product whose claim is auditability, an answer you
//         cannot return to has not been audited. Each row carries when it ran, how long it took and what
//         confidence it reached, so the history reads as a record rather than as a list of old questions.
//
//         A LENS'S VERDICT SITS ABOVE THE RUNS, as a slot this component does not interpret. The two are
//         different kinds of statement and both belong on screen: a verdict is a standing fact about the
//         evidence, a run is an answer to a question somebody asked. Replacing the runs with it would take
//         away the ability to ask about what the verdict just said, which is the entire reason the
//         cross-modal reading lives inside the workspace rather than on a surface of its own.
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
import { formatDurationMs, formatPercentage, formatRelativeTime } from "@/lib/formatters";
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
  /** A lens's standing conclusion, rendered above the run history. See the note above. */
  verdictSection?: React.ReactNode;
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
  verdictSection,
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
  const drawnRegions = useInvestigationStore((state) => state.drawnRegions);
  const activeRegionId = useInvestigationStore((state) => state.activeRegionId);
  const setActiveRegionId = useInvestigationStore((state) => state.setActiveRegionId);
  const activeRegion = drawnRegions.find((region) => region.id === activeRegionId) ?? null;

  const selectedRunId = useInvestigationStore((state) => state.selectedRunId);
  const selectRun = useInvestigationStore((state) => state.selectRun);

  // Null selection follows the newest run, which is what an operator wants while one is streaming.
  const currentRun =
    (selectedRunId === null ? null : (runs.find((run) => run.id === selectedRunId) ?? null)) ??
    runs.at(-1) ??
    null;
  const priorRuns = runs.filter((run) => run.id !== currentRun?.id);

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
        {verdictSection ? <div className="mb-3">{verdictSection}</div> : null}

        {priorRuns.length > 0 ? (
          <ol className="mb-3 flex flex-col gap-0.5 border-b border-border-soft pb-2">
            {priorRuns.map((run) => (
              <li key={run.id}>
                <button
                  type="button"
                  onClick={() => selectRun(run.id)}
                  title="Reopen this answer"
                  className="flex w-full flex-col gap-0.5 rounded-sm px-1 py-1 text-left transition-colors duration-fast hover:bg-aeris-teal/8 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  <span className="truncate font-mono text-[11px] text-muted-foreground">
                    {run.query}
                  </span>
                  <span className="flex items-center gap-1.5 font-mono text-[9px] tracking-wide text-muted-foreground/55 uppercase">
                    <span>{formatRelativeTime(run.startedAt)}</span>
                    {run.totalDurationMs !== null ? (
                      <span>· {formatDurationMs(run.totalDurationMs)}</span>
                    ) : null}
                    {run.confidence !== null ? (
                      <span>· {formatPercentage(run.confidence)}</span>
                    ) : null}
                    {run.insufficientEvidence !== null ? (
                      <span className="text-aeris-amber/70">· insufficient evidence</span>
                    ) : null}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        ) : null}

        {/* Reading an older answer is a state the operator must be able to see and leave. */}
        {selectedRunId !== null && runs.at(-1)?.id !== selectedRunId ? (
          <div className="mb-2 flex items-center gap-2 rounded-md border border-aeris-amber/35 bg-aeris-amber/5 px-2 py-1.5">
            <span className="flex-1 text-[11px] text-aeris-amber">Showing an earlier answer.</span>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 px-2 text-[11px]"
              onClick={() => selectRun(null)}
            >
              Back to latest
            </Button>
          </div>
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
            activeRegion ? (
              <button
                type="button"
                onClick={() => setActiveRegionId(null)}
                title="Ask about the whole area of interest instead"
                className={cn(
                  "rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                )}
              >
                <Chip tone="teal">
                  Scoped to{" "}
                  {activeRegion.areaHectares >= 100
                    ? `${(activeRegion.areaHectares / 100).toFixed(1)} km²`
                    : `${activeRegion.areaHectares.toFixed(1)} ha`}{" "}
                  region · clear
                </Chip>
              </button>
            ) : null
          }
        />
      </div>
    </div>
  );
}
