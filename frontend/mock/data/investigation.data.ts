// mock/data/investigation.data.ts — generated investigations, evidence graphs and analysis scripts.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : Builds an investigation from a set of scene ids, the layers and evidence it produces, the claims
//         those support, and the scripted analysis run that delivers them.
// where : Used by mock/transport/routes.ts and mock/streams/analysis-stream.ts.
// how   : Everything is derived from a seed taken from the scene ids, so the same selection always yields
//         the same area, the same polygons and the same numbers. Math.random() would reshuffle on every
//         reload and make visual review impossible — you could never tell whether something moved because
//         of your code or because the data did.
//
//         SCENE IMAGERY IS A STAND-IN. Phase 1 has no tile server, so T0 and T1 point at two genuinely
//         different public sources of the same ground: a Sentinel-2 cloudless mosaic and a recent
//         high-resolution imagery service. That is deliberate — the comparator has to reveal a real
//         difference to be worth testing, and two renderings of the same picture would prove nothing.
//         In Phase 2 these URLs come from the backend TileJSON and nothing else changes.
//
//         The run reproduces the target dialogue from the design documents — built-up area up, concentrated
//         in the north-east, confidence 91 per cent — but the hectare figure is MEASURED from the polygons
//         actually generated rather than quoted from the document. A claim whose number does not match its
//         own geometry is precisely the unfalsifiable statistic this product exists to replace, so the mock
//         is held to the same standard as the backend will be, and the self-test asserts the two agree.

import type {
  Claim,
  EvidenceGraph,
  EvidenceItem,
  InsufficientEvidence,
} from "@/features/investigation/types/evidence.types";
import type {
  AnalysisPlan,
  AnalysisTraceStep,
  RegionSuggestion,
} from "@/features/investigation/types/analysis.types";
import type {
  Investigation,
  InvestigationSceneSlot,
  InvestigationSummary,
} from "@/features/investigation/types/investigation.types";
import type { EvidenceFeature, EvidenceLayer } from "@/features/investigation/types/layer.types";
import type { ReportSection } from "@/features/investigation/types/report.types";
import { LAYER_RENDERING } from "@/lib/constants/layers";

import { createSeededRandom, pickOne, randomFloat } from "../transport/deterministic-random";
import { MOCK_AREAS } from "./geography";

/** Public stand-in imagery. Replaced by backend TileJSON in Phase 2. */
const STAND_IN_TILES = {
  sentinel2Archive: {
    url: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2018_3857/default/g/{z}/{y}/{x}.jpg",
    attribution: "Sentinel-2 cloudless 2018 by EOX IT Services GmbH",
    maximumZoom: 14,
  },
  recentImagery: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    maximumZoom: 18,
  },
} as const;

/**
 * Half-width of a generated area of interest, in degrees. Roughly a four-kilometre box.
 *
 * Sized like a real change-detection AOI — an urban expansion corridor, not a whole district. That is
 * what keeps the quoted hectares plausible: a change mask covering hundreds of hectares inside a nine
 * kilometre box would be a land-use survey, not a construction finding.
 */
const AOI_HALF_SPAN_DEGREES = 0.02;

const CHANGE_POLYGON_COUNT = 11;
const DETECTION_BOX_COUNT = 18;
const CLOUD_BLOB_COUNT = 3;
const RESIDUAL_POINT_COUNT = 9;

interface GeneratedInvestigation {
  investigation: Investigation;
  layers: EvidenceLayer[];
  evidence: EvidenceItem[];
  claims: Claim[];
  answer: string;
  traceSteps: AnalysisTraceStep[];
}

/**
 * Generated investigations survive a page reload.
 *
 * The design commits to the URL being the investigation — a link reopens the same workspace. Without
 * persistence that claim is false in Phase 1: the store is in memory, so refreshing an investigation URL
 * would 404 and manual testing would be impossible. Session storage keeps the promise honest until the
 * backend takes over. Everything held here is plain data, so it round-trips through JSON unchanged.
 */
const SESSION_STORAGE_KEY = "aeris.mock.investigations";

const investigationsById = new Map<string, GeneratedInvestigation>(loadPersisted());

function loadPersisted(): [string, GeneratedInvestigation][] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as [string, GeneratedInvestigation][]) : [];
  } catch {
    // A quota error or a shape change from an older build must never stop the app booting.
    return [];
  }
}

