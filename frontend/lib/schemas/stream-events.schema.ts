// Shared stream events whose payload is independent of the transport surface that carries them.
//
// Both schemas keep `runId`: speech and interface actions belong to the scientific run whose evidence
// authorises them, even when they arrive beside assistant-message events. The frontend command registry
// remains authoritative for command-specific parameter validation.

import { z } from "zod";

export const uiCommandEventSchema = z.object({
  type: z.literal("ui-command"),
  runId: z.string().min(1),
  commandId: z.string().min(1),
  params: z.record(z.string(), z.unknown()),
  reason: z.string().min(1),
});

export const speechEventSchema = z.object({
  type: z.literal("speech"),
  runId: z.string().min(1),
  utteranceId: z.string().min(1),
  text: z.string().min(1),
  audioUrl: z.url().nullable(),
  claimIds: z.array(z.string().min(1)),
  interruptible: z.boolean(),
  provisional: z.boolean(),
  supersedesUtteranceId: z.string().min(1).nullable(),
});
