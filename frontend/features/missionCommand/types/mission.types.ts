// features/missionCommand/types/mission.types.ts — mission domain types, inferred from the Zod schemas.
//
// what  : TypeScript types for missions, their status and analysis kind, and paginated mission responses.
// where : Imported by mission services, hooks and the Active Missions list.
// how   : See imagery.types.ts — types are inferred from schemas so validator and type stay in lockstep.

import type { z } from "zod";

import type {
  missionAnalysisKindSchema,
  missionCreateRequestSchema,
  missionPageSchema,
  missionSchema,
  missionStatusSchema,
} from "../schemas/mission.schema";

export type MissionStatus = z.infer<typeof missionStatusSchema>;
export type MissionAnalysisKind = z.infer<typeof missionAnalysisKindSchema>;
export type Mission = z.infer<typeof missionSchema>;
export type MissionPage = z.infer<typeof missionPageSchema>;
export type MissionCreateRequest = z.infer<typeof missionCreateRequestSchema>;
