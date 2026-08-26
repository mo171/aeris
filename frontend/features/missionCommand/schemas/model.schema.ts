// features/missionCommand/schemas/model.schema.ts — contract for the specialist model registry status feed.
//
// what  : Zod schema for the health and load of each specialist remote-sensing model AERIS can dispatch to.
// where : Parsed by model-registry.service.ts; drives the Model Status strip in the data panel.
// how   : AERIS routes each question to a specialist model, so an operator must be able to see at a glance
//         which capabilities are actually available before asking. Health is a four-state enum rather than
//         a boolean because "warming" and "degraded" change what the router will do.

import { z } from "zod";

export const modelHealthSchema = z.enum(["online", "warming", "degraded", "offline"]);

export const modelCapabilitySchema = z.enum([
  "vision-language",
  "grounding",
  "change-detection",
  "segmentation",
  "object-detection",
  "spectral-index",
  "cross-modal-fusion",
]);

export const modelStatusSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  capability: modelCapabilitySchema,
  version: z.string().min(1),
  health: modelHealthSchema,
  medianLatencyMs: z.number().int().nonnegative(),
  queueDepth: z.number().int().nonnegative(),
});

export const modelStatusCollectionSchema = z.object({
  models: z.array(modelStatusSchema),
  checkedAt: z.iso.datetime(),
});
