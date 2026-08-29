// features/investigation/schemas/catalogue.schema.ts — the temporal archive query and what comes back.
//
// what  : Zod schemas for the request the workspace sends when it asks the archive what exists over an
//         area between two dates, and for the acquisitions, coverage holes and recommended pair returned.
// where : Parsed by catalogue.service.ts; the inferred types drive the timeline scrubber and its filters.
// how   : This is the contract the timeline exists to produce, and it is a different request from the one
//         the workspace used to make.
//
//         Before, the backend was handed two scene ids someone had picked and had no choice but to
//         process them. It could not say "there is nothing usable in that window", could not offer a
//         cleaner pair eleven days away, and could not be asked for a series rather than a pair — none of
//         that is expressible when the selection has already happened upstream.
//
//         Sending the WINDOW instead of the SELECTION moves that judgement to the side that has the
//         catalogue. The response is allowed to disagree with the request: `recommendedPair` may name
//         dates the operator did not choose, and `advisory` says why. The interface presents that as a
//         suggestion rather than applying it silently, because the operator owns the decision and has
//         context the catalogue does not.
//
//         The area of interest travels with the query. Search, crop, band maths and tiling are then one
//         bounded job against one request, instead of a scene lookup followed by a separate argument
//         about extent.

import { z } from "zod";

import { geoBoundingBoxSchema, isoTimestampSchema } from "@/lib/schemas/geo.schema";

import { acquisitionModalitySchema, acquisitionSchema } from "./investigation.schema";

export const temporalQuerySchema = z
  .object({
    areaOfInterest: geoBoundingBoxSchema,
    from: isoTimestampSchema,
    to: isoTimestampSchema,
    /** At least one, so an empty selection can never be read as "everything". */
    modalities: z.array(acquisitionModalitySchema).min(1),
    /** Optical acquisitions cloudier than this are catalogued in the response but not offered as inputs. */
    maximumCloudPercentage: z.number().min(0).max(100),
  })
  .refine((query) => Date.parse(query.from) < Date.parse(query.to), {
    message: "The start of the window must fall before its end.",
    path: ["from"],
  });

/** A stretch of the requested window with no usable acquisition in it. */
export const coverageGapSchema = z.object({
  from: isoTimestampSchema,
  to: isoTimestampSchema,
  days: z.number().int().nonnegative(),
  /** Why nothing is usable here — no pass, or every pass too cloudy. Read straight out to the operator. */
  reason: z.string().min(1),
});

/**
 * The pair the catalogue would choose for this window.
 *
 * Named separately from the operator's own selection so the two can disagree visibly. An interface that
 * silently substituted the backend's pair would be answering a question nobody asked.
 */
export const pairRecommendationSchema = z.object({
  t0SceneId: z.string().min(1),
  t1SceneId: z.string().min(1),
  separationDays: z.number().int().nonnegative(),
  /** Stated in the operator's terms — "clearest pair spanning the requested window", not a score. */
  reason: z.string().min(1),
});

export const catalogueSearchResponseSchema = z.object({
  /** Echoed back so a late response can be discarded rather than applied over a newer query. */
  query: temporalQuerySchema,
  acquisitions: z.array(acquisitionSchema),
  coverageGaps: z.array(coverageGapSchema),
  recommendedPair: pairRecommendationSchema.nullable(),
  /** A single sentence when the catalogue has something to say about the window. Null when it does not. */
  advisory: z.string().nullable(),
});
