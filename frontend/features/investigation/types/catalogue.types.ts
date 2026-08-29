// features/investigation/types/catalogue.types.ts — the archive query types.
//
// what  : TypeScript types inferred from catalogue.schema.ts.
// where : Imported by catalogue.service.ts, use-catalogue-search.ts and the timeline filter controls.
// how   : Inferred rather than hand-written, so one definition produces both the runtime validator and
//         the compile-time type and a backend drift fails at the boundary rather than six components deep.

import type { z } from "zod";

import type {
  catalogueSearchResponseSchema,
  coverageGapSchema,
  pairRecommendationSchema,
  temporalQuerySchema,
} from "../schemas/catalogue.schema";
import type { acquisitionModalitySchema, acquisitionTilesSchema } from "../schemas/investigation.schema";

export type AcquisitionModality = z.infer<typeof acquisitionModalitySchema>;
export type AcquisitionTiles = z.infer<typeof acquisitionTilesSchema>;
export type TemporalQuery = z.infer<typeof temporalQuerySchema>;
export type CoverageGap = z.infer<typeof coverageGapSchema>;
export type PairRecommendation = z.infer<typeof pairRecommendationSchema>;
export type CatalogueSearchResponse = z.infer<typeof catalogueSearchResponseSchema>;