function persist(): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.sessionStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify([...investigationsById.entries()]),
    );
  } catch {
    // Storage being full only costs reload survival, which is a convenience rather than a requirement.
  }
}

function seedFromIds(sceneIds: readonly string[]): number {
  let seed = 7;
  for (const sceneId of sceneIds.join("|")) {
    seed = (seed * 31 + sceneId.charCodeAt(0)) >>> 0;
  }
  return seed || 7;
}

function traceIdFromSeed(seed: number): string {
  return seed.toString(16).padStart(6, "0").slice(-6);
}

// ── Geometry helpers ──────────────────────────────────────────────────────────────────────────────

function buildPolygonRing(
  random: () => number,
  centreLatitude: number,
  centreLongitude: number,
  radiusDegrees: number,
): { latitude: number; longitude: number }[] {
  const vertexCount = 6;
  const ring: { latitude: number; longitude: number }[] = [];

  for (let index = 0; index < vertexCount; index += 1) {
    const angle = (index / vertexCount) * Math.PI * 2;
    // Jittered radius per vertex, so the shapes read as segmented regions rather than as hexagons.
    const radius = radiusDegrees * randomFloat(random, 0.55, 1.25);
    ring.push({
      latitude: centreLatitude + Math.sin(angle) * radius,
      longitude: centreLongitude + Math.cos(angle) * radius * 1.35,
    });
  }

  return ring;
}

/**
 * Hectares enclosed by a ring, from the ring itself.
 *
 * Measured with the shoelace formula over a local metric projection rather than estimated from the
 * radius the polygon was generated with. That matters more than it looks: the primary claim quotes this
 * figure, and a number that only approximates the geometry it cites is exactly the kind of unfalsifiable
 * statistic this whole product exists to replace. Computing it from the drawn vertices means the claim
 * and the pixels cannot drift apart, and the self-test asserts they do not.
 */
function hectaresForRing(ring: readonly { latitude: number; longitude: number }[]): number {
  if (ring.length < 3) {
    return 0;
  }

  const originLatitude = ring[0].latitude;
  const metresPerDegreeLatitude = 110_540;
  const metresPerDegreeLongitude = 111_320 * Math.cos((originLatitude * Math.PI) / 180);

  const projected = ring.map((point) => ({
    x: (point.longitude - ring[0].longitude) * metresPerDegreeLongitude,
    y: (point.latitude - originLatitude) * metresPerDegreeLatitude,
  }));

  let doubleArea = 0;
  for (let index = 0; index < projected.length; index += 1) {
    const current = projected[index];
    const next = projected[(index + 1) % projected.length];
    doubleArea += current.x * next.y - next.x * current.y;
  }

  return Math.abs(doubleArea) / 2 / 10_000;
}

// ── Generation ────────────────────────────────────────────────────────────────────────────────────

