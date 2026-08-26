// features/missionCommand/types/imagery.types.ts — imagery domain types, inferred from the Zod schemas.
//
// what  : TypeScript types for satellite scenes, sensor modality, processing state and upload tickets.
// where : Imported by imagery services, hooks and every component that renders scene metadata.
// how   : Types are inferred rather than hand-written so the validator and the type can never drift apart.
//         Change the schema and every consumer updates; there is no second definition to forget.

import type { z } from "zod";

import type {
  imageryCatalogPageSchema,
  imageryProcessingStateSchema,
  imagerySceneSchema,
  imageryUploadTicketSchema,
  sensorModalitySchema,
  temporalRoleSchema,
} from "../schemas/imagery.schema";

export type SensorModality = z.infer<typeof sensorModalitySchema>;
export type ImageryProcessingState = z.infer<typeof imageryProcessingStateSchema>;
export type TemporalRole = z.infer<typeof temporalRoleSchema>;
export type ImageryScene = z.infer<typeof imagerySceneSchema>;
export type ImageryCatalogPage = z.infer<typeof imageryCatalogPageSchema>;
export type ImageryUploadTicket = z.infer<typeof imageryUploadTicketSchema>;

/** Progress of a single file moving from the operator's disk to cloud storage. */
export interface ImageryUploadTask {
  localId: string;
  fileName: string;
  fileSizeBytes: number;
  progressPercentage: number;
  state: "preparing" | "uploading" | "processing" | "complete" | "failed";
  errorMessage: string | null;
}
