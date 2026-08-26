// features/missionCommand/schemas/shared.schema.ts — geospatial and pagination primitives shared by every
// Mission Command schema.
//
// what  : Zod schemas for geographic points, bounding boxes, ISO timestamps and cursor pages.
// where : Composed by the imagery, mission, model and assistant schemas in this folder.
// how   : Every domain type in this feature is defined as a Zod schema first and its TypeScript type is
//         inferred from it. One definition therefore produces both the compile-time type and the runtime
//         validator, so a backend contract drift is caught at the boundary instead of surfacing as
//         undefined-property errors deep inside a component.

import { z } from "zod";

export const isoTimestampSchema = z.iso.datetime();

export const geoPointSchema = z.object({
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
});

export const geoBoundingBoxSchema = z.object({
  west: z.number().min(-180).max(180),
  south: z.number().min(-90).max(90),
  east: z.number().min(-180).max(180),
  north: z.number().min(-90).max(90),
});

/** Wraps any item schema in the standard cursor-page envelope returned by collection endpoints. */
export function createCursorPageSchema<TItemSchema extends z.ZodType>(itemSchema: TItemSchema) {
  return z.object({
    items: z.array(itemSchema),
    nextCursor: z.string().nullable(),
    totalCount: z.number().int().nonnegative().nullable(),
  });
}