function generate(
  investigationId: string,
  sceneIds: readonly string[],
  seedQuery: string | null,
  missionId: string | null,
): GeneratedInvestigation {
  const seed = seedFromIds(sceneIds);
  const random = createSeededRandom(seed);
  const area = pickOne(random, MOCK_AREAS);
  const traceId = traceIdFromSeed(seed);

  const areaOfInterest = {
    west: area.longitude - AOI_HALF_SPAN_DEGREES,
    south: area.latitude - AOI_HALF_SPAN_DEGREES,
    east: area.longitude + AOI_HALF_SPAN_DEGREES,
    north: area.latitude + AOI_HALF_SPAN_DEGREES,
  };

  const hasSar = sceneIds.length >= 3;

  const sceneSlots: InvestigationSceneSlot[] = [
    {
      role: "t0",
      sceneId: sceneIds[0] ?? `${investigationId}-t0`,
      name: `${area.name} · 2018-03-14`,
      capturedAt: "2018-03-14T05:22:00.000Z",
      modality: "optical",
      sensorPlatform: "Sentinel-2A",
      groundSampleDistanceMeters: 10,
      cloudCoverPercentage: 4,
      coordinateReferenceSystem: "EPSG:32643",
      layerId: `${investigationId}-layer-t0`,
    },
    {
      role: "t1",
      sceneId: sceneIds[1] ?? `${investigationId}-t1`,
      name: `${area.name} · 2026-07-29`,
      capturedAt: "2026-07-29T05:31:00.000Z",
      modality: "optical",
      sensorPlatform: "Sentinel-2B",
      groundSampleDistanceMeters: 10,
      cloudCoverPercentage: 2,
      coordinateReferenceSystem: "EPSG:32643",
      layerId: `${investigationId}-layer-t1`,
    },
  ];

  if (hasSar) {
    sceneSlots.push({
      role: "sar",
      sceneId: sceneIds[2] ?? `${investigationId}-sar`,
      name: `${area.name} · SAR 2026-07-27`,
      capturedAt: "2026-07-27T17:48:00.000Z",
      modality: "sar",
      sensorPlatform: "Sentinel-1A",
      groundSampleDistanceMeters: 20,
      // Null, not zero: SAR is unaffected by cloud, and zero would claim a cloud-free radar scene.
      cloudCoverPercentage: null,
      coordinateReferenceSystem: "EPSG:32643",
      layerId: `${investigationId}-layer-sar`,
    });
  }

  const investigation: Investigation = {
    id: investigationId,
    name: `Urban expansion — ${area.name}`,
    areaOfInterestName: `${area.name}, ${area.country}`,
    areaOfInterest,
    centroid: { latitude: area.latitude, longitude: area.longitude },
    status: "ready",
    mode: hasSar ? "crossModal" : "temporal",
    createdAt: "2026-08-27T08:12:00.000Z",
    updatedAt: "2026-08-27T08:12:00.000Z",
    sceneSlots,
    cameraBookmark: null,
    seedQuery,
    missionId,
    traceId,
  };

  const sceneLayers = buildSceneLayers(investigationId, areaOfInterest, hasSar);
  const analysis = buildAnalysisProducts(investigationId, random, area, areaOfInterest, hasSar);

  return {
    investigation,
    layers: [...sceneLayers, ...analysis.layers],
    evidence: analysis.evidence,
    claims: analysis.claims,
    answer: analysis.answer,
    traceSteps: analysis.traceSteps,
  };
}

function buildSceneLayers(
  investigationId: string,
  bounds: { west: number; south: number; east: number; north: number },
  hasSar: boolean,
): EvidenceLayer[] {
  const base = {
    kind: "raster-tiles" as const,
    renderMode: "draped" as const,
    opacity: 1,
    isVisible: true,
    bounds,
    minimumZoom: 3,
    features: [],
  };

  const layers: EvidenceLayer[] = [
    {
      ...base,
      id: `${investigationId}-layer-t0`,
      title: "T0 · Sentinel-2 2018",
      colorRampId: "true-color",
      comparatorSide: "left",
      tileUrlTemplate: STAND_IN_TILES.sentinel2Archive.url,
      attribution: STAND_IN_TILES.sentinel2Archive.attribution,
      maximumZoom: STAND_IN_TILES.sentinel2Archive.maximumZoom,
      provenance: {
        modelId: "ingest",
        modelVersion: "1.4.0",
        traceStepId: `${investigationId}-step-S1`,
        confidence: null,
      },
    },
    {
      ...base,
      id: `${investigationId}-layer-t1`,
      title: "T1 · Sentinel-2 2026",
      colorRampId: "true-color",
      comparatorSide: "right",
      tileUrlTemplate: STAND_IN_TILES.recentImagery.url,
      attribution: STAND_IN_TILES.recentImagery.attribution,
      maximumZoom: STAND_IN_TILES.recentImagery.maximumZoom,
      provenance: {
        modelId: "ingest",
        modelVersion: "1.4.0",
        traceStepId: `${investigationId}-step-S1`,
        confidence: null,
      },
    },
  ];

  if (hasSar) {
    layers.push({
      ...base,
      id: `${investigationId}-layer-sar`,
      title: "SAR · Sentinel-1 backscatter",
      colorRampId: "sar-grayscale",
      comparatorSide: "both",
      isVisible: false,
      tileUrlTemplate: STAND_IN_TILES.recentImagery.url,
      attribution: STAND_IN_TILES.recentImagery.attribution,
      maximumZoom: STAND_IN_TILES.recentImagery.maximumZoom,
      provenance: {
        modelId: "sar-preprocess",
        modelVersion: "0.9.2",
        traceStepId: `${investigationId}-step-S8`,
        confidence: null,
      },
    });
  }

  return layers;
}

interface AnalysisProducts {
  layers: EvidenceLayer[];
  evidence: EvidenceItem[];
  claims: Claim[];
  answer: string;
  traceSteps: AnalysisTraceStep[];
}

