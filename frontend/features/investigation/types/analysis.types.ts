// features/investigation/types/analysis.types.ts — the streamed analysis run types.
//
// what  : TypeScript types inferred from analysis.schema.ts, plus the assembled run state the UI reads.
// where : Imported by the run hook, the execution spine and analysis.service.ts.
// how   : AnalysisStreamEvent is a discriminated union on `type`, so a switch over it is exhaustiveness
//         checked. Adding a new event kind surfaces every handler that needs updating at compile time
//         rather than silently dropping frames at runtime.

import type { z } from "zod";

import type {
  analysisIntentSchema,
  analysisPlanSchema,
  analysisPlanStepSchema,
  analysisRunRequestSchema,
  analysisRunStatusSchema,
  analysisStreamEventSchema,
  analysisTraceStepSchema,
  pipelineStageCodeSchema,
  regionSuggestionSchema,
  traceStepStateSchema,
} from "../schemas/analysis.schema";
import type { InsufficientEvidence } from "./evidence.types";

export type PipelineStageCodeValue = z.infer<typeof pipelineStageCodeSchema>;
export type TraceStepState = z.infer<typeof traceStepStateSchema>;
export type AnalysisTraceStep = z.infer<typeof analysisTraceStepSchema>;
export type AnalysisIntent = z.infer<typeof analysisIntentSchema>;
export type AnalysisRunStatus = z.infer<typeof analysisRunStatusSchema>;
export type AnalysisRunRequest = z.infer<typeof analysisRunRequestSchema>;
export type AnalysisPlanStep = z.infer<typeof analysisPlanStepSchema>;
export type AnalysisPlan = z.infer<typeof analysisPlanSchema>;
export type AnalysisStreamEvent = z.infer<typeof analysisStreamEventSchema>;
export type RegionSuggestion = z.infer<typeof regionSuggestionSchema>;

/** One completed or in-flight analysis, folded from the stream. */
export interface AnalysisRun {
  id: string;
  query: string;
  intent: AnalysisIntent | null;
  status: AnalysisRunStatus;
  startedAt: string;
  answerText: string;
  confidence: number | null;
  insufficientEvidence: InsufficientEvidence | null;
  traceSteps: AnalysisTraceStep[];
  claimIds: string[];
  totalDurationMs: number | null;
}
