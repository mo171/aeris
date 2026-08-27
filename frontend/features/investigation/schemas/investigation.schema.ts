// features/investigation/schemas/investigation.schema.ts — the investigation record and its scene slots.
//
// what  : Zod schemas for an investigation, the scenes attached to its role slots, the camera bookmark it
//         restores to, and the create handshake that starts the descent.
// where : Parsed by investigation.service.ts. The inferred types drive the header, the inputs panel and
//         the camera.
// how   : Scenes occupy named ROLES rather than sitting in a flat list. The comparator binds to roles —
//         t0 against t1 for temporal work, sar against t1 for cross-modal — which is what lets pages 3
//         and 4 be configurations of this same workspace rather than separate implementations of it.
//
//         The create response is deliberately small and must return fast. The camera is already flying by
//         the time it resolves, so anything expensive belongs in the analysis run that follows rather than
//         in this call: a slow create turns a continuous descent into a stall.

import { z } from "zod";

import { geoBoundingBoxSchema, geoPointSchema, isoTimestampSchema } from "@/lib/schemas/geo.schema";

export const investigationStatusSchema = z.enum(["draft", "running", "ready", "failed"]);

export const sceneRoleSchema = z.enum(["t0", "t1", "sar", "aux"]);

export const workspaceModeSchema = z.enum(["temporal", "crossModal"]);

/** A restorable camera pose, so a shared URL reopens the exact view the operator left. */
export const cameraBookmarkSchema = z.object({
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  altitudeMeters: z.number().positive(),
  headingDegrees: z.number(),
  pitchDegrees: z.number(),
});

export const investigationSceneSlotSchema = z.object({
  role: sceneRoleSchema,
  sceneId: z.string().min(1),
  name: z.string().min(1),
  capturedAt: isoTimestampSchema,
  modality: z.enum(["optical", "sar", "multispectral", "hyperspectral"]),
  sensorPlatform: z.string().min(1),
  groundSampleDistanceMeters: z.number().positive(),
  /** Null for SAR, which is unaffected by cloud. Zero would claim a cloud-free radar scene. */
  cloudCoverPercentage: z.number().min(0).max(100).nullable(),
  coordinateReferenceSystem: z.string().min(1),
  /** The layer this scene renders through, so the comparator can bind a role to a raster. */
  layerId: z.string().min(1),
});

export const investigationSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  areaOfInterestName: z.string().min(1),
  areaOfInterest: geoBoundingBoxSchema,
  centroid: geoPointSchema,
  status: investigationStatusSchema,
  mode: workspaceModeSchema,
  createdAt: isoTimestampSchema,
  updatedAt: isoTimestampSchema,
  sceneSlots: z.array(investigationSceneSlotSchema),
  cameraBookmark: cameraBookmarkSchema.nullable(),
  /** The question that started this investigation, carried down from Mission Command. */
  seedQuery: z.string().nullable(),
  missionId: z.string().nullable(),
  /** Provenance identity. Small, permanent, and the most credible element on the page. */
  traceId: z.string().min(1),
});

export const investigationSummarySchema = investigationSchema.pick({
  id: true,
  name: true,
  areaOfInterestName: true,
  status: true,
  mode: true,
  updatedAt: true,
  traceId: true,
});

export const investigationListSchema = z.object({
  items: z.array(investigationSummarySchema),
});

export const investigationCreateRequestSchema = z.object({
  sceneIds: z.array(z.string().min(1)).min(1, "Select at least one scene to investigate."),
  seedQuery: z.string().nullable(),
  missionId: z.string().nullable(),
});

export const investigationCreateResponseSchema = z.object({
  investigationId: z.string().min(1),
  areaOfInterestName: z.string().min(1),
  areaOfInterest: geoBoundingBoxSchema,
  /** Where the camera should already be heading by the time this response reaches the UI. */
  cameraTarget: z.object({
    latitude: z.number().min(-90).max(90),
    longitude: z.number().min(-180).max(180),
    altitudeMeters: z.number().positive(),
  }),
});
