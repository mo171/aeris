// features/missionCommand/schemas/assistant.schema.ts — the streamed agent wire format.
//
// what  : Zod schemas for execution-trace steps, assistant messages, suggestions, and every event that can
//         arrive over the assistant SSE stream.
// where : assistant.service.ts validates each raw stream frame against assistantStreamEventSchema before
//         it reaches the session hook. Nothing unvalidated ever reaches the UI.
// how   : The stream is a discriminated union on `type`. Validating per frame means a malformed or
//         truncated frame is dropped as data instead of corrupting the transcript — important because the
//         assistant panel is append-only and cannot recover from a bad write.

import { z } from "zod";

import { isoTimestampSchema } from "@/lib/schemas/geo.schema";

export const executionStepStateSchema = z.enum(["pending", "running", "completed", "failed", "skipped"]);

export const executionTraceStepSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  detail: z.string().nullable(),
  state: executionStepStateSchema,
  /** Populated once the step finishes; drives the timing column in the trace UI. */
  durationMs: z.number().int().nonnegative().nullable(),
  /** Which specialist model executed this step, when one was involved. */
  modelId: z.string().nullable(),
});

export const assistantRoleSchema = z.enum(["operator", "aeris"]);

export const assistantMessageStatusSchema = z.enum(["streaming", "complete", "failed"]);

export const assistantMessageSchema = z.object({
  id: z.string().min(1),
  role: assistantRoleSchema,
  content: z.string(),
  createdAt: isoTimestampSchema,
  status: assistantMessageStatusSchema,
  trace: z.array(executionTraceStepSchema),
  /** 0–1. Null for operator messages and for answers where AERIS declines to assert one. */
  confidence: z.number().min(0).max(1).nullable(),
  evidenceRegionCount: z.number().int().nonnegative(),
});

export const assistantSuggestionSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  prompt: z.string().min(1),
  /** Which of the three analysis pillars this suggestion exercises. */
  pillar: z.enum(["single-image", "temporal", "cross-modal"]),
});

export const assistantSuggestionCollectionSchema = z.object({
  suggestions: z.array(assistantSuggestionSchema),
});

export const assistantStreamEventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("message-start"),
    messageId: z.string().min(1),
    createdAt: isoTimestampSchema,
  }),
  z.object({
    type: z.literal("trace-step"),
    messageId: z.string().min(1),
    step: executionTraceStepSchema,
  }),
  z.object({
    type: z.literal("token"),
    messageId: z.string().min(1),
    text: z.string(),
  }),
  z.object({
    type: z.literal("message-complete"),
    messageId: z.string().min(1),
    confidence: z.number().min(0).max(1).nullable(),
    evidenceRegionCount: z.number().int().nonnegative(),
  }),
  z.object({
    type: z.literal("stream-error"),
    messageId: z.string().min(1),
    message: z.string().min(1),
  }),
  z.object({
    type: z.literal("ui-command"),
    messageId: z.string().min(1),
    commandId: z.string().min(1),
    params: z.record(z.string(), z.any()),
    reason: z.string().min(1),
  }),
  z.object({
    type: z.literal("speech"),
    messageId: z.string().min(1),
    claimIds: z.array(z.string()),
    audioUrl: z.string().url(),
    interruptible: z.boolean(),
    provisional: z.boolean().optional(),
  }),
  z.object({
    type: z.literal("figure-ready"),
    messageId: z.string().min(1),
    figureId: z.string().min(1),
    isPrimary: z.boolean().optional(),
    legend: z.any(),
    renderSpec: z.any(),
  }),
]);

export const assistantAskRequestSchema = z.object({
  prompt: z.string().min(1, "Enter a question before sending."),
  sessionId: z.string().min(1),
  /** Scene ids the operator has selected as context for this question. */
  sceneIds: z.array(z.string()),
});