function buildAnalysisProducts(
  investigationId: string,
  random: () => number,
  area: (typeof MOCK_AREAS)[number],
  bounds: { west: number; south: number; east: number; north: number },
  hasSar: boolean,
): AnalysisProducts {
  const changeLayerId = `${investigationId}-layer-change`;
  const detectionLayerId = `${investigationId}-layer-buildings`;
  const cloudLayerId = `${investigationId}-layer-cloud`;
  const residualLayerId = `${investigationId}-layer-residual`;

  // Change is concentrated in the north-east quadrant, which is what the primary claim asserts. The
  // geometry and the sentence have to agree, or the evidence contradicts the answer.
  const changeFeatures: EvidenceFeature[] = [];
  let totalHectares = 0;

  for (let index = 0; index < CHANGE_POLYGON_COUNT; index += 1) {
    const centreLatitude = randomFloat(random, area.latitude + 0.001, bounds.north - 0.003);
    const centreLongitude = randomFloat(random, area.longitude + 0.001, bounds.east - 0.003);
    const radius = randomFloat(random, 0.0005, 0.0018);
    const ring = buildPolygonRing(random, centreLatitude, centreLongitude, radius);
    const areaHectares = hectaresForRing(ring);
    totalHectares += areaHectares;

    changeFeatures.push({
      id: `${changeLayerId}-f${index}`,
      label: `Change region ${index + 1}`,
      geometry: { type: "polygon", ring },
      magnitude: Math.min(1, radius / 0.0018),
      confidence: randomFloat(random, 0.72, 0.97),
      areaHectares,
    });
  }

  const detectionFeatures: EvidenceFeature[] = Array.from(
    { length: DETECTION_BOX_COUNT },
    (_, index) => {
      const centreLatitude = randomFloat(random, area.latitude, bounds.north - 0.002);
      const centreLongitude = randomFloat(random, area.longitude, bounds.east - 0.002);
      const halfSpan = randomFloat(random, 0.00018, 0.00055);

      return {
        id: `${detectionLayerId}-f${index}`,
        label: `Structure ${index + 1}`,
        geometry: {
          type: "bbox" as const,
          bounds: {
            west: centreLongitude - halfSpan * 1.4,
            south: centreLatitude - halfSpan,
            east: centreLongitude + halfSpan * 1.4,
            north: centreLatitude + halfSpan,
          },
        },
        magnitude: randomFloat(random, 0.3, 0.9),
        confidence: randomFloat(random, 0.68, 0.95),
        areaHectares: null,
      };
    },
  );

  const cloudFeatures: EvidenceFeature[] = Array.from({ length: CLOUD_BLOB_COUNT }, (_, index) => {
    const centreLatitude = randomFloat(random, bounds.south + 0.004, bounds.north - 0.004);
    const centreLongitude = randomFloat(random, bounds.west + 0.004, bounds.east - 0.004);
    const ring = buildPolygonRing(
      random,
      centreLatitude,
      centreLongitude,
      randomFloat(random, 0.002, 0.005),
    );

    return {
      id: `${cloudLayerId}-f${index}`,
      label: `Cloud ${index + 1}`,
      geometry: { type: "polygon" as const, ring },
      magnitude: 0.3,
      confidence: null,
      areaHectares: hectaresForRing(ring),
    };
  });

  const residualFeatures: EvidenceFeature[] = Array.from(
    { length: RESIDUAL_POINT_COUNT },
    (_, index) => ({
      id: `${residualLayerId}-f${index}`,
      label: `Tie point ${index + 1} · ${randomFloat(random, 0.2, 1.1).toFixed(2)} px residual`,
      geometry: {
        type: "point" as const,
        position: {
          latitude: randomFloat(random, bounds.south + 0.006, bounds.north - 0.006),
          longitude: randomFloat(random, bounds.west + 0.006, bounds.east - 0.006),
        },
      },
      magnitude: randomFloat(random, 0.1, 0.5),
      confidence: null,
      areaHectares: null,
    }),
  );

  const layers: EvidenceLayer[] = [
    {
      id: changeLayerId,
      kind: "polygon-vector",
      renderMode: "draped",
      title: "Change mask · built-up gain",
      colorRampId: "change-diverging",
      opacity: LAYER_RENDERING.defaultOpacity["polygon-vector"],
      isVisible: true,
      comparatorSide: "both",
      tileUrlTemplate: null,
      attribution: null,
      bounds,
      minimumZoom: null,
      maximumZoom: null,
      features: changeFeatures,
      provenance: {
        modelId: "changeformer",
        modelVersion: "1.2.0",
        traceStepId: `${investigationId}-step-S13`,
        confidence: 0.91,
      },
    },
    {
      id: detectionLayerId,
      kind: "bbox-vector",
      renderMode: "draped",
      title: "New structures",
      colorRampId: "detection-teal",
      opacity: LAYER_RENDERING.defaultOpacity["bbox-vector"],
      isVisible: true,
      comparatorSide: "both",
      tileUrlTemplate: null,
      attribution: null,
      bounds,
      minimumZoom: null,
      maximumZoom: null,
      features: detectionFeatures,
      provenance: {
        modelId: "dota-detector",
        modelVersion: "2.1.3",
        traceStepId: `${investigationId}-step-S15`,
        confidence: 0.87,
      },
    },
    {
      id: cloudLayerId,
      kind: "polygon-vector",
      renderMode: "draped",
      title: "Cloud mask (T1)",
      colorRampId: "artefact-neutral",
      opacity: 0.45,
      // Artefacts stay hidden until the operator opens the trace step that produced them.
      isVisible: false,
      comparatorSide: "both",
      tileUrlTemplate: null,
      attribution: null,
      bounds,
      minimumZoom: null,
      maximumZoom: null,
      features: cloudFeatures,
      provenance: {
        modelId: "s2cloudless",
        modelVersion: "1.5.0",
        traceStepId: `${investigationId}-step-S7`,
        confidence: null,
      },
    },
    {
      id: residualLayerId,
      kind: "point-vector",
      renderMode: "draped",
      title: "Co-registration residual",
      colorRampId: "artefact-neutral",
      opacity: 0.9,
      isVisible: false,
      comparatorSide: "both",
      tileUrlTemplate: null,
      attribution: null,
      bounds,
      minimumZoom: null,
      maximumZoom: null,
      features: residualFeatures,
      provenance: {
        modelId: "registration",
        modelVersion: "0.7.1",
        traceStepId: `${investigationId}-step-S9`,
        confidence: null,
      },
    },
  ];

  const evidence: EvidenceItem[] = [
    {
      id: `${investigationId}-ev-change`,
      kind: "change-mask",
      title: "Change mask",
      layerId: changeLayerId,
      featureIds: changeFeatures.map((feature) => feature.id),
      areaHectares: totalHectares,
      magnitude: 0.92,
      confidence: 0.91,
      sourceSceneIds: [],
    },
    {
      id: `${investigationId}-ev-detections`,
      kind: "detection",
      title: "New structures",
      layerId: detectionLayerId,
      featureIds: detectionFeatures.map((feature) => feature.id),
      areaHectares: null,
      magnitude: 0.74,
      confidence: 0.87,
      sourceSceneIds: [],
    },
    {
      id: `${investigationId}-ev-stats`,
      kind: "statistic",
      title: "Area statistics",
      layerId: null,
      featureIds: [],
      areaHectares: totalHectares,
      magnitude: 0.5,
      confidence: 0.91,
      sourceSceneIds: [],
    },
  ];

  if (hasSar) {
    evidence.push({
      id: `${investigationId}-ev-sar`,
      kind: "cross-modal",
      title: "SAR corroboration",
      layerId: `${investigationId}-layer-sar`,
      featureIds: [],
      areaHectares: null,
      magnitude: 0.61,
      confidence: 0.84,
      sourceSceneIds: [],
    });
  }

  const percentageIncrease = 18.4;

  const claims: Claim[] = [
    {
      id: `${investigationId}-claim-primary`,
      runId: "",
      text: "Built-up area increased across the area of interest.",
      kind: "quantitative",
      confidence: 0.91,
      metrics: [
        {
          label: "Built-up change",
          value: percentageIncrease,
          unit: "%",
          direction: "increase",
          precision: 1,
        },
        {
          label: "Affected area",
          value: totalHectares,
          unit: "ha",
          direction: "increase",
          precision: 1,
        },
        {
          label: "Structures detected",
          value: DETECTION_BOX_COUNT,
          unit: "new",
          direction: "increase",
          precision: 0,
        },
      ],
      evidenceIds: [
        `${investigationId}-ev-change`,
        `${investigationId}-ev-detections`,
        `${investigationId}-ev-stats`,
      ],
      modelId: "changeformer",
      modelVersion: "1.2.0",
      traceStepId: `${investigationId}-step-S13`,
      isPrimary: true,
    },
    {
      id: `${investigationId}-claim-spatial`,
      runId: "",
      text: "The change is concentrated in the north-eastern quadrant rather than distributed evenly.",
      kind: "spatial",
      confidence: 0.88,
      metrics: [],
      evidenceIds: [`${investigationId}-ev-change`],
      modelId: "changeformer",
      modelVersion: "1.2.0",
      traceStepId: `${investigationId}-step-S15`,
      isPrimary: false,
    },
  ];

  if (hasSar) {
    claims.push({
      id: `${investigationId}-claim-crossmodal`,
      runId: "",
      text: "Radar backscatter over the same regions is consistent with new built structures, so both sensors support the finding.",
      kind: "categorical",
      confidence: 0.84,
      metrics: [],
      evidenceIds: [`${investigationId}-ev-sar`, `${investigationId}-ev-change`],
      modelId: "optical-sar-fusion",
      modelVersion: "0.6.0",
      traceStepId: `${investigationId}-step-S13`,
      isPrimary: false,
    });
  }

  const answer = [
    `Built-up area increased by approximately ${percentageIncrease}%.`,
    `${totalHectares.toFixed(1)} hectares of new built-up regions were detected, primarily in the north-eastern portion of the scene, together with ${DETECTION_BOX_COUNT} individual structures not present in the 2018 observation.`,
    hasSar
      ? "Radar backscatter over the same regions is consistent with new construction, so the detection is supported by both sensors."
      : "Only optical observations were available, so the detection rests on a single sensor.",
  ].join(" ");

  return {
    layers,
    evidence,
    claims,
    answer,
    traceSteps: buildTraceSteps(investigationId, hasSar, {
      cloudLayerId,
      residualLayerId,
      changeLayerId,
      detectionLayerId,
    }),
  };
}

