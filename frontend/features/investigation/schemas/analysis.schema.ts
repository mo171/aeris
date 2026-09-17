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

import { parameterValueSchema } from "@/lib/constants/parameters";
import { PIPELINE_STAGE_CODES } from "@/lib/constants/pipeline-stages";
import { isoTimestampSchema } from "@/lib/schemas/geo.schema";
import { speechEventSchema, uiCommandEventSchema } from "@/lib/schemas/stream-events.schema";

import { claimSchema, evidenceItemSchema, insufficientEvidenceSchema } from "./evidence.schema";
import { colorRampIdSchema, evidenceLayerSchema } from "./layer.schema";

export const pipelineStageCodeSchema = z.enum(PIPELINE_STAGE_CODES);

export const nodeRefSchema = z.object({
  kind: z.enum(["scene", "region", "layer", "figure", "claim", "step"]),
  id: z.string().min(1),
});

export const traceStepStateSchema = z.enum([
  "pending",
  "running",
  "completed",
  "failed",
  "skipped",
]);

export const analysisStepSchema = z.object({
  id: z.string().min(1),
  /** Catalogue operation, when the step corresponds to one. Null for infrastructure stages (S1–S11). */
  operationId: z.string().nullable(),
  stageCode: pipelineStageCodeSchema,
  inputs: z.array(nodeRefSchema),
  /** Resolved values the step ran (or will run) with — never the request, always the truth. */
  parameters: z.record(z.string(), parameterValueSchema),
  outputs: z.array(nodeRefSchema),
  model: z.object({ id: z.string(), version: z.string() }).nullable(),
  /** Why this step / this model, authored by the planner. Catalogue rationale is the fallback. */
  rationale: z.string().nullable(),
  /** Step ids this step consumes. THE GRAPH. Without it the trace is a list; with it, a canvas. */
  dependsOn: z.array(z.string()),
});

export const analysisTraceStepSchema = analysisStepSchema.extend({
  detail: z.string().nullable(),
  state: traceStepStateSchema,
  durationMs: z.number().int().nonnegative().nullable(),
  /**
   * The intermediate product this stage generated, if it produced one worth inspecting.
   * Clicking the step loads this onto the scene as a temporary layer — the cloud mask, the registration
   * residual, the index map. This is what turns the trace from a progress bar into an instrument.
   */
  artefactLayerId: z.string().nullable(),
  artefactUri: z.string().nullable().optional(),
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
  parameterOverrides: z.record(z.string(), z.record(z.string(), parameterValueSchema)).nullable().optional(),
  rerunFromStepId: z.string().nullable().optional(),
  parentRunId: z.string().nullable().optional(),
});

export const analysisPlanStepSchema = analysisStepSchema.extend({
  title: z.string().min(1),
  description: z.string().min(1),
  /** The operator can strike a step out before the plan runs. A fixed plan is just a script. */
  isEnabled: z.boolean(),
});

export const analysisPlanSchema = z.object({
  id: z.string().min(1),
  summary: z.string().min(1),
  steps: z.array(analysisPlanStepSchema),
});

export const figureReadyEventSchema = z.object({
  type: z.literal("figure-ready"),
  runId: z.string().min(1),
  figureId: z.string().min(1),
  kind: z.enum([
    "rgb-composite",
    "index-map",
    "mask-overlay",
    "detection-overlay",
    "comparison",
    "histogram",
    "sar-backscatter",
  ]),
  title: z.string().min(1),
  caption: z.string().nullable(),
  imageUrl: z.string().min(1),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  traceStepId: z.string().min(1),
  claimIds: z.array(z.string().min(1)),
  legend: z.object({
    kind: z.enum(["continuous", "categorical", "binary"]),
    label: z.string().min(1),
    colorRamp: colorRampIdSchema,
    domain: z.array(z.number()).length(2).nullable(),
    entries: z
      .array(z.object({ color: z.string().regex(/^#[0-9a-fA-F]{6}$/), label: z.string().min(1) }))
      .nullable(),
  }),
  renderSpec: z.object({
    sceneIds: z.array(z.string()),
    bands: z.array(z.string()),
    stretch: z.record(z.string(), z.union([z.number(), z.string()])),
    colorRamp: colorRampIdSchema,
    resampling: z.string().min(1),
    crs: z.string().nullable(),
    decimation: z.number().int().positive(),
    maskApplied: z.boolean(),
  }),
  isPrimary: z.boolean(),
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
  uiCommandEventSchema,
  speechEventSchema,
  figureReadyEventSchema,
]);

export const regionSuggestionSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  prompt: z.string().min(1),
});

export const regionSuggestionCollectionSchema = z.object({
  suggestions: z.array(regionSuggestionSchema),
});
