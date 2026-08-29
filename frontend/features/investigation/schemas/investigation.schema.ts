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

/**
 * One acquisition over the area of interest.
 *
 * An investigation is not a pair of images, it is a time series that a pair is currently selected from.
 * Modelling it that way is what makes a timeline possible at all: with only T0 and T1 on the wire there
 * is nothing to scrub through, and retrofitting the stack later would change every consumer.
 *
 * `quicklookUrl` is a single rendered image of the scene, not a tile template — enough to recognise the
 * place and judge cloud cover before committing to loading it.
 */
export const acquisitionModalitySchema = z.enum([
  "optical",
  "sar",
  "multispectral",
  "hyperspectral",
]);

/**
 * Where the pixels for one acquisition actually live.
 *
 * Carried on the acquisition rather than resolved separately, because scrubbing the timeline has to be
 * able to put any date on the scene without a second round trip. A catalogue that lists observations but
 * cannot say where to fetch them turns every scrub into a request the operator waits on.
 */
export const acquisitionTilesSchema = z.object({
  urlTemplate: z.string().min(1),
  attribution: z.string().nullable(),
  minimumZoom: z.number().int().nonnegative(),
  maximumZoom: z.number().int().nonnegative(),
});

export const acquisitionSchema = z.object({
  id: z.string().min(1),
  sceneId: z.string().min(1),
  capturedAt: isoTimestampSchema,
  modality: acquisitionModalitySchema,
  sensorPlatform: z.string().min(1),
  groundSampleDistanceMeters: z.number().positive(),
  /** Null for SAR, which is unaffected by cloud. Zero would claim a cloud-free radar scene. */
  cloudCoverPercentage: z.number().min(0).max(100).nullable(),
  quicklookUrl: z.string().nullable(),
  /** Null when the acquisition is catalogued but has not been tiled, so it cannot be scrubbed to. */
  tiles: acquisitionTilesSchema.nullable(),
  /** False when the acquisition is catalogued but not yet processed to a usable product. */
  isAvailable: z.boolean(),
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
  /** Every acquisition over this area of interest, oldest first. The timeline scrubs across these. */
  acquisitions: z.array(acquisitionSchema),
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