function buildTraceSteps(
  investigationId: string,
  hasSar: boolean,
  artefactLayerIds: {
    cloudLayerId: string;
    residualLayerId: string;
    changeLayerId: string;
    detectionLayerId: string;
  },
): AnalysisTraceStep[] {
  const step = (
    stageCode: AnalysisTraceStep["stageCode"],
    detail: string | null,
    modelId: string | null,
    modelVersion: string | null,
    artefactLayerId: string | null,
  ): AnalysisTraceStep => ({
    id: `${investigationId}-step-${stageCode}`,
    stageCode,
    detail,
    state: "pending",
    durationMs: null,
    modelId,
    modelVersion,
    artefactLayerId,
  });

  const steps: AnalysisTraceStep[] = [
    step("S1", "2 scenes referenced", null, null, null),
    step("S3", "Sentinel-2 L2A, 2018-03-14 and 2026-07-29", null, null, null),
    step("S4", "EPSG:32643 confirmed on both", null, null, null),
    step("S6", "Nodata 0.4%, histograms nominal", null, null, null),
    step("S7", "6.1% cloud masked on T1", "s2cloudless", "1.5.0", artefactLayerIds.cloudLayerId),
    step("S8", "Reprojected to analysis grid", null, null, null),
    step("S9", "Residual 0.61 px RMSE", "registration", "0.7.1", artefactLayerIds.residualLayerId),
    step("S11", "512 px windows, 10% overlap", null, null, null),
    step("S12", "NDBI and NDVI computed", "index-engine", "1.1.0", null),
    step(
      "S13",
      "Bi-temporal change detection",
      "changeformer",
      "1.2.0",
      artefactLayerIds.changeLayerId,
    ),
    step(
      "S15",
      "Change bound to 14 georeferenced regions",
      "dota-detector",
      "2.1.3",
      artefactLayerIds.detectionLayerId,
    ),
    step("S16", "Answer rendered from validated results", "rs-vlm", "0.4.2", null),
    step("S18", "Aggregate confidence 0.91", null, null, null),
    step("S19", "Trace appended", null, null, null),
    step("S20", "Response released", null, null, null),
  ];

  if (hasSar) {
    steps.splice(
      10,
      0,
      step("S14", "Cross-modal reading over both sensors", "optical-sar-fusion", "0.6.0", null),
    );
  }

  return steps;
}

