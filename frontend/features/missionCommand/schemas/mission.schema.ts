// features/missionCommand/schemas/mission.schema.ts — contract for missions and their globe representation.
//
// what  : Zod schemas for a mission record, a globe marker, and an ambient satellite track.
// where : Parsed by mission.service.ts; inferred types drive the mission list and the 3D marker layer.
// how   : Globe markers are intentionally a separate, much smaller shape than a full Mission. The marker
//         feed is unbounded (thousands of points uploaded to the GPU), so it carries only what the
//         renderer needs — position, status and magnitude — while the full record is fetched on demand.

import { z } from "zod";

import { createCursorPageSchema, geoPointSchema, isoTimestampSchema } from "./shared.schema";

export const missionStatusSchema = z.enum(["active", "monitoring", "alert", "archived"]);

export const missionAnalysisKindSchema = z.enum([
  "change-detection",
  "vegetation-health",
  "urban-growth",
  "flood-mapping",
  "cross-modal",
]);

export const missionSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  status: missionStatusSchema,
  analysisKind: missionAnalysisKindSchema,
  areaOfInterestName: z.string().min(1),
  centroid: geoPointSchema,
  createdAt: isoTimestampSchema,
  lastRunAt: isoTimestampSchema.nullable(),
  nextRunAt: isoTimestampSchema.nullable(),
  sceneCount: z.number().int().nonnegative(),
  /** Confidence of the most recent run, 0–1. Null before the first run completes. */
  confidence: z.number().min(0).max(1).nullable(),
  openAlertCount: z.number().int().nonnegative(),
  summary: z.string(),
});

export const missionPageSchema = createCursorPageSchema(missionSchema);

export const globeMarkerSchema = z.object({
  id: z.string().min(1),
  missionId: z.string().nullable(),
  label: z.string().min(1),
  position: geoPointSchema,
  status: missionStatusSchema,
  /** 0–1 relative importance; scales marker radius and pulse amplitude. */
  magnitude: z.number().min(0).max(1),
});

export const globeMarkerCollectionSchema = z.object({
  markers: z.array(globeMarkerSchema),
  generatedAt: isoTimestampSchema,
});

export const satelliteTrackSchema = z.object({
  id: z.string().min(1),
  platform: z.string().min(1),
  origin: geoPointSchema,
  destination: geoPointSchema,
  /** 0–1 position of the moving head along the arc at the time the payload was generated. */
  phase: z.number().min(0).max(1),
});

export const satelliteTrackCollectionSchema = z.object({
  tracks: z.array(satelliteTrackSchema),
  generatedAt: isoTimestampSchema,
});
