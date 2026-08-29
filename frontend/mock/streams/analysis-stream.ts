// mock/streams/analysis-stream.ts — replays an analysis run as real server-sent-event frames.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : Emits run-start, trace-step, layer-ready, claim, answer-token and run-complete frames on a
//         realistic schedule, honouring cancellation.
// where : Installed onto lib/streaming by mock/streams/index.ts.
// how   : Frames are JSON strings in exactly the format the live endpoint will send, so the parsing,
//         validation and incremental-commit path in the workspace is the production one.
//
//         Trace steps are emitted twice — running, then completed with a duration — because that
//         transition IS the execution-trace UI and it must be exercised rather than reconstructed.
//
//         Layers are emitted at the stage that produced them, mid-run, rather than batched at the end.
//         That is the behaviour the whole surface is designed around: the operator watches the change
//         mask land on the scene while the answer is still being written. Mocking it any other way would
//         hide the one timing characteristic that matters.

import type { AnalysisRunRequest } from "@/features/investigation/types/analysis.types";
import type { StreamRequestConfig } from "@/lib/streaming/stream-client";

import { selectMockAnalysisScript } from "../data/investigation.data";

const RUN_START_DELAY_MS = 120;
const STEP_START_DELAY_MS = 90;
const STEP_COMPLETE_DELAY_MS = 130;
const TOKEN_DELAY_MS = 16;
const TOKENS_PER_FRAME = 3;

export async function mockAnalysisStream({
  path,
  body,
  signal,
  onMessage,
}: StreamRequestConfig): Promise<void> {
  const request = body as AnalysisRunRequest;
  const runId = `run_${Date.now().toString(36)}`;
  const script = selectMockAnalysisScript(
    request.investigationId,
    request.query,
    request.operationId,
  );

  const emit = (payload: unknown) => onMessage(JSON.stringify(payload));

  if (!script) {
    emit({ type: "run-error", runId, message: `No investigation found at ${path}.` });
    return;
  }

  const startedAtMs = Date.now();

  if (await isCancelled(signal, RUN_START_DELAY_MS)) {
    return;
  }

  emit({
    type: "run-start",
    runId,
    intent: request.regionBounds ? "GROUND" : "CHANGE_DETECT",
    startedAt: new Date().toISOString(),
  });

  for (const step of script.traceSteps) {
    if (await isCancelled(signal, STEP_START_DELAY_MS)) {
      return;
    }
    emit({ type: "trace-step", runId, step: { ...step, state: "running", durationMs: null } });

    if (await isCancelled(signal, STEP_COMPLETE_DELAY_MS)) {
      return;
    }
    emit({
      type: "trace-step",
      runId,
      step: {
        ...step,
        state: "completed",
        durationMs: STEP_START_DELAY_MS + STEP_COMPLETE_DELAY_MS,
      },
    });

    // A layer becomes available the moment its stage finishes, not when the run does.
    const readyLayer = script.layers.find((layer) => layer.provenance.traceStepId === step.id);
    if (readyLayer) {
      emit({
        type: "layer-ready",
        runId,
        layer: readyLayer,
        evidence: script.evidence.filter((item) => item.layerId === readyLayer.id),
      });
    }
  }

  // Evidence that draws nothing — the area statistics — still has to reach the graph, or claims that
  // cite it would render as unsupported.
  const unattachedEvidence = script.evidence.filter((item) => item.layerId === null);
  if (unattachedEvidence.length > 0 && script.layers.length > 0) {
    emit({
      type: "layer-ready",
      runId,
      layer: { ...script.layers[0], isVisible: script.layers[0].isVisible },
      evidence: unattachedEvidence,
    });
  }

  for (const claim of script.claims) {
    if (await isCancelled(signal, STEP_START_DELAY_MS)) {
      return;
    }
    emit({ type: "claim", runId, claim: { ...claim, runId } });
  }

  for (const chunk of chunkIntoTokens(script.answer)) {
    if (await isCancelled(signal, TOKEN_DELAY_MS)) {
      return;
    }
    emit({ type: "answer-token", runId, text: chunk });
  }

  emit({
    type: "run-complete",
    runId,
    confidence: script.confidence,
    insufficientEvidence: script.insufficientEvidence,
    totalDurationMs: Date.now() - startedAtMs,
  });
}

/** Splits text into word-sized chunks while preserving whitespace exactly. */
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
