// features/missionCommand/hooks/use-assistant-session.ts — the live conversation with the AERIS agent.
//
// what  : Owns the transcript, opens and cancels the answer stream, folds stream events into messages, and
//         exposes the suggested queries.
// where : Consumed by AssistantPanel. It is the only place that talks to assistant.service.ts.
// how   : Token frames arrive every few milliseconds. Committing each one to React state would re-render
//         the transcript seventy times a second and visibly stutter once an answer grows long, so incoming
//         text accumulates in a ref and is flushed on a fixed interval. The reveal still looks continuous
//         because TypewriterText animates ahead of the commits — the smoothness comes from the renderer,
//         not from the commit rate.
//
//         Trace steps are committed immediately: they are low frequency and they are the operator's only
//         signal that the agent is actually working.
//
//         Cancellation goes through an AbortController that also tears down the mock or live transport, so
//         pressing stop actually stops the work rather than just hiding it.

"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useId, useReducer, useRef, useState } from "react";

import { QUERY_KEYS } from "@/lib/constants/query-keys";

import {
  fetchAssistantSuggestions,
  streamAssistantAnswer,
} from "../services/assistant.service";
import { useMissionCommandStore } from "../store/mission-command-store";
import type {
  AssistantMessage,
  AssistantStreamEvent,
  AssistantSuggestion,
  ExecutionTraceStep,
} from "../types/assistant.types";

const TEXT_FLUSH_INTERVAL_MS = 80;
const SUGGESTIONS_STALE_TIME_MS = 10 * 60_000;

type TranscriptAction =
  | { type: "append-operator-message"; message: AssistantMessage }
  | { type: "start-assistant-message"; messageId: string; createdAt: string }
  | { type: "upsert-trace-step"; messageId: string; step: ExecutionTraceStep }
  | { type: "append-text"; messageId: string; text: string }
  | {
      type: "complete-message";
      messageId: string;
      confidence: number | null;
      evidenceRegionCount: number;
    }
  | { type: "fail-message"; messageId: string; reason: string }
  | { type: "clear" };

function transcriptReducer(
  messages: AssistantMessage[],
  action: TranscriptAction,
): AssistantMessage[] {
  switch (action.type) {
    case "append-operator-message":
      return [...messages, action.message];

    case "start-assistant-message":
      return [
        ...messages,
        {
          id: action.messageId,
          role: "aeris",
          content: "",
          createdAt: action.createdAt,
          status: "streaming",
          trace: [],
          confidence: null,
          evidenceRegionCount: 0,
        },
      ];

    case "upsert-trace-step":
      return messages.map((message) => {
        if (message.id !== action.messageId) {
          return message;
        }
        const existingIndex = message.trace.findIndex((step) => step.id === action.step.id);
        const trace =
          existingIndex === -1
            ? [...message.trace, action.step]
            : message.trace.map((step, index) => (index === existingIndex ? action.step : step));
        return { ...message, trace };
      });

    case "append-text":
      return messages.map((message) =>
        message.id === action.messageId
          ? { ...message, content: message.content + action.text }
          : message,
      );

    case "complete-message":
      return messages.map((message) =>
        message.id === action.messageId
          ? {
              ...message,
              status: "complete",
              confidence: action.confidence,
              evidenceRegionCount: action.evidenceRegionCount,
            }
          : message,
      );

    case "fail-message":
      return messages.map((message) =>
        message.id === action.messageId
          ? {
              ...message,
              status: "failed",
              content: message.content.length > 0 ? message.content : action.reason,
            }
          : message,
      );

    case "clear":
      return [];
  }
}

interface AssistantSessionResult {
  messages: AssistantMessage[];
  suggestions: AssistantSuggestion[];
  isStreaming: boolean;
  ask: (prompt: string) => void;
  stop: () => void;
  clear: () => void;
}

