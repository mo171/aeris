import { z } from "zod";

import type { CursorPage } from "@/lib/types/api.types";
import { projectCreateRequestSchema, projectSchema } from "../schemas/project.schema";

export type Project = z.infer<typeof projectSchema>;
export type ProjectCreateRequest = z.infer<typeof projectCreateRequestSchema>;
export type ProjectPage = CursorPage<Project>;
