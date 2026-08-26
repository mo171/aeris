// features/missionCommand/services/assistant.service.ts — the streamed conversation with the AERIS agent.
//
// what  : Fetches suggested queries and opens the server-sent-event stream that carries answer tokens and
//         execution-trace steps back from the agent.
// where : Called by use-assistant-session.ts. Nothing else opens a stream.
// how   : Answers arrive incrementally, so the stream goes through lib/streaming rather than axios. Each
//         raw frame is validated against assistantStreamEventSchema before it is handed upward: a
//         truncated or malformed frame is dropped as data, because the transcript is append-only and
//         cannot recover from a bad write. Unparseable frames are counted, not thrown, so one bad frame
//         never kills an otherwise healthy answer.

import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";
import { openStream } from "@/lib/streaming/stream-client";

import {
  assistantStreamEventSchema,
  assistantSuggestionCollectionSchema,
} from "../schemas/assistant.schema";
import type {
  AssistantAskRequest,
  AssistantStreamEvent,
  AssistantSuggestion,
} from "../types/assistant.types";

export async function fetchAssistantSuggestions(
  signal?: AbortSignal,
): Promise<AssistantSuggestion[]> {
  const response = await apiClient.get(REST_API.assistant.suggestions, { signal });
  const collection = parseApiResponse(
    assistantSuggestionCollectionSchema,
    response.data,
    "the assistant suggestions endpoint",
  );

  return collection.suggestions;
}

export interface AssistantStreamHandlers {
  onEvent: (event: AssistantStreamEvent) => void;
  /** Called once with the number of frames that failed validation, after the stream closes. */
  onMalformedFrames?: (frameCount: number) => void;
}

export async function streamAssistantAnswer(
  request: AssistantAskRequest,
  handlers: AssistantStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let malformedFrameCount = 0;

  await openStream({
    path: REST_API.assistant.stream,
    body: request,
    signal,
    onMessage: (rawData) => {
      const event = safeParseStreamFrame(rawData);
      if (event) {
        handlers.onEvent(event);
      } else {
        malformedFrameCount += 1;
      }
    },
  });

  if (malformedFrameCount > 0) {
    handlers.onMalformedFrames?.(malformedFrameCount);
  }
}

function safeParseStreamFrame(rawData: string): AssistantStreamEvent | null {
  try {
    const parsed = assistantStreamEventSchema.safeParse(JSON.parse(rawData));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}
