// features/missionCommand/components/assistantPanel/AssistantPanel.tsx — the right panel: the AERIS agent.
//
// what  : The greeting, the transcript, the suggested queries, the scene-context chips and the composer.
// where : Rendered by MissionCommandScreen inside a PanelContainer.
// how   : The transcript scrolls in a plain container rather than a virtualiser. Message heights change
//         continuously while an answer streams and while a trace expands, and a virtualiser re-measuring
//         under those conditions produces exactly the scroll jitter this build is meant to avoid. Cost is
//         controlled instead with content-visibility on completed turns, which keeps paint bounded without
//         touching layout stability.
//
//         Auto-scroll follows the answer only while the operator is already at the bottom. Yanking the
//         view down while someone is reading an earlier answer is one of the most disliked behaviours a
//         streaming interface can have.

"use client";

import { Eraser, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import {
  PromptComposer,
  type PromptComposerHandle,
} from "@/components/sharedUI/functionalComponent/input/PromptComposer";
import { Button } from "@/components/ui/button";
import { APP } from "@/lib/constants/app";
import { cn } from "@/lib/utils";

import { useAssistantSession } from "../../hooks/use-assistant-session";
import { useMissionCommandStore } from "../../store/mission-command-store";
import { AssistantMessageCard } from "./AssistantMessageCard";
import { SuggestedQueries } from "./SuggestedQueries";

const BOTTOM_STICK_THRESHOLD_PX = 64;

export function AssistantPanel() {
  const { messages, suggestions, isStreaming, ask, stop, clear } = useAssistantSession();
  const [draftPrompt, setDraftPrompt] = useState("");

  const selectedSceneIds = useMissionCommandStore((state) => state.selectedSceneIds);
  const toggleSceneSelection = useMissionCommandStore((state) => state.toggleSceneSelection);
  const setAssistantControls = useMissionCommandStore((state) => state.setAssistantControls);

  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<PromptComposerHandle | null>(null);
  const isPinnedToBottomRef = useRef(true);

  const submitPrompt = useCallback(
    (prompt: string) => {
      ask(prompt);
      setDraftPrompt("");
      isPinnedToBottomRef.current = true;
    },
    [ask],
  );

  // Publish the panel's controls so the command bus — and later the agent and voice layers — can drive it.
  useEffect(() => {
    setAssistantControls({
      ask: submitPrompt,
      stop,
      clear,
      focusComposer: () => composerRef.current?.focus(),
    });
    return () => {
      setAssistantControls(null);
    };
  }, [clear, setAssistantControls, stop, submitPrompt]);

  const handleTranscriptScroll = useCallback(() => {
    const container = transcriptRef.current;
    if (!container) {
      return;
    }
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    isPinnedToBottomRef.current = distanceFromBottom < BOTTOM_STICK_THRESHOLD_PX;
  }, []);

  useEffect(() => {
    const container = transcriptRef.current;
    if (container && isPinnedToBottomRef.current) {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages]);

  const hasTranscript = messages.length > 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-9 shrink-0 items-center justify-between gap-2 border-b border-border px-3">
        <h2 className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-foreground">
          <Sparkles className="size-3.5 text-aeris-teal" aria-hidden="true" />
          {APP.name} Assistant
        </h2>
        {hasTranscript ? (
          <Button size="icon-xs" variant="ghost" aria-label="Clear conversation" onClick={clear}>
            <Eraser />
          </Button>
        ) : null}
      </header>

      <div
        ref={transcriptRef}
        onScroll={handleTranscriptScroll}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain py-2"
      >
        {!hasTranscript ? (
          <>
            <div className="px-3 pb-3">
              <p className="font-mono text-[10px] tracking-[0.18em] text-aeris-teal uppercase">
                {APP.name} online
              </p>
              <p className="mt-1.5 text-[11px] leading-relaxed text-foreground">
                Global systems nominal. What would you like to investigate?
              </p>
              <p className="mt-1.5 text-[10px] leading-relaxed text-muted-foreground">
                Select imagery on the left to give me context, then ask in plain language. Every answer
                arrives with its evidence, its confidence and the trace of how it was produced.
              </p>
            </div>
            <SuggestedQueries suggestions={suggestions} onSelect={submitPrompt} />
          </>
        ) : (
          messages.map((message) => (
            <AssistantMessageCard key={message.id} message={message} />
          ))
        )}
      </div>

      <div className="shrink-0 border-t border-border p-2">
        <PromptComposer
          value={draftPrompt}
          onValueChange={setDraftPrompt}
          onSubmit={() => submitPrompt(draftPrompt)}
          onStop={stop}
          isStreaming={isStreaming}
          placeholder="Ask about the selected imagery…"
          ref={composerRef}
          contextSlot={
            selectedSceneIds.length > 0 ? (
              <>
                <span className="aeris-technical">Context</span>
                {selectedSceneIds.map((sceneId) => (
                  <button
                    key={sceneId}
                    type="button"
                    onClick={() => toggleSceneSelection(sceneId)}
                    aria-label={`Remove ${sceneId} from context`}
                    className="transition-opacity duration-fast hover:opacity-70"
                  >
                    <Chip tone="teal">{sceneId}</Chip>
                  </button>
                ))}
              </>
            ) : null
          }
          hintSlot={
            <span
              className={cn(
                "font-mono text-[9px] tracking-wide uppercase",
                selectedSceneIds.length === 0 ? "text-aeris-amber/80" : "text-muted-foreground",
              )}
            >
              {selectedSceneIds.length === 0
                ? "No imagery selected — answers will be limited"
                : `${selectedSceneIds.length} scene${selectedSceneIds.length === 1 ? "" : "s"} in context`}
            </span>
          }
        />
      </div>
    </div>
  );
}
