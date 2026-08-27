// features/investigation/types/investigation.types.ts — the investigation record types.
//
// what  : TypeScript types inferred from investigation.schema.ts.
// where : Imported by the header, the inputs panel, the camera hook and investigation.service.ts.
// how   : Inferred rather than hand-written, so one definition produces both the runtime validator and
//         the compile-time type. A backend contract drift then fails at the boundary instead of surfacing
//         as an undefined property six components deep.

import type { z } from "zod";

import type {
  cameraBookmarkSchema,
  investigationCreateRequestSchema,
  investigationCreateResponseSchema,
  investigationSceneSlotSchema,
  investigationSchema,
  investigationSummarySchema,
  sceneRoleSchema,
  workspaceModeSchema,
} from "../schemas/investigation.schema";

export type SceneRole = z.infer<typeof sceneRoleSchema>;
export type WorkspaceMode = z.infer<typeof workspaceModeSchema>;
export type CameraBookmark = z.infer<typeof cameraBookmarkSchema>;
export type InvestigationSceneSlot = z.infer<typeof investigationSceneSlotSchema>;
export type Investigation = z.infer<typeof investigationSchema>;
export type InvestigationSummary = z.infer<typeof investigationSummarySchema>;
export type InvestigationCreateRequest = z.infer<typeof investigationCreateRequestSchema>;
export type InvestigationCreateResponse = z.infer<typeof investigationCreateResponseSchema>;
