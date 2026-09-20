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
import mumbaiRunData from "../data/mumbai-run-data.json";

const RUN_START_DELAY_MS = 150;
const STEP_START_DELAY_MS = 140;
const STEP_COMPLETE_DELAY_MS = 220;
const TOKEN_DELAY_MS = 20;
const TOKENS_PER_FRAME = 2;

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

  // ── Re-run path ──────────────────────────────────────────────────────────────────────────────────
  //
  // When a step id is supplied the backend (and here, the mock) treats every step BEFORE the rerun
  // point as "skipped" — reused from the prior run — and every step AT or AFTER as re-executing.
  // parameterOverrides are merged into the affected step's parameters so the inspector shows the
  // new value on the wire rather than the old one.

  const rerunFromStepId = request.rerunFromStepId ?? null;
  const parameterOverrides = request.parameterOverrides ?? {};

  // Build the ordered list of step IDs so we can find the cut point
  const stepIds = script.traceSteps.map((s) => s.id);
  const rerunIndex = rerunFromStepId ? stepIds.indexOf(rerunFromStepId) : -1;

  for (let i = 0; i < script.traceSteps.length; i++) {
    const step = script.traceSteps[i];
    const isUpstream = rerunIndex !== -1 && i < rerunIndex;

    if (isUpstream) {
      // Upstream of the rerun point: emit as skipped immediately (no running → completed cycle)
      emit({
        type: "trace-step",
        runId,
        step: {
          ...step,
          state: "skipped",
          durationMs: null,
          detail: `Reused from prior run (upstream of step ${rerunFromStepId})`,
        },
      });
      continue;
    }

    // Apply parameter overrides for the re-run step (and any downstream that inherit the same key)
    const stepOverrides = parameterOverrides[step.id] ?? {};
    const effectiveStep = Object.keys(stepOverrides).length > 0
      ? { ...step, parameters: { ...step.parameters, ...stepOverrides } }
      : step;

    if (await isCancelled(signal, STEP_START_DELAY_MS)) {
      return;
    }
    emit({ type: "trace-step", runId, step: { ...effectiveStep, state: "running", durationMs: null } });

    if (await isCancelled(signal, STEP_COMPLETE_DELAY_MS)) {
      return;
    }
    emit({
      type: "trace-step",
      runId,
      step: {
        ...effectiveStep,
        state: "completed",
        durationMs: STEP_START_DELAY_MS + STEP_COMPLETE_DELAY_MS,
      },
    });

    // Layers become available the moment their stage finishes, not when the run does.
    const readyLayers = script.layers.filter((layer) => layer.provenance.traceStepId === step.id);
    for (const readyLayer of readyLayers) {
      emit({
        type: "layer-ready",
        runId,
        layer: readyLayer,
        evidence: script.evidence.filter((item) => item.layerId === readyLayer.id),
      });
    }

    // Emit analytical figures produced by this step
    const stepFigures = (mumbaiRunData.figures ?? []).filter(
      (fig) => fig.stage === step.stageCode || step.id.endsWith(fig.stage),
    );
    for (const fig of stepFigures) {
      emit({
        type: "figure-ready",
        runId,
        figureId: fig.id,
        kind: fig.kind === "cross-modal" ? "comparison" : fig.kind,
        title: fig.title,
        caption: fig.caption,
        imageUrl: fig.imageUrl,
        width: 1024,
        height: 768,
        traceStepId: step.id,
        claimIds: script.claims
          .filter((c) => c.traceStepId === step.id || c.traceStepId?.includes(fig.stage))
          .map((c) => c.id),
        legend: {
          kind: "continuous",
          label: fig.title,
          colorRamp:
            fig.kind === "index-map"
              ? "index-vegetation"
              : fig.kind === "sar-backscatter"
                ? "sar-grayscale"
                : "mask-amber",
          domain: [0, 1],
          entries: null,
        },
        renderSpec: {
          sceneIds: ["SCN_01M289GY37847TXAC6919HZE9E"],
          bands: ["B04", "B03", "B02"],
          stretch: { min: 0, max: 1 },
          colorRamp:
            fig.kind === "index-map"
              ? "index-vegetation"
              : fig.kind === "sar-backscatter"
                ? "sar-grayscale"
                : "mask-amber",
          resampling: "bilinear",
          crs: "EPSG:32643",
          decimation: 1,
          maskApplied: true,
        },
        isPrimary: false,
      });
    }
  }

  // Evidence that draws nothing — the area statistics — still has to reach the graph.
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
