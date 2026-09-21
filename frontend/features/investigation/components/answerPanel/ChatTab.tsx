"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  CheckCircle2,
  CornerDownLeft,
  Loader2,
  Send,
  Sparkles,
  Square,
  User,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatRelativeTime } from "@/lib/formatters";
import { TypewriterText } from "@/components/sharedUI/dumbComponent/TypewriterText";
import { cn } from "@/lib/utils";
import { useVoiceStore, type VoiceChatMessage } from "@/features/voice/store/voice-store";

import type { AnalysisRun } from "../../types/analysis.types";
import type { Claim, EvidenceItem } from "../../types/evidence.types";
import type { InvestigationEvent } from "../../types/history.types";

interface ChatTabProps {
  runs: AnalysisRun[];
  isRunning: boolean;
  claimsById: Record<string, Claim>;
  evidenceById: Record<string, EvidenceItem>;
  onAsk: (query: string) => void;
  onStop: () => void;
  onFocusEvidence?: (claim: Claim) => void;
  history?: InvestigationEvent[];
}

const QUICK_PROMPTS = [
  "Assess vegetation density and canopy health index",
  "Detect structural changes and surface anomalies",
  "Inspect surface water extent and moisture index",
  "Measure target sector bounding area and coordinates",
];

/**
 * One voice turn rendered in the run thread's own visual language: operator
 * on the right, AERIS on the left, with a voice caption so spoken turns are
 * distinguishable from typed analysis runs at a glance.
 */
