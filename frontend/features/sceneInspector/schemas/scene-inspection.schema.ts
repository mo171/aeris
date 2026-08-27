// features/sceneInspector/schemas/scene-inspection.schema.ts — the contract for one scene, inspected alone.
//
// what  : Zod schema for everything the scene inspector window needs: the acquisition, its quicklook, and
//         the area of interest it belongs to.
// where : Parsed by scene-inspection.service.ts; drives the pop-out window.
// how   : Deliberately self-contained. The inspector opens as a separate browser window with its own
//         JavaScript context — it cannot read the workspace's stores or query cache, and should not try.
//         Everything it needs arrives from one request keyed by scene id, which is also what makes the
//         window shareable as a plain URL.

import { z } from "zod";

import { geoBoundingBoxSchema } from "@/lib/schemas/geo.schema";
import { acquisitionSchema } from "@/features/investigation/schemas/investigation.schema";

export const sceneInspectionSchema = z.object({
  acquisition: acquisitionSchema,
  investigationId: z.string().min(1),
  areaOfInterestName: z.string().min(1),
  areaOfInterest: geoBoundingBoxSchema,
  coordinateReferenceSystem: z.string().min(1),
  /** Band descriptors, so the inspector can state what the sensor actually recorded. */
  bands: z.array(
    z.object({
      name: z.string().min(1),
      wavelengthNanometres: z.number().positive().nullable(),
      description: z.string(),
    }),
  ),
});
