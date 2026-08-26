// lib/streaming/stream-client.ts — the server-sent-event transport for streamed agent output.
//
// what  : Opens a POST stream, parses SSE frames, and hands raw `data:` payload strings to the caller.
//         Also exposes a transport slot so the Phase 1 mock can substitute an in-memory stream.
// where : Used by features/missionCommand/services/assistant.service.ts. Nothing else should touch it.
// how   : Assistant answers and execution-trace steps arrive incrementally, so this cannot go through
//         axios (browsers do not give axios a readable stream). It uses fetch + ReadableStream directly.
//         Callers receive raw strings rather than parsed objects on purpose: the wire format is identical
//         between the mock and the live backend, so the parsing/validation code path is exercised in
//         Phase 1 exactly as it will run in Phase 2.

import { env } from "@/lib/env";

export interface StreamRequestConfig {
  /** Path relative to the API base URL. */
  path: string;
  body: unknown;
  signal?: AbortSignal;
  /** Called once per SSE `data:` frame with the raw payload string. */
  onMessage: (rawData: string) => void;
}

export type StreamTransport = (config: StreamRequestConfig) => Promise<void>;

const SSE_FRAME_DELIMITER = "\n\n";
const SSE_DATA_PREFIX = "data:";

const fetchStreamTransport: StreamTransport = async ({ path, body, signal, onMessage }) => {
  const response = await fetch(`${env.NEXT_PUBLIC_API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Stream request failed with status ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    let delimiterIndex = buffer.indexOf(SSE_FRAME_DELIMITER);
    while (delimiterIndex !== -1) {
      const frame = buffer.slice(0, delimiterIndex);
      buffer = buffer.slice(delimiterIndex + SSE_FRAME_DELIMITER.length);
      emitFrame(frame, onMessage);
      delimiterIndex = buffer.indexOf(SSE_FRAME_DELIMITER);
    }
  }

  if (buffer.trim().length > 0) {
    emitFrame(buffer, onMessage);
  }
};

function emitFrame(frame: string, onMessage: (rawData: string) => void): void {
  for (const line of frame.split("\n")) {
    if (line.startsWith(SSE_DATA_PREFIX)) {
      const payload = line.slice(SSE_DATA_PREFIX.length).trim();
      if (payload.length > 0) {
        onMessage(payload);
      }
    }
  }
}

let activeTransport: StreamTransport = fetchStreamTransport;

/**
 * Replaces the stream transport. The Phase 1 mock bridge is the only caller; deleting /mock restores the
 * real fetch transport with no other change anywhere in the codebase.
 */
export function setStreamTransport(transport: StreamTransport): void {
  activeTransport = transport;
}

export function openStream(config: StreamRequestConfig): Promise<void> {
  return activeTransport(config);
}
