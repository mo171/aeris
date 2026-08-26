// features/missionCommand/schemas/imagery.schema.ts — contract for satellite scenes and the upload handshake.
//
// what  : Zod schemas describing an imagery scene, its acquisition metadata, and the signed-upload ticket.
// where : Parsed by imagery.service.ts on every response; the inferred types flow out to hooks and UI.
// how   : Scene metadata is the evidence trail for every downstream analysis, so it is validated rather
//         than trusted — a scene missing its CRS or ground sample distance must fail loudly here, not
//         silently produce a wrong hectare figure six screens later.

import { z } from "zod";

import { createCursorPageSchema, geoBoundingBoxSchema, geoPointSchema, isoTimestampSchema } from "@/lib/schemas/geo.schema";

export const sensorModalitySchema = z.enum(["optical", "sar", "multispectral", "hyperspectral"]);

export const imageryProcessingStateSchema = z.enum(["queued", "processing", "ready", "failed"]);

/** Which side of a bi-temporal pair this scene occupies, if any. */
export const temporalRoleSchema = z.enum(["single", "t0", "t1"]);

export const imagerySceneSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  capturedAt: isoTimestampSchema,
  ingestedAt: isoTimestampSchema,
  modality: sensorModalitySchema,
  sensorPlatform: z.string().min(1),
  bandCount: z.number().int().positive(),
  groundSampleDistanceMeters: z.number().positive(),
  /** Null for SAR, which is unaffected by cloud. */
  cloudCoverPercentage: z.number().min(0).max(100).nullable(),
  coordinateReferenceSystem: z.string().min(1),
  boundingBox: geoBoundingBoxSchema,
  centroid: geoPointSchema,
  fileSizeBytes: z.number().int().nonnegative(),
  processingState: imageryProcessingStateSchema,
  temporalRole: temporalRoleSchema,
  thumbnailUrl: z.string().nullable(),
});

export const imageryCatalogPageSchema = createCursorPageSchema(imagerySceneSchema);

/**
 * Signed-URL handshake. Files upload directly to cloud storage and never pass through the backend,
 * which is why the ticket carries the headers the storage provider requires.
 */
export const imageryUploadTicketSchema = z.object({
  sceneId: z.string().min(1),
  uploadUrl: z.string().min(1),
  expiresAt: isoTimestampSchema,
  requiredHeaders: z.record(z.string(), z.string()),
});
