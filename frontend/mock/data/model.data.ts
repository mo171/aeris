// mock/data/model.data.ts — live health for the specialist model fleet.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : Runtime status records for the models declared in lib/constants/models.ts.
// where : Served by the model status route; rendered by the ModelStatusStrip and the Model Observatory.
// how   : Ids come from the catalogue, not from here — this file supplies only what a real status feed
//         would: version, health, latency and queue depth. Fixed rather than generated, and deliberately
//         including one degraded and one warming entry so the non-healthy states are visible during review
//         instead of only in theory.

import type { ModelStatus } from "@/features/missionCommand/types/model.types";

export const MOCK_MODEL_STATUSES: readonly ModelStatus[] = [
  { id: "rs-vlm", version: "1.4.2", health: "online", medianLatencyMs: 1_840, queueDepth: 2 },
  {
    id: "grounding-dino-sam",
    version: "2.1.0",
    health: "online",
    medianLatencyMs: 2_310,
    queueDepth: 1,
  },
  { id: "changeformer", version: "3.0.1", health: "online", medianLatencyMs: 3_120, queueDepth: 4 },
  {
    id: "segformer-landcover",
    version: "1.9.7",
    health: "degraded",
    medianLatencyMs: 6_480,
    queueDepth: 11,
  },
  {
    id: "dota-detector",
    version: "2.3.4",
    health: "online",
    medianLatencyMs: 1_260,
    queueDepth: 0,
  },
  { id: "index-engine", version: "4.0.0", health: "online", medianLatencyMs: 210, queueDepth: 0 },
  {
    id: "optical-sar-fusion",
    version: "0.9.3",
    health: "warming",
    medianLatencyMs: 4_950,
    queueDepth: 3,
  },
  { id: "s2cloudless", version: "1.5.0", health: "online", medianLatencyMs: 640, queueDepth: 0 },
  {
    id: "co-registration",
    version: "0.7.1",
    health: "online",
    medianLatencyMs: 980,
    queueDepth: 1,
  },
  {
    id: "sar-preprocess",
    version: "0.9.2",
    health: "online",
    medianLatencyMs: 2_040,
    queueDepth: 0,
  },
];
