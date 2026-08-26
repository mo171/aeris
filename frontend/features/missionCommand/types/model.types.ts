// features/missionCommand/types/model.types.ts — specialist model registry types, inferred from schemas.
//
// what  : TypeScript types for model health, capability and the status collection.
// where : Imported by model-registry.service.ts, use-model-status.ts and the ModelStatusStrip component.
// how   : See imagery.types.ts.

import type { z } from "zod";

import type {
  modelCapabilitySchema,
  modelHealthSchema,
  modelStatusCollectionSchema,
  modelStatusSchema,
} from "../schemas/model.schema";

export type ModelHealth = z.infer<typeof modelHealthSchema>;
export type ModelCapability = z.infer<typeof modelCapabilitySchema>;
export type ModelStatus = z.infer<typeof modelStatusSchema>;
export type ModelStatusCollection = z.infer<typeof modelStatusCollectionSchema>;
