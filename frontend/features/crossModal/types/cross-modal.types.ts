// features/crossModal/types/cross-modal.types.ts — the cross-modal types.
//
// what  : TypeScript types inferred from cross-modal.schema.ts.
// where : Imported by the Lab's components, hooks and service.
// how   : Inferred rather than hand-written, so the wire contract and the types the components consume
//         cannot drift. Same rule the investigation feature follows.

import type { z } from "zod";

import type {
  agreementRowSchema,
  crossModalResultSchema,
  fusionVerdictSchema,
  modalityAdvisorySchema,
  polarisationSchema,
  sensorIdSchema,
  sensorRunSchema,
} from "../schemas/cross-modal.schema";

export type SensorId = z.infer<typeof sensorIdSchema>;
export type Polarisation = z.infer<typeof polarisationSchema>;
export type SensorRun = z.infer<typeof sensorRunSchema>;
export type AgreementRow = z.infer<typeof agreementRowSchema>;
export type ModalityAdvisory = z.infer<typeof modalityAdvisorySchema>;
export type FusionVerdict = z.infer<typeof fusionVerdictSchema>;
export type CrossModalResult = z.infer<typeof crossModalResultSchema>;
