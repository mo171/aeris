// features/missionCommand/schemas/model.schema.ts — contract for the specialist model fleet's live health.
//
// what  : Zod schema for the runtime state of each specialist model — health, latency and queue depth.
// where : Parsed by model-registry.service.ts; drives the Model Status strip and the Model Observatory.
// how   : THE WIRE CARRIES THE ID AND THE LIVE NUMBERS, NOTHING ELSE. What a model is called, what it does
//         and why the router picks it are authored copy in lib/constants/models.ts, on the same rule
//         pipeline-stages.ts follows — that copy should be editable without a backend deploy, and a
//         payload that also carried it could disagree with the catalogue.
//
//         Health is a four-state enum rather than a boolean because "warming" and "degraded" change what
//         the router will do, and an operator should see that before asking a question rather than after
//         it fails.

import { z } from "zod";

import { MODEL_IDS } from "@/lib/constants/models";

export const modelHealthSchema = z.enum(["online", "warming", "degraded", "offline"]);

/** An id the catalogue does not know fails here rather than rendering as a nameless row. */
export const modelIdSchema = z.enum(MODEL_IDS);

export const modelStatusSchema = z.object({
  id: modelIdSchema,
  version: z.string().min(1),
  health: modelHealthSchema,
  medianLatencyMs: z.number().int().nonnegative(),
  queueDepth: z.number().int().nonnegative(),
});

export const modelStatusCollectionSchema = z.object({
  models: z.array(modelStatusSchema),
  checkedAt: z.iso.datetime(),
});
