// features/sceneInspector/types/scene-inspection.types.ts — inspector types.
//
// what  : TypeScript types inferred from scene-inspection.schema.ts.
// where : Imported by the inspector components and its service.
// how   : Inferred from the schema, so the validator and the type cannot disagree.

import type { z } from "zod";

import type { sceneInspectionSchema } from "../schemas/scene-inspection.schema";

export type SceneInspection = z.infer<typeof sceneInspectionSchema>;
