// mock/data/version.data.ts — pre-seeded investigation versions for Phase D.
//
// what  : Mock versions representing an operator's edit to the change threshold,
//         to verify the diff engine and VersionCompareSheet render correctly.
// where : Used by use-investigation-versions.ts and mock routes.
// how   : In Phase 1, versions are stored in memory just like investigations.

import type { InvestigationVersion } from "@/features/investigation/types/version.types";

/**
 * An in-memory store of versions, keyed by investigationId.
 */
const versionsByInvestigation = new Map<string, InvestigationVersion[]>();

export function getMockVersions(investigationId: string): InvestigationVersion[] {
  let versions = versionsByInvestigation.get(investigationId);
  if (!versions) {
    // Seed with two versions to demonstrate diffing
    versions = [
      {
        id: "v1",
        label: "Initial baseline",
        actor: "agent",
        createdAt: new Date(Date.now() - 3600000).toISOString(), // 1 hour ago
        parentVersionId: null,
        snapshot: {
          sceneSlots: [
            {
              role: "t0",
              sceneId: "scene_opt_2023",
              name: "Baseline 2023",
              capturedAt: new Date().toISOString(),
              modality: "optical",
              sensorPlatform: "Sentinel-2",
              groundSampleDistanceMeters: 10,
              cloudCoverPercentage: 0,
              coordinateReferenceSystem: "EPSG:32631",
              layerId: "layer_opt_2023",
            },
            {
              role: "t1",
              sceneId: "scene_opt_2024",
              name: "Comparison 2024",
              capturedAt: new Date().toISOString(),
              modality: "optical",
              sensorPlatform: "Sentinel-2",
              groundSampleDistanceMeters: 10,
              cloudCoverPercentage: 0,
              coordinateReferenceSystem: "EPSG:32631",
              layerId: "layer_opt_2024",
            },
          ],
          timelinePair: {
            baselineSceneId: "scene_opt_2023",
            comparisonSceneId: "scene_opt_2024",
          },
          steps: [
            {
              id: "step-1",
              stageCode: "S1",
              operationId: "investigation.selectScenes",
              state: "completed",
              inputs: [],
              outputs: [],
              parameters: {},
              durationMs: 450,
              rationale: "Selected optical imagery for change detection.",
              model: null,
              dependsOn: [],
              detail: null,
              artefactLayerId: null,
            },
            {
              id: "step-2",
              stageCode: "S13",
              operationId: "investigation.detectChange",
              state: "completed",
              inputs: [],
              outputs: [],
              parameters: { threshold: 0.35 },
              durationMs: 1200,
              rationale: "Detected changes with strict threshold.",
              model: { id: "aeris-change-detect", version: "1.2" },
              dependsOn: ["step-1"],
              detail: null,
              artefactLayerId: null,
            },
          ],
          resultSummary: {
            claimMetrics: [
              { claimId: "claim-1", label: "Area changed", value: 45.2, unit: "ha" },
            ],
            confidence: 0.88,
          },
          layerIds: ["layer-change"],
          traceId: "tr_mock_v1",
        },
      },
      {
        id: "v2",
        label: "Relaxed threshold",
        actor: "operator",
        createdAt: new Date().toISOString(), // Now
        parentVersionId: "v1",
        snapshot: {
          sceneSlots: [
            {
              role: "t0",
              sceneId: "scene_opt_2023",
              name: "Baseline 2023",
              capturedAt: new Date().toISOString(),
              modality: "optical",
              sensorPlatform: "Sentinel-2",
              groundSampleDistanceMeters: 10,
              cloudCoverPercentage: 0,
              coordinateReferenceSystem: "EPSG:32631",
              layerId: "layer_opt_2023",
            },
            {
              role: "t1",
              sceneId: "scene_opt_2024",
              name: "Comparison 2024",
              capturedAt: new Date().toISOString(),
              modality: "optical",
              sensorPlatform: "Sentinel-2",
              groundSampleDistanceMeters: 10,
              cloudCoverPercentage: 0,
              coordinateReferenceSystem: "EPSG:32631",
              layerId: "layer_opt_2024",
            },
          ],
          timelinePair: {
            baselineSceneId: "scene_opt_2023",
            comparisonSceneId: "scene_opt_2024",
          },
          steps: [
            {
              id: "step-1",
              stageCode: "S1",
              operationId: "investigation.selectScenes",
              state: "completed",
              inputs: [],
              outputs: [],
              parameters: {},
              durationMs: 0, // reused
              rationale: "Selected optical imagery for change detection.",
              model: null,
              dependsOn: [],
              detail: null,
              artefactLayerId: null,
            },
            {
              id: "step-2-rerun",
              stageCode: "S13",
              operationId: "investigation.detectChange",
              state: "completed",
              inputs: [],
              outputs: [],
              parameters: { threshold: 0.45 },
              durationMs: 1100,
              rationale: "Detected changes with relaxed threshold.",
              model: { id: "aeris-change-detect", version: "1.2" },
              dependsOn: ["step-1"],
              detail: null,
              artefactLayerId: null,
            },
          ],
          resultSummary: {
            claimMetrics: [
              { claimId: "claim-1", label: "Area changed", value: 68.7, unit: "ha" },
            ],
            confidence: 0.92,
          },
          layerIds: ["layer-change-v2"],
          traceId: "tr_mock_v2",
        },
      },
    ];
    versionsByInvestigation.set(investigationId, versions);
  }
  return versions;
}

export function saveMockVersion(investigationId: string, version: InvestigationVersion) {
  const versions = getMockVersions(investigationId);
  versions.push(version);
  versionsByInvestigation.set(investigationId, versions);
  return version;
}
