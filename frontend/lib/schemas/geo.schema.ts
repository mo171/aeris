// lib/schemas/geo.schema.ts — geospatial and pagination primitives shared by every feature's schemas.
//
// what  : Zod schemas for geographic points, bounding boxes, ISO timestamps and cursor pages.
//         Application-wide rather than feature-scoped: a latitude means the same thing on every surface,
//         and duplicating the definition per feature is how two surfaces end up disagreeing about it.
// where : Composed by every feature's Zod schemas — imagery, missions, investigations, evidence, reports.
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
