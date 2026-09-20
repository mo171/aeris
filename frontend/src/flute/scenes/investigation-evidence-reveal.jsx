"use client";

import React from "react";
import { Surface } from "@webprodigies/flute";

import { GeoStage } from "@/components/sharedUI/functionalComponent/geoStage/GeoStage";
import { EvidenceTab } from "@/features/investigation/components/answerPanel/EvidenceTab";

const surfaceStyle = {
  position: "absolute",
  overflow: "hidden",
};

const previewRun = {
  id: "flute-evidence-reveal",
  query: "Has built-up area increased across the area of interest?",
  intent: null,
  status: "completed",
  startedAt: "2026-09-20T00:00:00.000Z",
  answerText: "",
  confidence: 0.94,
  insufficientEvidence: null,
  traceSteps: [],
  claimIds: ["built-up-change"],
  totalDurationMs: 4200,
};

const previewClaims = {
  "built-up-change": {
    id: "built-up-change",
    text: "Built-up area increased across the area of interest.",
    traceStepId: "inv_1vgbgkv-step-S13",
    modelId: "changeformer",
    modelVersion: "1.2.0",
    evidenceIds: ["change-mask", "new-structures", "area-statistics"],
  },
};

const previewEvidence = {
  "change-mask": {
    id: "change-mask",
    title: "Change mask",
    kind: "raster",
    layerId: "inv_1vgbgkv-layer-change",
    sourceSceneIds: [],
  },
  "new-structures": {
    id: "new-structures",
    title: "New structures",
    kind: "vector",
    layerId: "inv_1vgbgkv-layer-buildings",
    sourceSceneIds: [],
  },
  "area-statistics": {
    id: "area-statistics",
    title: "Area statistics",
    kind: "metric",
    layerId: null,
    sourceSceneIds: [],
  },
};

export default function InvestigationEvidenceRevealScene() {
  return (
    <>
      <Surface id="evidence-stage" style={{ ...surfaceStyle, inset: 0, zIndex: 0 }}>
        <GeoStage />
      </Surface>

      <Surface
        id="evidence-panel"
        style={{
          ...surfaceStyle,
          top: 56,
          right: 18,
          bottom: 24,
          width: 980,
          zIndex: 3,
          border: "1px solid rgba(120, 180, 220, 0.22)",
          borderRadius: 10,
          background: "rgba(12, 17, 29, 0.86)",
          boxShadow: "0 28px 90px rgba(0, 0, 0, 0.5)",
        }}
      >
        <div style={{ height: "100%", padding: 12 }}>
          <EvidenceTab
            currentRun={previewRun}
            claimsById={previewClaims}
            evidenceById={previewEvidence}
          />
        </div>
      </Surface>
    </>
  );
}