function VoiceChatBubble({ message }: { message: VoiceChatMessage }) {
  if (message.role === "operator") {
    return (
      <div className="flex justify-end gap-2 items-start pl-6">
        <div className="max-w-[85%] rounded-lg bg-primary/15 border border-primary/25 px-3 py-2 text-foreground space-y-1">
          <div className="flex items-center justify-between gap-3 text-[10px] text-primary font-medium">
            <span>Operator · Voice</span>
            <span className="text-muted-foreground/70 font-mono">
              {formatRelativeTime(message.createdAt)}
            </span>
          </div>
          <p className="text-xs leading-relaxed font-sans">{message.text}</p>
        </div>
        <div className="size-6 rounded-full bg-surface-3 border border-border-soft flex items-center justify-center shrink-0 text-muted-foreground">
          <User className="size-3.5" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start gap-2 items-start pr-4">
      <div className="size-6 rounded-full bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center shrink-0 text-cyan-400">
        <Bot className="size-3.5" />
      </div>
      <div className="flex-1 max-w-[90%] rounded-lg bg-surface-2/60 border border-border-soft px-3.5 py-2.5 space-y-1">
        <div className="flex items-center justify-between text-[10px]">
          <span className="font-semibold text-cyan-300">AERIS · Voice</span>
          <span className="text-muted-foreground/70 font-mono">
            {formatRelativeTime(message.createdAt)}
          </span>
        </div>
        <p className="text-foreground leading-relaxed text-xs">{message.text}</p>
      </div>
    </div>
  );
}

export function ChatTab({
  runs,
  isRunning,
  claimsById,
  evidenceById,
  onAsk,
  onStop,
  onFocusEvidence,
}: ChatTabProps) {
  const [draft, setDraft] = useState("");
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Voice turns land in the same thread, ordered with runs by wall time.
  const voiceMessages = useVoiceStore((state) => state.messages);
  const timeline = useMemo(() => {
    const at = (iso: string) => {
      const parsed = Date.parse(iso);
      return Number.isFinite(parsed) ? parsed : 0;
    };
    return [
      ...runs.map((run) => ({ at: at(run.startedAt), run })),
      ...voiceMessages.map((voice) => ({ at: at(voice.createdAt), voice })),
    ].sort((left, right) => left.at - right.at);
  }, [runs, voiceMessages]);

  // Auto-scroll to bottom whenever runs, voice turns, or stream tokens change
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [runs, isRunning, voiceMessages]);

  const handleSend = () => {
    const trimmed = draft.trim();
    if (!trimmed || isRunning) return;
    onAsk(trimmed);
    setDraft("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-full flex-col bg-surface-1/40">
      {/* Messages Scroll Area */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto p-3 space-y-4 text-xs"
      >
        {/* System Initial Message */}
        <div className="flex gap-2.5 items-start bg-surface-2/30 border border-border-soft/60 rounded-md p-2.5">
          <div className="size-6 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 text-primary">
            <Sparkles className="size-3.5" />
          </div>
          <div className="flex-1 space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground text-[11px]">AERIS Intelligence</span>
              <span className="text-[10px] text-muted-foreground">Ready</span>
            </div>
            <p className="text-muted-foreground leading-relaxed">
              Target area of interest locked. Ask natural language questions, request multispectral index calculations, or inspect identified anomalies.
            </p>
          </div>
        </div>

        {/* Conversation Turns (analysis runs and voice exchanges, in order) */}
        {timeline.map((item) => {
          if ("voice" in item) {
            return <VoiceChatBubble key={item.voice.id} message={item.voice} />;
          }
          const run = item.run;
          const runClaims = run.claimIds
            .map((id) => claimsById[id])
            .filter((c): c is Claim => Boolean(c));

          return (
            <div key={run.id} className="space-y-3">
              {/* Operator Query Bubble */}
              <div className="flex justify-end gap-2 items-start pl-6">
                <div className="max-w-[85%] rounded-lg bg-primary/15 border border-primary/25 px-3 py-2 text-foreground space-y-1">
                  <div className="flex items-center justify-between gap-3 text-[10px] text-primary font-medium">
                    <span>Operator</span>
                    <span className="text-muted-foreground/70 font-mono">
                      {formatRelativeTime(run.startedAt)}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed font-sans">{run.query}</p>
                </div>
                <div className="size-6 rounded-full bg-surface-3 border border-border-soft flex items-center justify-center shrink-0 text-muted-foreground">
                  <User className="size-3.5" />
                </div>
              </div>

              {/* AERIS AI Response Bubble */}
              <div className="flex justify-start gap-2 items-start pr-4">
                <div className="size-6 rounded-full bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center shrink-0 text-cyan-400">
                  <Bot className="size-3.5" />
                </div>
                <div className="flex-1 max-w-[90%] rounded-lg bg-surface-2/60 border border-border-soft px-3.5 py-2.5 space-y-2">
                  <div className="flex items-center justify-between text-[10px]">
                    <div className="flex items-center gap-1.5">
                      <span className="font-semibold text-cyan-300">AERIS Model</span>
                      {run.status === "running" && (
                        <span className="inline-flex items-center gap-1 text-primary text-[9px] font-mono px-1.5 py-0.5 rounded bg-primary/10 border border-primary/20">
                          <Loader2 className="size-2.5 animate-spin" />
                          Streaming
                        </span>
                      )}
                      {run.confidence != null && run.status !== "running" && (
                        <span className="inline-flex items-center gap-0.5 text-emerald-400 text-[9px] font-mono px-1.5 py-0.2 rounded bg-emerald-500/10 border border-emerald-500/20">
                          <CheckCircle2 className="size-2.5" />
                          {Math.round(run.confidence * 100)}% Confidence
                        </span>
                      )}
                    </div>
                  </div>

                  {/* AI Answer Text */}
                  {run.answerText ? (
                    <div className="text-foreground leading-relaxed text-xs">
                      <TypewriterText
                        text={run.answerText}
                        isStreaming={run.status === "running"}
                      />
                    </div>
                  ) : run.status === "running" ? (
                    <div className="flex items-center gap-1.5 text-muted-foreground italic text-[11px]">
                      <Loader2 className="size-3 animate-spin text-primary" />
                      Consulting vision-language intelligence models...
                    </div>
                  ) : (
                    <p className="text-muted-foreground text-xs italic">No response text recorded.</p>
                  )}

                  {/* Claims / Metrics Section */}
                  {runClaims.length > 0 && (
                    <div className="pt-2 border-t border-border-soft/60 space-y-1.5">
                      <div className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground">
                        Extracted Claims & Metrics
                      </div>
                      <div className="space-y-1.5">
                        {runClaims.map((claim) => (
                          <div
                            key={claim.id}
                            onClick={() => onFocusEvidence?.(claim)}
                            className="p-2 rounded bg-surface-1/80 border border-border-soft hover:border-cyan-500/40 cursor-pointer transition-colors space-y-1"
                          >
                            <p className="text-[11px] text-foreground font-medium leading-snug">
                              {claim.text}
                            </p>
                            {claim.metrics.length > 0 && (
                              <div className="flex flex-wrap gap-1.5 pt-0.5">
                                {claim.metrics.map((m, idx) => (
                                  <span
                                    key={idx}
                                    className="inline-flex items-center gap-1 font-mono text-[9px] px-1.5 py-0.5 rounded bg-surface-3 text-cyan-300 border border-cyan-500/20"
                                  >
                                    <span className="text-muted-foreground">{m.label}:</span>
                                    <span className="font-semibold">{m.value} {m.unit}</span>
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Suggestion Chips */}
      {runs.length <= 1 && (
        <div className="px-3 py-1.5 border-t border-border-soft/40 flex flex-wrap gap-1 shrink-0">
          {QUICK_PROMPTS.map((prompt, i) => (
            <button
              key={i}
              type="button"
              disabled={isRunning}
              onClick={() => onAsk(prompt)}
              className="text-[10px] px-2 py-1 rounded bg-surface-2/60 hover:bg-surface-3 text-muted-foreground hover:text-foreground border border-border-soft/70 transition-colors text-left"
            >
              {prompt}
            </button>
          ))}
        </div>
      )}

      {/* Input Composer Bar */}
      <div className="p-2.5 border-t border-border-soft bg-surface-2/40 shrink-0">
        <div className="flex gap-1.5 items-end rounded-md bg-surface-1 border border-border-soft p-1.5 focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
          <textarea
            ref={textareaRef}
            rows={2}
            value={draft}
            disabled={isRunning}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isRunning
                ? "AERIS is analyzing..."
                : "Ask about this scene (e.g. 'Assess vegetation and structural stability')..."
            }
            className="flex-1 bg-transparent text-xs text-foreground placeholder:text-muted-foreground/60 resize-none outline-none px-1 py-0.5 leading-relaxed"
          />

          <div className="flex items-center gap-1 shrink-0 pb-0.5">
            {isRunning ? (
              <Button
                type="button"
                size="sm"
                variant="destructive"
                onClick={onStop}
                className="h-7 px-2 text-[11px] gap-1"
              >
                <Square className="size-3 fill-current" />
                <span>Stop</span>
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                onClick={handleSend}
                disabled={!draft.trim()}
                className="h-7 px-2.5 text-[11px] gap-1 bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                <span>Ask</span>
                <CornerDownLeft className="size-3" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