// ── Public surface used by the mock routes and streams ────────────────────────────────────────────

function ensure(investigationId: string): GeneratedInvestigation | null {
  return investigationsById.get(investigationId) ?? null;
}

export function createMockInvestigation(
  sceneIds: readonly string[],
  seedQuery: string | null,
  missionId: string | null,
): Investigation {
  const investigationId = `inv_${seedFromIds(sceneIds).toString(36)}`;
  const existing = investigationsById.get(investigationId);
  if (existing) {
    return existing.investigation;
  }

  const generated = generate(investigationId, sceneIds, seedQuery, missionId);
  investigationsById.set(investigationId, generated);
  persist();
  return generated.investigation;
}

export function getMockInvestigation(investigationId: string): Investigation | null {
  return ensure(investigationId)?.investigation ?? null;
}

export function listMockInvestigations(): InvestigationSummary[] {
  return [...investigationsById.values()].map(({ investigation }) => ({
    id: investigation.id,
    name: investigation.name,
    areaOfInterestName: investigation.areaOfInterestName,
    status: investigation.status,
    mode: investigation.mode,
    updatedAt: investigation.updatedAt,
    traceId: investigation.traceId,
  }));
}

/**
 * The graph as it exists before any analysis has run: the scenes, and nothing else.
 * Analysis products arrive through the run stream, which is the point — the operator watches them land.
 */
