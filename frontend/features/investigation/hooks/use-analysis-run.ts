// features/investigation/hooks/use-analysis-run.ts — the live analysis run: trace, layers, claims, answer.
//
// what  : Opens the run stream, folds trace steps and answer tokens into the feature store, and mutates
//         the cached evidence graph as layers and claims arrive.
// where : Called once by InvestigationScreen. It is the only place that talks to analysis.service.ts.
// how   : Layers are committed the instant a `layer-ready` frame arrives rather than at the end of the
//         run. That is the difference between a workspace that feels alive and one that feels like a form
//         submission: the operator watches the change mask land on the scene while the answer is still
//         being written.
//
//         Layers and claims go into the QUERY CACHE, not the store, because they are server state. The
//         stream mutates that cache incrementally — the rule for realtime data here — so nothing refetches
//         and the graph the layer stack reads is the same one the spotlight resolves against.
//
//         Answer tokens arrive every few milliseconds, so they accumulate in a ref and flush on an
//         interval. Committing each one would re-render the answer panel around seventy times a second
//         and visibly stutter once the answer grows; the reveal still reads as continuous because the
//         typewriter renderer animates ahead of the commits.
//
//         Trace steps commit immediately. They are low frequency, and they are the operator only signal
//         that the machine is actually working.

"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import { QUERY_KEYS } from "@/lib/constants/query-keys";

import { streamAnalysisRun } from "../services/analysis.service";
import { useInvestigationStore } from "../store/investigation-store";
import type { AnalysisRun, AnalysisStreamEvent } from "../types/analysis.types";
import type { EvidenceItem, NormalisedEvidenceGraph } from "../types/evidence.types";
import type { EvidenceLayer } from "../types/layer.types";
import type { Claim } from "../types/evidence.types";

const ANSWER_FLUSH_INTERVAL_MS = 80;

const EMPTY_GRAPH: NormalisedEvidenceGraph = {
  claimsById: {},
  claimOrder: [],
  evidenceById: {},
  layersById: {},
  layerOrder: [],
};

interface AnalysisRunControls {
  ask: (query: string, options?: { planId?: string }) => void;
  stop: () => void;
}

