// features/investigation/services/analysis.service.ts — the streamed analysis run.
//
// what  : Opens the run stream, validates every frame, fetches the autonomous plan, and fetches the
//         question suggestions for a drawn region.
// where : Called by use-analysis-run.ts, use-autonomous-investigation.ts and use-region-selection.ts.
// how   : The run streams because its parts become useful at different times. A change mask should reach
//         the scene the moment it exists, not once the answer finishes writing — so this goes through
//         lib/streaming rather than axios, exactly like the assistant on Mission Command.
//
//         Each raw frame is validated before it is handed upward. A truncated or malformed frame is
//         dropped as data and counted, never thrown: the trace and the answer are append-only and one bad
//         frame must not be able to kill an otherwise healthy run.

import { apiClient } from "@/lib/axios/axios-client";
import { parseApiResponse } from "@/lib/axios/parse-api-response";
import { REST_API } from "@/lib/constants/rest.api";
import { openStream } from "@/lib/streaming/stream-client";

import {
  analysisPlanSchema,
  analysisStreamEventSchema,
  regionSuggestionCollectionSchema,
} from "../schemas/analysis.schema";
import type {
  AnalysisPlan,
  AnalysisRunRequest,
  AnalysisStreamEvent,
  RegionSuggestion,
} from "../types/analysis.types";

export interface AnalysisStreamHandlers {
  onEvent: (event: AnalysisStreamEvent) => void;
  /** Called once with the number of frames that failed validation, after the stream closes. */
  onMalformedFrames?: (frameCount: number) => void;
}

export async function streamAnalysisRun(
  request: AnalysisRunRequest,
  handlers: AnalysisStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let malformedFrameCount = 0;

  await openStream({
    path: REST_API.investigations.runs(request.investigationId),
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

/**
 * The plan an autonomous investigation intends to run, fetched BEFORE execution.
 * Returning it first is what makes the macro an instrument rather than a scripted demo: the operator can
 * strike a step out, and a demo that lets a judge delete a step cannot have been rehearsed.
 */
export async function fetchAnalysisPlan(
  investigationId: string,
  fromClaimId: string,
  signal?: AbortSignal,
): Promise<AnalysisPlan> {
  const response = await apiClient.get(REST_API.investigations.plan(investigationId), {
    params: { from: fromClaimId },
    signal,
  });

  return parseApiResponse(analysisPlanSchema, response.data, "the investigation plan endpoint");
}

/**
 * Questions worth asking about a region the operator just drew.
 * Backend-driven, because what is worth asking about a polygon depends on what imagery covers it and
 * what has already been analysed there — neither of which the browser knows.
 */
export async function fetchRegionSuggestions(
  investigationId: string,
  bounds: { west: number; south: number; east: number; north: number },
  signal?: AbortSignal,
): Promise<RegionSuggestion[]> {
  const response = await apiClient.get(REST_API.regions.suggestions, {
    params: {
      investigationId,
      west: bounds.west,
      south: bounds.south,
      east: bounds.east,
      north: bounds.north,
    },
    signal,
  });

  const collection = parseApiResponse(
    regionSuggestionCollectionSchema,
    response.data,
    "the region suggestions endpoint",
  );

  return collection.suggestions;
}

/**
 * Parses one stream frame, dropping anything that does not match the contract.
 *
 * Dropping is right in production — one malformed frame must not abort a run that is otherwise
 * delivering — but a SILENT drop is not. A layer frame that fails validation looks exactly like a layer
 * the backend never sent, and the workspace renders "no evidence yet" with nothing anywhere saying why.
 * In development the reason is printed, because that is the difference between a five-minute fix and an
 * afternoon.
 */
function safeParseStreamFrame(rawData: string): AnalysisStreamEvent | null {
  try {
    const parsed = analysisStreamEventSchema.safeParse(JSON.parse(rawData));
    if (!parsed.success) {
      if (process.env.NODE_ENV !== "production") {
        console.warn("[AERIS] Analysis stream frame rejected by the contract.", parsed.error.issues);
      }
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
}
