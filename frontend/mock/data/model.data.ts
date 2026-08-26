// mock/data/model.data.ts — the specialist model fleet as it will appear in the registry.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : Static status records for the specialist models named in the AERIS system design.
// where : Served by the model status route, rendered by the ModelStatusStrip.
// how   : Fixed rather than generated. These are the real models the platform routes to, so the strip
//         should read exactly as it will in production — including one degraded and one warming entry, so
//         the non-healthy states are visible during review instead of only in theory.

import type { ModelStatus } from "@/features/missionCommand/types/model.types";

export const MOCK_MODEL_STATUSES: readonly ModelStatus[] = [
  {
    id: "mdl_rsvlm",
    name: "GeoChat RS-VLM",
    capability: "vision-language",
    version: "1.4.2",
    health: "online",
    medianLatencyMs: 1_840,
    queueDepth: 2,
  },
  {
    id: "mdl_grounding",
    name: "Grounding DINO + SAM",
    capability: "grounding",
    version: "2.1.0",
    health: "online",
    medianLatencyMs: 2_310,
    queueDepth: 1,
  },
  {
    id: "mdl_changeformer",
    name: "ChangeFormer",
    capability: "change-detection",
    version: "3.0.1",
    health: "online",
    medianLatencyMs: 3_120,
    queueDepth: 4,
  },
  {
    id: "mdl_segformer",
    name: "SegFormer-B4 LandCover",
    capability: "segmentation",
    version: "1.9.7",
    health: "degraded",
    medianLatencyMs: 6_480,
    queueDepth: 11,
  },
  {
    id: "mdl_dota",
    name: "DOTA Object Detector",
    capability: "object-detection",
    version: "2.3.4",
    health: "online",
    medianLatencyMs: 1_260,
    queueDepth: 0,
  },
  {
    id: "mdl_spectral",
    name: "Spectral Index Engine",
    capability: "spectral-index",
    version: "4.0.0",
    health: "online",
    medianLatencyMs: 210,
    queueDepth: 0,
  },
  {
    id: "mdl_fusion",
    name: "Optical-SAR Late Fusion",
    capability: "cross-modal-fusion",
    version: "0.9.3",
    health: "warming",
    medianLatencyMs: 4_950,
    queueDepth: 3,
  },
];