export function getMockEvidenceGraph(investigationId: string): EvidenceGraph | null {
  const generated = ensure(investigationId);
  if (!generated) {
    return null;
  }

  return {
    claims: [],
    evidence: [],
    layers: generated.layers.filter((layer) => layer.kind === "raster-tiles"),
    generatedAt: new Date().toISOString(),
  };
}

export interface MockAnalysisScript {
  traceSteps: AnalysisTraceStep[];
  layers: EvidenceLayer[];
  evidence: EvidenceItem[];
  claims: Claim[];
  answer: string;
  confidence: number | null;
  insufficientEvidence: InsufficientEvidence | null;
}

/**
 * Picks what a question should produce.
 *
 * A query mentioning a sensor the investigation does not carry returns the refusal path rather than an
 * invented answer — the low-confidence UX has to be exercised in Phase 1, not discovered in Phase 2.
 */
export function selectMockAnalysisScript(
  investigationId: string,
  query: string,
): MockAnalysisScript | null {
  const generated = ensure(investigationId);
  if (!generated) {
    return null;
  }

  const normalisedQuery = query.toLowerCase();
  const hasSar = generated.investigation.sceneSlots.some((slot) => slot.role === "sar");
  const asksForSar = normalisedQuery.includes("sar") || normalisedQuery.includes("radar");

  if (asksForSar && !hasSar) {
    return {
      traceSteps: generated.traceSteps.slice(0, 4),
      layers: [],
      evidence: [],
      claims: [],
      answer: "",
      confidence: null,
      insufficientEvidence: {
        reason:
          "This investigation carries only optical observations, so a radar cross-check cannot be performed on the available imagery.",
        remedies: [
          {
            id: "attach-sar",
            label: "Attach a SAR scene",
            prompt: "Attach the nearest Sentinel-1 acquisition and compare both sensors.",
          },
          {
            id: "optical-only",
            label: "Answer from optical alone",
            prompt: "What changed between these two optical observations?",
          },
        ],
      },
    };
  }

  return {
    traceSteps: generated.traceSteps,
    layers: generated.layers.filter((layer) => layer.kind !== "raster-tiles"),
    evidence: generated.evidence,
    claims: generated.claims,
    answer: generated.answer,
    confidence: 0.91,
    insufficientEvidence: null,
  };
}

export function getMockRegionSuggestions(investigationId: string): RegionSuggestion[] {
  const generated = ensure(investigationId);
  const hasSar = generated?.investigation.sceneSlots.some((slot) => slot.role === "sar") ?? false;

  const suggestions: RegionSuggestion[] = [
    {
      id: "region-what-changed",
      label: "What changed here?",
      prompt: "What changed inside this region between the two observations?",
    },
    {
      id: "region-construction",
      label: "Is this construction?",
      prompt: "Are the changes inside this region consistent with new construction?",
    },
    {
      id: "region-vegetation",
      label: "How much vegetation was lost?",
      prompt: "How much vegetation was lost inside this region?",
    },
  ];

  if (hasSar) {
    suggestions.push({
      id: "region-sar",
      label: "Does SAR agree?",
      prompt: "Does the radar observation support the optical finding inside this region?",
    });
  }

  return suggestions;
}

