import { z } from "zod";

import { createCursorPageSchema, geoBoundingBoxSchema, geoPointSchema, isoTimestampSchema } from "@/lib/schemas/geo.schema";

export const projectSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  areaOfInterestName: z.string().min(1),
  areaOfInterest: geoBoundingBoxSchema.nullable(),
  centroid: geoPointSchema.nullable(),
  createdAt: isoTimestampSchema,
  updatedAt: isoTimestampSchema,
  lastActivityAt: isoTimestampSchema.nullable(),
});

export const projectPageSchema = createCursorPageSchema(projectSchema);

export const projectCreateRequestSchema = z.object({
  name: z.string().min(1, "Give the project a name."),
  areaOfInterestName: z.string().min(1),
  areaOfInterest: geoBoundingBoxSchema,
});