export function useAssistantSession(): AssistantSessionResult {
  const [messages, dispatch] = useReducer(transcriptReducer, []);
  const [isStreaming, setIsStreaming] = useState(false);

  const selectedSceneIds = useMissionCommandStore((state) => state.selectedSceneIds);
  const selectedSceneIdsRef = useRef(selectedSceneIds);

  // Mirrored from an effect so `ask` can read the newest selection without being re-created — and so
  // rendering stays free of ref writes.
  useEffect(() => {
    selectedSceneIdsRef.current = selectedSceneIds;
  }, [selectedSceneIds]);

  // useId gives a stable identifier across server and client without a random call during render.
  const sessionId = `sess_${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const abortControllerRef = useRef<AbortController | null>(null);
  const pendingTextRef = useRef<{ messageId: string; text: string } | null>(null);
  const flushTimerRef = useRef<number | null>(null);

  const { data: suggestions } = useQuery({
    queryKey: QUERY_KEYS.assistant.suggestions(),
    queryFn: ({ signal }) => fetchAssistantSuggestions(signal),
    staleTime: SUGGESTIONS_STALE_TIME_MS,
  });

  const flushPendingText = useCallback(() => {
    const pending = pendingTextRef.current;
    if (!pending || pending.text.length === 0) {
      return;
    }
    pendingTextRef.current = { messageId: pending.messageId, text: "" };
    dispatch({ type: "append-text", messageId: pending.messageId, text: pending.text });
  }, []);

  const stopFlushTimer = useCallback(() => {
    if (flushTimerRef.current !== null) {
      window.clearInterval(flushTimerRef.current);
      flushTimerRef.current = null;
    }
  }, []);

  const handleStreamEvent = useCallback(
    (event: AssistantStreamEvent) => {
      switch (event.type) {
        case "message-start":
          pendingTextRef.current = { messageId: event.messageId, text: "" };
          dispatch({
            type: "start-assistant-message",
            messageId: event.messageId,
            createdAt: event.createdAt,
          });
          break;

        case "trace-step":
          dispatch({ type: "upsert-trace-step", messageId: event.messageId, step: event.step });
          break;

        case "token": {
          const pending = pendingTextRef.current;
          pendingTextRef.current = {
            messageId: event.messageId,
            text: (pending?.messageId === event.messageId ? pending.text : "") + event.text,
          };
          break;
        }

        case "message-complete":
          flushPendingText();
          dispatch({
            type: "complete-message",
            messageId: event.messageId,
            confidence: event.confidence,
            evidenceRegionCount: event.evidenceRegionCount,
          });
          break;

        case "stream-error":
          flushPendingText();
          dispatch({ type: "fail-message", messageId: event.messageId, reason: event.message });
          break;
      }
    },
    [flushPendingText],
  );

  const ask = useCallback(
    (prompt: string) => {
      const trimmedPrompt = prompt.trim();
      if (trimmedPrompt.length === 0 || abortControllerRef.current) {
        return;
      }

      dispatch({
        type: "append-operator-message",
        message: {
          id: `op_${Date.now().toString(36)}`,
          role: "operator",
          content: trimmedPrompt,
          createdAt: new Date().toISOString(),
          status: "complete",
          trace: [],
          confidence: null,
          evidenceRegionCount: 0,
        },
      });

      const abortController = new AbortController();
      abortControllerRef.current = abortController;
      setIsStreaming(true);

      flushTimerRef.current = window.setInterval(flushPendingText, TEXT_FLUSH_INTERVAL_MS);

      void streamAssistantAnswer(
        {
          prompt: trimmedPrompt,
          sessionId,
          sceneIds: selectedSceneIdsRef.current,
        },
        { onEvent: handleStreamEvent },
        abortController.signal,
      )
        .catch((error: unknown) => {
          const pending = pendingTextRef.current;
          if (pending && !abortController.signal.aborted) {
            dispatch({
              type: "fail-message",
              messageId: pending.messageId,
              reason:
                error instanceof Error
                  ? `The answer stream failed: ${error.message}`
                  : "The answer stream failed.",
            });
          }
        })
        .finally(() => {
          flushPendingText();
          stopFlushTimer();
          abortControllerRef.current = null;
          setIsStreaming(false);
        });
    },
    [flushPendingText, handleStreamEvent, sessionId, stopFlushTimer],
  );

  const stop = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    flushPendingText();
    stopFlushTimer();

    const pending = pendingTextRef.current;
    if (pending) {
      dispatch({
        type: "complete-message",
        messageId: pending.messageId,
        confidence: null,
        evidenceRegionCount: 0,
      });
    }
    setIsStreaming(false);
  }, [flushPendingText, stopFlushTimer]);

  const clear = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    stopFlushTimer();
    pendingTextRef.current = null;
    setIsStreaming(false);
    dispatch({ type: "clear" });
  }, [stopFlushTimer]);

  // A panel unmounting mid-answer must not leave a timer or an open stream behind.
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      if (flushTimerRef.current !== null) {
        window.clearInterval(flushTimerRef.current);
      }
    };
  }, []);

  return {
    messages,
    suggestions: suggestions ?? [],
    isStreaming,
    ask,
    stop,
    clear,
  };
}
