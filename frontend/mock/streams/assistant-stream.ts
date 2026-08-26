// mock/streams/assistant-stream.ts — replays a scripted agent answer as real server-sent-event frames.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : A StreamTransport implementation that emits message-start, trace-step, token and
//         message-complete frames on a realistic schedule, honouring cancellation.
// where : Installed onto lib/streaming by mock/index.ts.
// how   : Frames are emitted as JSON strings in exactly the format the live SSE endpoint will send, so the
//         parsing, validation and incremental-render path in the assistant panel is the production one.
//         Trace steps are emitted twice — once as `running`, once as `completed` — because that transition
//         is the whole point of the execution trace UI and it must be exercised, not simulated after the
//         fact. Tokens are emitted in word-sized chunks rather than per character: that is how real
//         token streams arrive, and it is what the rAF-batched renderer is tuned for.

import type { StreamRequestConfig, StreamTransport } from "@/lib/streaming/stream-client";
import type { AssistantAskRequest } from "@/features/missionCommand/types/assistant.types";

import { selectAssistantScript } from "../data/assistant.data";

const TRACE_STEP_START_DELAY_MS = 130;
const TRACE_STEP_COMPLETE_DELAY_MS = 190;
const TOKEN_DELAY_MS = 14;
const TOKENS_PER_FRAME = 3;

export const mockAssistantStreamTransport: StreamTransport = async ({
  body,
  signal,
  onMessage,
}: StreamRequestConfig) => {
  const request = body as AssistantAskRequest;
  const messageId = `msg_${Date.now().toString(36)}`;
  const script = selectAssistantScript(request.prompt, request.sceneIds.length > 0);

  const emit = (payload: unknown) => onMessage(JSON.stringify(payload));

  emit({ type: "message-start", messageId, createdAt: new Date().toISOString() });

  for (const step of script.trace) {
    if (await isCancelled(signal, TRACE_STEP_START_DELAY_MS)) {
      return;
    }
    emit({ type: "trace-step", messageId, step: { ...step, state: "running", durationMs: null } });

    if (await isCancelled(signal, TRACE_STEP_COMPLETE_DELAY_MS)) {
      return;
    }
    emit({ type: "trace-step", messageId, step: { ...step, state: "completed" } });
  }

  for (const chunk of chunkIntoTokens(script.answer)) {
    if (await isCancelled(signal, TOKEN_DELAY_MS)) {
      return;
    }
    emit({ type: "token", messageId, text: chunk });
  }

  emit({
    type: "message-complete",
    messageId,
    confidence: script.confidence,
    evidenceRegionCount: script.evidenceRegionCount,
  });
};

/** Splits text into word-sized chunks while preserving whitespace and newlines exactly. */
function chunkIntoTokens(text: string): string[] {
  const words = text.split(/(\s+)/).filter((part) => part.length > 0);
  const chunks: string[] = [];

  for (let index = 0; index < words.length; index += TOKENS_PER_FRAME) {
    chunks.push(words.slice(index, index + TOKENS_PER_FRAME).join(""));
  }

  return chunks;
}

/** Waits, then reports whether the caller aborted during the wait. */
function isCancelled(signal: AbortSignal | undefined, delayMs: number): Promise<boolean> {
  if (signal?.aborted) {
    return Promise.resolve(true);
  }

  return new Promise((resolve) => {
    const timeoutId = window.setTimeout(() => {
      signal?.removeEventListener("abort", handleAbort);
      resolve(Boolean(signal?.aborted));
    }, delayMs);

    function handleAbort() {
      window.clearTimeout(timeoutId);
      resolve(true);
    }

    signal?.addEventListener("abort", handleAbort, { once: true });
  });
}