export function getMockPlan(investigationId: string): AnalysisPlan | null {
  const generated = ensure(investigationId);
  if (!generated) {
    return null;
  }

  const hasSar = generated.investigation.sceneSlots.some((slot) => slot.role === "sar");

  const steps: AnalysisPlan["steps"] = [
    {
      id: `${investigationId}-plan-localise`,
      title: "Localise the strongest change regions",
      description: "Rank the change mask by magnitude and isolate the top regions.",
      modelId: "changeformer",
      stageCode: "S15",
      isEnabled: true,
    },
    {
      id: `${investigationId}-plan-detect`,
      title: "Detect structures inside those regions",
      description: "Run building detection on the T1 observation, cropped to the change regions.",
      modelId: "dota-detector",
      stageCode: "S13",
      isEnabled: true,
    },
    {
      id: `${investigationId}-plan-area`,
      title: "Quantify the affected area",
      description: "Compute georeferenced hectares from the intersected geometry.",
      modelId: "geospatial-engine",
      stageCode: "S15",
      isEnabled: true,
    },
    {
      id: `${investigationId}-plan-explain`,
      title: "Explain the validated result",
      description: "Render the structured findings into language, without adding to them.",
      modelId: "rs-vlm",
      stageCode: "S16",
      isEnabled: true,
    },
  ];

  if (hasSar) {
    steps.splice(2, 0, {
      id: `${investigationId}-plan-sar`,
      title: "Cross-check against radar",
      description: "Compare backscatter over the same regions to corroborate the optical detection.",
      modelId: "optical-sar-fusion",
      stageCode: "S14",
      isEnabled: true,
    });
  }

  return {
    id: `${investigationId}-plan`,
    summary:
      "Localise the strongest change, detect what is inside it, quantify the area, and explain the validated result.",
    steps,
  };
}

export function getMockReportSections(investigationId: string): ReportSection[] {
  const generated = ensure(investigationId);
  if (!generated) {
    return [];
  }

  const { investigation, claims } = generated;
  const primary = claims.find((claim) => claim.isPrimary);
  const areaMetric = primary?.metrics.find((metric) => metric.unit === "ha");

  return [
    {
      id: "summary",
      kind: "summary",
      heading: "Executive summary",
      body: `Built-up area within ${investigation.areaOfInterestName} increased between the 2018 and 2026 observations. ${
        areaMetric ? `${areaMetric.value.toFixed(1)} hectares` : "The affected area"
      } of new built-up land was detected, concentrated in the north-eastern quadrant of the area of interest.`,
      layerIds: [],
    },
    {
      id: "inputs",
      kind: "inputs",
      heading: "Input imagery",
      body: investigation.sceneSlots
        .map(
          (slot) =>
            `${slot.role.toUpperCase()} — ${slot.name} (${slot.sensorPlatform}, ${slot.groundSampleDistanceMeters} m, ${slot.coordinateReferenceSystem})`,
        )
        .join("\n"),
      layerIds: investigation.sceneSlots.map((slot) => slot.layerId),
    },
    {
      id: "findings",
      kind: "findings",
      heading: "Findings",
      body: claims.map((claim) => `• ${claim.text}`).join("\n"),
      layerIds: [],
    },
    {
      id: "models",
      kind: "models",
      heading: "Models used",
      body: [...new Set(claims.map((claim) => `${claim.modelId}@${claim.modelVersion}`))].join("\n"),
      layerIds: [],
    },
    {
      id: "confidence",
      kind: "confidence",
      heading: "Confidence",
      body: "Aggregate confidence 91%, combining per-model scores with the co-registration residual and cloud-coverage checks recorded in the execution trace.",
      layerIds: [],
    },
    {
      id: "limitations",
      kind: "limitations",
      heading: "Limitations",
      body: "Cloud cover on the later observation masked 6.1% of the area of interest; change within masked regions is not asserted. Ground sample distance limits detection of structures below roughly 20 m across.",
      layerIds: [],
    },
    {
      id: "conclusion",
      kind: "conclusion",
      heading: "Conclusion",
      body: `The observed expansion is consistent, localised and supported by georeferenced evidence. Every figure in this report resolves through trace ${investigation.traceId}.`,
      layerIds: [],
    },
  ];
}
