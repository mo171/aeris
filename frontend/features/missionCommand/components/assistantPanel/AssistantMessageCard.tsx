// features/missionCommand/components/assistantPanel/AssistantMessageCard.tsx — one turn of the conversation.
//
// what  : Renders an operator question as a plain right-aligned line, and an AERIS answer as a structured
//         card carrying its execution trace, confidence and evidence count.
// where : Rendered by AssistantMessageList.
// how   : The asymmetry is deliberate and comes straight from the product design: the operator's question
//         is just text, but an AERIS answer is a claim that must arrive with its provenance attached.
//         Rendering the answer as a bare bubble would make it look like chat output, which is exactly the
//         impression the platform exists to avoid.
//
//         Completed messages get content-visibility so a long transcript stops paying layout and paint
//         cost for turns that have scrolled out of view — the cheap alternative to virtualising content
//         whose height changes while it streams.

"use client";

import { memo } from "react";

import { Chip } from "@/components/sharedUI/dumbComponent/Chip";
import { TypewriterText } from "@/components/sharedUI/dumbComponent/TypewriterText";
import { ConfidenceMeter } from "@/components/sharedUI/functionalComponent/dataDisplay/ConfidenceMeter";
import { formatRelativeTime } from "@/lib/formatters";
import { cn } from "@/lib/utils";

import type { AssistantMessage } from "../../types/assistant.types";
import { ExecutionTraceBlock } from "./ExecutionTraceBlock";

interface AssistantMessageCardProps {
  message: AssistantMessage;
}

export const AssistantMessageCard = memo(function AssistantMessageCard({
  message,
}: AssistantMessageCardProps) {
  const isComplete = message.status === "complete";

  if (message.role === "operator") {
    return (
      <div className="flex justify-end px-3 py-1.5">
        <div className="max-w-[85%] rounded-md rounded-br-sm border border-aeris-blue/25 bg-aeris-blue/[0.1] px-2.5 py-1.5">
          <p className="text-[11px] leading-relaxed whitespace-pre-wrap text-foreground">
            {message.content}
          </p>
        </div>
      </div>
    );
  }

  return (
    <article
      className="px-3 py-1.5"
      style={isComplete ? { contentVisibility: "auto", containIntrinsicSize: "auto 220px" } : undefined}
    >
      <div
        className={cn(
          "rounded-md border bg-surface-2/50 px-2.5 py-2",
          message.status === "failed" ? "border-aeris-red/35" : "border-border-soft",
        )}
      >
        <header className="flex items-center gap-2">
          <span className="font-mono text-[9px] tracking-[0.18em] text-aeris-teal uppercase">
            AERIS
          </span>
          <span className="font-mono text-[9px] text-muted-foreground">
            {formatRelativeTime(message.createdAt)}
          </span>
          {message.evidenceRegionCount > 0 ? (
            <Chip tone="teal" className="ml-auto">
              {message.evidenceRegionCount} evidence
            </Chip>
          ) : null}
        </header>

        <ExecutionTraceBlock steps={message.trace} messageStatus={message.status} />

        {message.content.length > 0 ? (
          <div className="mt-2 text-[11px] leading-relaxed text-foreground">
            <TypewriterText text={message.content} isStreaming={message.status === "streaming"} />
          </div>
        ) : null}

        {isComplete ? (
          <footer className="mt-2 border-t border-border-soft pt-1.5">
            <ConfidenceMeter value={message.confidence} />
          </footer>
        ) : null}
      </div>
    </article>
  );
});
