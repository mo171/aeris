// features/investigation/schemas/analysis.schema.ts — the streamed analysis run: trace, layers, claims, answer.
//
// what  : Zod schemas for a trace step, the autonomous plan, and every event the run stream can emit.
// where : analysis.service.ts validates each raw SSE frame against analysisStreamEventSchema before it
//         reaches the run hook. Nothing unvalidated ever reaches the UI.
// how   : `layer-ready` is a separate event from `trace-step` on purpose, and it is the single most
//         important line in this file. The viewer must draw a change mask the moment it exists rather
//         than after the whole run finishes — that difference is what separates a workspace that feels
//         alive from one that feels like a form submission.
//
//         Every trace step carries its stage code and, where the stage produces one, the artefact layer
//         it can put on the map. The PDF's provenance requirements already oblige the backend to retain
//         those intermediates as addressable artefacts, so surfacing them costs a URI it already holds
//         and buys the operator the ability to click any step and see what the machine actually saw.
//
//         Steps are emitted twice — once `running`, once `completed` with a duration. That transition is
//         the execution-trace UI, and it must be exercised rather than reconstructed after the fact.

import { z } from "zod";

import { isoTimestampSchema } from "@/lib/schemas/geo.schema";
import { PIPELINE_STAGE_CODES } from "@/lib/constants/pipeline-stages";

import { claimSchema, evidenceItemSchema, insufficientEvidenceSchema } from "./evidence.schema";
import { evidenceLayerSchema } from "./layer.schema";

export const pipelineStageCodeSchema = z.enum(PIPELINE_STAGE_CODES);

export const traceStepStateSchema = z.enum([
  "pending",
  "running",
  "completed",
  "failed",
  "skipped",
]);

export const analysisTraceStepSchema = z.object({
  id: z.string().min(1),
  /** Looked up in lib/constants/pipeline-stages.ts for its label; the wire carries the code only. */
  stageCode: pipelineStageCodeSchema,
  detail: z.string().nullable(),
  state: traceStepStateSchema,
  durationMs: z.number().int().nonnegative().nullable(),
  modelId: z.string().nullable(),
  modelVersion: z.string().nullable(),
  /**
   * The intermediate product this stage generated, if it produced one worth inspecting.
   * Clicking the step loads this onto the scene as a temporary layer — the cloud mask, the registration
   * residual, the index map. This is what turns the trace from a progress bar into an instrument.
   */
  artefactLayerId: z.string().nullable(),
});

export const analysisIntentSchema = z.enum([
  "SCENE_VQA",
  "GROUND",
  "INDEX_QUERY",
  "DETECT",
  "SEGMENT",
  "CHANGE_DETECT",
  "CHANGE_VQA",
  "CROSS_MODAL",
  "EVIDENCE_RECALL",
]);

export const analysisRunStatusSchema = z.enum(["running", "complete", "failed", "cancelled"]);

export const analysisRunRequestSchema = z.object({
  investigationId: z.string().min(1),
  query: z.string().min(1, "Enter a question before sending."),
  /** Present when the operator scoped the question by drawing on the scene. */
  regionBounds: z
    .object({
      west: z.number(),
      south: z.number(),
      east: z.number(),
      north: z.number(),
    })
    .nullable(),
  /** Set when the run was launched by the autonomous macro rather than typed. */
  planId: z.string().nullable(),
  /**
   * The named operation the operator chose, when they chose one rather than typing.
   *
   * Sending the operation instead of only a sentence lets the backend dispatch directly rather than
   * classifying intent from language it may read wrong. Null means the request really is a free-text
   * question and intent classification is the right first stage.
   */
  operationId: z.string().nullable(),
});

export const analysisPlanStepSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  description: z.string().min(1),
  modelId: z.string().min(1),
  stageCode: pipelineStageCodeSchema,
  /** The operator can strike a step out before the plan runs. A fixed plan is just a script. */
  isEnabled: z.boolean(),
});

export const analysisPlanSchema = z.object({
  id: z.string().min(1),
  summary: z.string().min(1),
  steps: z.array(analysisPlanStepSchema),
});

export const analysisStreamEventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("run-start"),
    runId: z.string().min(1),
    intent: analysisIntentSchema,
    startedAt: isoTimestampSchema,
  }),
  z.object({
    type: z.literal("trace-step"),
    runId: z.string().min(1),
    step: analysisTraceStepSchema,
  }),
  z.object({
    type: z.literal("layer-ready"),
    runId: z.string().min(1),
    layer: evidenceLayerSchema,
    /** The evidence records this layer draws, delivered with it so nothing renders unattributed. */
    evidence: z.array(evidenceItemSchema),
  }),
  z.object({
    type: z.literal("claim"),
    runId: z.string().min(1),
    claim: claimSchema,
  }),
  z.object({
    type: z.literal("answer-token"),
    runId: z.string().min(1),
    text: z.string(),
  }),
  z.object({
    type: z.literal("run-complete"),
    runId: z.string().min(1),
    confidence: z.number().min(0).max(1).nullable(),
    insufficientEvidence: insufficientEvidenceSchema.nullable(),
    totalDurationMs: z.number().int().nonnegative(),
  }),
  z.object({
    type: z.literal("run-error"),
    runId: z.string().min(1),
    message: z.string().min(1),
  }),
  z.object({
    type: z.literal("ui-command"),
    runId: z.string().min(1),
    commandId: z.string().min(1),
    params: z.record(z.string(), z.any()),
    reason: z.string().min(1),
  }),
  z.object({
    type: z.literal("speech"),
    runId: z.string().min(1),
    claimIds: z.array(z.string()),
    audioUrl: z.string().url(),
    interruptible: z.boolean(),
    provisional: z.boolean().optional(),
  }),
  z.object({
    type: z.literal("figure-ready"),
    runId: z.string().min(1),
    figureId: z.string().min(1),
    isPrimary: z.boolean().optional(),
    legend: z.any(),
    renderSpec: z.any(),
  }),
]);

export const regionSuggestionSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  prompt: z.string().min(1),
});

export const regionSuggestionCollectionSchema = z.object({
  suggestions: z.array(regionSuggestionSchema),
});
