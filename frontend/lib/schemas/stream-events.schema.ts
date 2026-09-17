// Shared stream events whose payload is independent of the transport surface that carries them.
//
// Both schemas keep `runId`: speech and interface actions belong to the scientific run whose evidence
// authorises them, even when they arrive beside assistant-message events. Speech `kind` is the truth-source
// discriminator; the retained `provisional` boolean must agree with it because clients render that state
// directly. The frontend command registry remains authoritative for command-specific parameter validation.

import { z } from "zod";

export const uiCommandEventSchema = z.object({
  type: z.literal("ui-command"),
  runId: z.string().min(1),
  commandId: z.string().min(1),
  params: z.record(z.string(), z.unknown()),
  reason: z.string().min(1),
});

export const speechKindSchema = z.enum(["grounded", "provisional", "progress", "refusal"]);

const normalisedAudioLocationSchema = z.string().trim().min(1);

const absoluteAudioUrlSchema = normalisedAudioLocationSchema.url({ protocol: /^https?$/ });

const sameOriginAudioPathSchema = normalisedAudioLocationSchema.regex(
  /^\/(?:[^/\s]\S*)?$/,
  "Audio paths must be root-relative and cannot be protocol-relative.",
);

export const audioLocationSchema = z
  .union([absoluteAudioUrlSchema, sameOriginAudioPathSchema])
  .nullable();

export const speechEventSchema = z
  .object({
    type: z.literal("speech"),
    runId: z.string().min(1),
    utteranceId: z.string().min(1),
    kind: speechKindSchema,
    text: z.string().min(1),
    audioUrl: audioLocationSchema,
    claimIds: z.array(z.string().min(1)),
    interruptible: z.boolean(),
    provisional: z.boolean(),
    supersedesUtteranceId: z.string().min(1).nullable(),
  })
  .superRefine((event, context) => {
    const isProvisional = event.kind === "provisional";
    if (event.provisional !== isProvisional) {
      context.addIssue({
        code: "custom",
        path: ["provisional"],
        message: "provisional must be true exactly when kind is provisional",
      });
    }
    if (event.kind === "grounded" && event.claimIds.length === 0) {
      context.addIssue({
        code: "custom",
        path: ["claimIds"],
        message: "grounded speech requires at least one claim id",
      });
    }
    if (isProvisional && event.claimIds.length > 0) {
      context.addIssue({
        code: "custom",
        path: ["claimIds"],
        message: "provisional speech cannot carry claim ids",
      });
    }
    if (event.kind === "refusal" && event.interruptible) {
      context.addIssue({
        code: "custom",
        path: ["interruptible"],
        message: "refusal speech must be non-interruptible",
      });
    }
  });