export function useAnalysisRun(investigationId: string): AnalysisRunControls {
  const queryClient = useQueryClient();
  const abortControllerRef = useRef<AbortController | null>(null);
  const pendingAnswerRef = useRef<{ runId: string; text: string } | null>(null);
  // The stream does not echo the question back, so it is held here and attached when the run opens.
  const pendingQueryRef = useRef("");
  const flushTimerRef = useRef<number | null>(null);

  const evidenceQueryKey = QUERY_KEYS.investigations.evidence(investigationId);

  const flushPendingAnswer = useCallback(() => {
    const pending = pendingAnswerRef.current;
    if (!pending || pending.text.length === 0) {
      return;
    }
    pendingAnswerRef.current = { runId: pending.runId, text: "" };
    useInvestigationStore.getState().appendAnswerText(pending.runId, pending.text);
  }, []);

  const stopFlushTimer = useCallback(() => {
    if (flushTimerRef.current !== null) {
      window.clearInterval(flushTimerRef.current);
      flushTimerRef.current = null;
    }
  }, []);

  /** Adds one layer and its evidence to the cached graph without disturbing what is already there. */
  const commitLayer = useCallback(
    (layer: EvidenceLayer, evidence: readonly EvidenceItem[]) => {
      queryClient.setQueryData<NormalisedEvidenceGraph>(evidenceQueryKey, (current) => {
        const graph = current ?? EMPTY_GRAPH;
        const evidenceById = { ...graph.evidenceById };
        for (const item of evidence) {
          evidenceById[item.id] = item;
        }

        return {
          ...graph,
          evidenceById,
          layersById: { ...graph.layersById, [layer.id]: layer },
          // Draw order is a backend decision; a re-delivered layer keeps its original position.
          layerOrder: graph.layerOrder.includes(layer.id)
            ? graph.layerOrder
            : [...graph.layerOrder, layer.id],
        };
      });
    },
    [evidenceQueryKey, queryClient],
  );

  const commitClaim = useCallback(
    (claim: Claim) => {
      queryClient.setQueryData<NormalisedEvidenceGraph>(evidenceQueryKey, (current) => {
        const graph = current ?? EMPTY_GRAPH;
        return {
          ...graph,
          claimsById: { ...graph.claimsById, [claim.id]: claim },
          claimOrder: graph.claimOrder.includes(claim.id)
            ? graph.claimOrder
            : // The headline claim leads; supporting detail keeps arrival order behind it.
              claim.isPrimary
              ? [claim.id, ...graph.claimOrder]
              : [...graph.claimOrder, claim.id],
        };
      });
    },
    [evidenceQueryKey, queryClient],
  );

  const handleEvent = useCallback(
    (event: AnalysisStreamEvent) => {
      const store = useInvestigationStore.getState();

      switch (event.type) {
        case "run-start":
          pendingAnswerRef.current = { runId: event.runId, text: "" };
          store.startRun(
            createRun(event.runId, event.startedAt, event.intent, pendingQueryRef.current),
          );
          break;

        case "trace-step":
          store.upsertTraceStep(event.runId, event.step);
          break;

        case "layer-ready":
          commitLayer(event.layer, event.evidence);
          break;

        case "claim":
          commitClaim(event.claim);
          store.attachClaim(event.runId, event.claim.id);
          break;

        case "answer-token": {
          const pending = pendingAnswerRef.current;
          pendingAnswerRef.current = {
            runId: event.runId,
            text: (pending?.runId === event.runId ? pending.text : "") + event.text,
          };
          break;
        }

        case "run-complete":
          flushPendingAnswer();
          store.completeRun(event.runId, {
            confidence: event.confidence,
            insufficientEvidence: event.insufficientEvidence,
            totalDurationMs: event.totalDurationMs,
          });
          break;

        case "run-error":
          flushPendingAnswer();
          store.failRun(event.runId, event.message);
          break;
      }
    },
    [commitClaim, commitLayer, flushPendingAnswer],
  );

  const ask = useCallback(
    (query: string, options?: { planId?: string }) => {
      const trimmedQuery = query.trim();
      if (trimmedQuery.length === 0 || abortControllerRef.current) {
        return;
      }

      const store = useInvestigationStore.getState();
      pendingQueryRef.current = trimmedQuery;
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      flushTimerRef.current = window.setInterval(flushPendingAnswer, ANSWER_FLUSH_INTERVAL_MS);

      void streamAnalysisRun(
        {
          investigationId,
          query: trimmedQuery,
          // A drawn region scopes the question to what the operator outlined; the backend crops to it.
          regionBounds: store.drawnRegion?.bounds ?? null,
          planId: options?.planId ?? null,
        },
        { onEvent: handleEvent },
        abortController.signal,
      )
        .catch((error: unknown) => {
          const pending = pendingAnswerRef.current;
          if (pending && !abortController.signal.aborted) {
            useInvestigationStore
              .getState()
              .failRun(
                pending.runId,
                error instanceof Error
                  ? `The analysis stream failed: ${error.message}`
                  : "The analysis stream failed.",
              );
          }
        })
        .finally(() => {
          flushPendingAnswer();
          stopFlushTimer();
          abortControllerRef.current = null;
        });
    },
    [flushPendingAnswer, handleEvent, investigationId, stopFlushTimer],
  );

  const stop = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    flushPendingAnswer();
    stopFlushTimer();

    const pending = pendingAnswerRef.current;
    if (pending) {
      useInvestigationStore.getState().cancelRun(pending.runId);
    }
  }, [flushPendingAnswer, stopFlushTimer]);

  // A workspace closed mid-run must not leave an interval or an open stream behind.
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      if (flushTimerRef.current !== null) {
        window.clearInterval(flushTimerRef.current);
      }
    };
  }, []);

  return { ask, stop };
}

function createRun(
  runId: string,
  startedAt: string,
  intent: AnalysisRun["intent"],
  query: string,
): AnalysisRun {
  return {
    id: runId,
    query,
    intent,
    status: "running",
    startedAt,
    answerText: "",
    confidence: null,
    insufficientEvidence: null,
    traceSteps: [],
    claimIds: [],
    totalDurationMs: null,
  };
}
