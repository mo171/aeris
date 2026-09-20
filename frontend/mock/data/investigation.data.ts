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
  Acquisition,
  Investigation,
  InvestigationSceneSlot,
  InvestigationSummary,
} from "@/features/investigation/types/investigation.types";
import type { EvidenceFeature, EvidenceLayer } from "@/features/investigation/types/layer.types";
import type { ReportSection } from "@/features/investigation/types/report.types";
import { ANALYSIS_OPERATIONS } from "@/lib/constants/analysis-operations";
import { LAYER_RENDERING } from "@/lib/constants/layers";

import { createSeededRandom, pickOne, randomFloat } from "../transport/deterministic-random";
import { MOCK_AREAS } from "./geography";
import mumbaiRunData from "./mumbai-run-data.json";

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

/** Acquisitions generated per investigation. Enough history for a timeline to be worth scrubbing. */
const ACQUISITION_COUNT = 17;

/**
 * Days between consecutive acquisitions, walked in order from the archive start.
 *
 * Deliberately uneven. A real optical archive over one place is clustered revisits separated by stretches
 * where nothing was tasked or nothing was usable, and the two long entries here are those stretches — they
 * are what makes the timeline's coverage-hole rendering exercisable at all. An evenly spaced series would
 * look synthetic and, worse, would mean the gap handling never runs in the one place it is meant to prove.
 */
const ACQUISITION_INTERVAL_DAYS = [
  80, 110, 45, 140, 700, 90, 60, 130, 170, 95, 850, 75, 120, 55, 190, 100,
] as const;

/** Where the archive starts. Fixed so the demo narrative always spans the same eight years. */
const ARCHIVE_START = Date.UTC(2018, 1, 6, 5, 24);
/** Zoom level a quicklook tile is taken at. 12 covers roughly a city and reads as a recognisable place. */
const QUICKLOOK_ZOOM = 12;

/** How often the archive carries a radar companion — every Nth optical pass. */
const RADAR_COMPANION_EVERY = 4;

const CHANGE_POLYGON_COUNT = 11;
const DETECTION_BOX_COUNT = 18;
const CLOUD_BLOB_COUNT = 3;
const RESIDUAL_POINT_COUNT = 9;

/**
 * Products generated alongside the primary change run, so every encoding in the overlay catalogue has
 * something on screen to exercise it.
 *
 * A catalogue nothing produces is a catalogue nobody can check. These exist so the continuous ramp, the
 * class palette, the graduated bins, the hatched mask and the extruded heat surface are all reachable in
 * Phase 1 — and so the legend, the inspector readout and the browser can be verified against real
 * geometry rather than asserted to work. They are deleted with the rest of /mock in Phase 2.
 */
const NDVI_CELL_COUNT = 14;
const LAND_COVER_PATCH_COUNT = 12;
const WATER_PATCH_COUNT = 6;
const DENSITY_BAND_COUNT = 5;

/** Land-cover classes the generator draws from, weighted toward what an urban-fringe scene contains. */
const MOCK_LAND_COVER_CLASSES = [
  "built-up",
  "vegetation",
  "cropland",
  "bare-soil",
  "water",
  "wetland",
] as const;

/** Water states, ordered so the generator produces mostly permanent water with real gain and loss. */
const MOCK_WATER_STATES = ["permanent", "permanent", "gained", "lost", "seasonal"] as const;

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

/**
 * Bumped whenever the generated shape changes.
 *
 * Without it, a persisted investigation from an earlier build rehydrates into a session running newer
 * code and fails validation at the stream boundary — layers are silently dropped and the workspace
 * reports "no evidence yet" with nothing anywhere saying why. It costs a session's history to discard
 * the cache; it costs an afternoon to debug a schema change against data that predates it.
 */
const SESSION_STORAGE_VERSION = 9;

const investigationsById = new Map<string, GeneratedInvestigation>(loadPersisted());

function loadPersisted(): [string, GeneratedInvestigation][] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) {
      return [];
    }

    const payload = JSON.parse(raw) as {
      version?: number;
      entries?: [string, GeneratedInvestigation][];
    };

    // Anything from an older shape is dropped rather than trusted. Regenerating is instant; rendering
    // data the current contract rejects is not recoverable from inside the app.
    return payload.version === SESSION_STORAGE_VERSION ? (payload.entries ?? []) : [];
  } catch {
    // A quota error must never stop the app booting.
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
      JSON.stringify({
        version: SESSION_STORAGE_VERSION,
        entries: [...investigationsById.entries()],
      }),
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

/**
 * A single tile covering a point, used as a scene quicklook.
 *
 * Real quicklooks come from the backend in Phase 2. Deriving one from the same tile source the scene
 * renders from means the preview is genuinely a picture of that place rather than a placeholder — which
 * is the whole point of a quicklook: deciding whether a scene is worth opening.
 */
function buildQuicklookUrl(template: string, latitude: number, longitude: number): string {
  const scale = 2 ** QUICKLOOK_ZOOM;
  const latitudeRadians = (latitude * Math.PI) / 180;
  const x = Math.floor(((longitude + 180) / 360) * scale);
  const y = Math.floor(
    ((1 - Math.log(Math.tan(latitudeRadians) + 1 / Math.cos(latitudeRadians)) / Math.PI) / 2) * scale,
  );

  return template
    .replace("{z}", String(QUICKLOOK_ZOOM))
    .replace("{x}", String(x))
    .replace("{y}", String(y));
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
  const area = {
    name: "Mumbai Coastal Belt",
    latitude: 18.975,
    longitude: 72.86,
    country: "India",
  };
  const traceId = traceIdFromSeed(seed);

  const areaOfInterest = {
    west: 72.81855,
    south: 18.91907,
    east: 72.90132,
    north: 19.03092,
  };

  const hasSar = true;

  // Acquisitions first, because the role slots are DERIVED from them.
  const acquisitions = buildAcquisitions(investigationId, random, area);

  const baselineAcquisition =
    acquisitions.find((candidate) => candidate.sceneId === "SCN_01M2ZGSPQA1XFMJD4AJ6MHQRXD") ??
    acquisitions[0];
  const comparisonAcquisition =
    acquisitions.find((candidate) => candidate.sceneId === "SCN_01M289GQ9QMFQY7YGAFMFPSWDP") ??
    acquisitions[1];
  const radarAcquisition =
    acquisitions.find((candidate) => candidate.sceneId === "SCN_01M2FRFKYDX1EKKJCCKE0K6HH5") ??
    [...acquisitions].reverse().find((acquisition) => acquisition.modality === "sar");

  const slotFromAcquisition = (
    acquisition: Acquisition,
    role: "t0" | "t1" | "sar",
  ): InvestigationSceneSlot => ({
    role,
    sceneId: acquisition.sceneId,
    name: `${area.name} · ${acquisition.sensorPlatform} (${role.toUpperCase()})`,
    capturedAt: acquisition.capturedAt,
    modality: acquisition.modality,
    sensorPlatform: acquisition.sensorPlatform,
    groundSampleDistanceMeters: acquisition.groundSampleDistanceMeters,
    cloudCoverPercentage: acquisition.cloudCoverPercentage,
    coordinateReferenceSystem: "EPSG:32643",
    layerId: `${investigationId}-layer-${role}`,
  });

  const sceneSlots: InvestigationSceneSlot[] = [
    slotFromAcquisition(baselineAcquisition, "t0"),
    slotFromAcquisition(comparisonAcquisition, "t1"),
  ];

  if (radarAcquisition) {
    sceneSlots.push(slotFromAcquisition(radarAcquisition, "sar"));
  }

  const investigation: Investigation = {
    id: investigationId,
    projectId: "p-1",
    name: "Identification of Built-up and Water-Covered Regions",
    areaOfInterestName: "Mumbai Coastal Belt & Port Zone, India",
    areaOfInterest,
    centroid: { latitude: 18.975, longitude: 72.86 },
    status: "ready",
    mode: "crossModal",
    createdAt: "2026-03-24T08:12:00.000Z",
    updatedAt: "2026-03-25T12:00:00.000Z",
    sceneSlots,
    acquisitions,
    cameraBookmark: null,
    seedQuery,
    missionId,
    traceId,
  };

  const sceneLayers = buildSceneLayers(investigationId, areaOfInterest, sceneSlots, acquisitions);
  const analysis = buildAnalysisProducts(investigationId, random, area, areaOfInterest, hasSar, sceneSlots);

  return {
    investigation,
    layers: [...sceneLayers, ...analysis.layers],
    evidence: analysis.evidence,
    claims: analysis.claims,
    answer: analysis.answer,
    traceSteps: analysis.traceSteps,
  };
}

/**
 * The acquisition history over the area of interest, oldest first.
 */
function buildAcquisitions(
  investigationId: string,
  random: () => number,
  area: (typeof MOCK_AREAS)[number],
): Acquisition[] {
  const mumbaiAcquisitions: Acquisition[] = [
    {
      id: `${investigationId}-acq-mum-t0`,
      sceneId: "SCN_01M2ZGSPQA1XFMJD4AJ6MHQRXD",
      capturedAt: "2026-03-12T05:36:39.000Z",
      modality: "optical",
      sensorPlatform: "Sentinel-2B",
      groundSampleDistanceMeters: 10,
      cloudCoverPercentage: 0.1,
      quicklookUrl: "/figures/fig_01M289GSEDE1NJ7FAQF7TJ1FNW.webp",
      tiles: {
        urlTemplate: STAND_IN_TILES.recentImagery.url,
        attribution: "Sentinel-2B L2A MSI 10m / AERIS Ingest",
        minimumZoom: 3,
        maximumZoom: 18,
      },
      isAvailable: true,
    },
    {
      id: `${investigationId}-acq-mum-t1`,
      sceneId: "SCN_01M289GQ9QMFQY7YGAFMFPSWDP",
      capturedAt: "2026-03-24T05:36:40.000Z",
      modality: "optical",
      sensorPlatform: "Sentinel-2B",
      groundSampleDistanceMeters: 10,
      cloudCoverPercentage: 0.0,
      quicklookUrl: "/figures/fig_01M2FRFT7TYTAMDMX0MKS607DR.webp",
      tiles: {
        urlTemplate: STAND_IN_TILES.recentImagery.url,
        attribution: "Sentinel-2B L2A MSI 10m / AERIS Ingest",
        minimumZoom: 3,
        maximumZoom: 18,
      },
      isAvailable: true,
    },
    {
      id: `${investigationId}-acq-mum-sar`,
      sceneId: "SCN_01M2FRFKYDX1EKKJCCKE0K6HH5",
      capturedAt: "2026-03-15T01:03:12.000Z",
      modality: "sar",
      sensorPlatform: "Sentinel-1A",
      groundSampleDistanceMeters: 10,
      cloudCoverPercentage: null,
      quicklookUrl: "/figures/fig_01M2FRFVDW77W5S29R8453406K.webp",
      tiles: {
        urlTemplate: STAND_IN_TILES.recentImagery.url,
        attribution: "Sentinel-1A IW GRD RTC 10m / AERIS Ingest",
        minimumZoom: 3,
        maximumZoom: 18,
      },
      isAvailable: true,
    },
    {
      id: `${investigationId}-acq-mum-fusion`,
      sceneId: "SCN_01M2CROSSMODALFUSIONMUMBAI",
      capturedAt: "2026-03-25T12:00:00.000Z",
      modality: "sar",
      sensorPlatform: "Sentinel-1A + Sentinel-2B Fusion",
      groundSampleDistanceMeters: 10,
      cloudCoverPercentage: null,
      quicklookUrl: "/figures/fig_01M2FRG388F110H473H7803P0Q.webp",
      tiles: {
        urlTemplate: STAND_IN_TILES.recentImagery.url,
        attribution: "Cross-Modal Late Fusion Pipeline / AERIS Ingest",
        minimumZoom: 3,
        maximumZoom: 18,
      },
      isAvailable: true,
    },
  ];

  let capturedMs = ARCHIVE_START;
  const acquisitions: Acquisition[] = [...mumbaiAcquisitions];

  const optical = Array.from({ length: ACQUISITION_COUNT }, (_, index) => {
    if (index > 0) {
      const interval = ACQUISITION_INTERVAL_DAYS[(index - 1) % ACQUISITION_INTERVAL_DAYS.length];
      capturedMs += (interval + Math.floor(randomFloat(random, -6, 6))) * 86_400_000;
    }

    const isSar = false;
    const isOvercast = index % 3 === 2;
    const cloud = isSar
      ? null
      : Math.round(isOvercast ? randomFloat(random, 46, 88) : randomFloat(random, 0, 22));
    const source =
      index < ACQUISITION_COUNT / 2 ? STAND_IN_TILES.sentinel2Archive : STAND_IN_TILES.recentImagery;

    return {
      id: `${investigationId}-acq-${index}`,
      sceneId: `${investigationId}-scene-${index}`,
      capturedAt: new Date(capturedMs).toISOString(),
      modality: isSar ? ("sar" as const) : ("optical" as const),
      sensorPlatform: isSar ? "Sentinel-1A" : index % 2 === 0 ? "Sentinel-2A" : "Sentinel-2B",
      groundSampleDistanceMeters: isSar ? 20 : 10,
      cloudCoverPercentage: cloud,
      quicklookUrl: "/figures/fig_01M289GSEDE1NJ7FAQF7TJ1FNW.webp",
      tiles: {
        urlTemplate: source.url,
        attribution: source.attribution,
        minimumZoom: 3,
        maximumZoom: source.maximumZoom,
      },
      isAvailable: cloud === null || cloud < 40,
    };
  });

  acquisitions.push(...optical);

  optical.forEach((acquisition, index) => {
    if (index % RADAR_COMPANION_EVERY !== 0) {
      return;
    }

    const offsetDays = Math.round(randomFloat(random, 2, 9));
    acquisitions.push({
      ...acquisition,
      id: `${acquisition.id}-sar`,
      sceneId: `${acquisition.sceneId}-sar`,
      capturedAt: new Date(new Date(acquisition.capturedAt).getTime() + offsetDays * 86_400_000).toISOString(),
      modality: "sar" as const,
      sensorPlatform: "Sentinel-1A",
      groundSampleDistanceMeters: 20,
      cloudCoverPercentage: null,
      quicklookUrl: "/figures/fig_01M2FRFVDW77W5S29R8453406K.webp",
      isAvailable: true,
    });
  });

  return acquisitions.sort(
    (left, right) => new Date(left.capturedAt).getTime() - new Date(right.capturedAt).getTime(),
  );
}

function buildSceneLayers(
  investigationId: string,
  bounds: { west: number; south: number; east: number; north: number },
  slots: readonly InvestigationSceneSlot[],
  acquisitions: readonly Acquisition[],
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

  // Built from the slots rather than from a fixed pair, so the imagery a role draws is always the imagery
  // of the acquisition that role actually names.
  return slots.map((slot) => {
    const acquisition = acquisitions.find((candidate) => candidate.sceneId === slot.sceneId);
    const tiles = acquisition?.tiles ?? {
      urlTemplate: STAND_IN_TILES.recentImagery.url,
      attribution: STAND_IN_TILES.recentImagery.attribution,
      maximumZoom: STAND_IN_TILES.recentImagery.maximumZoom,
    };

    return {
      ...base,
      id: slot.layerId,
      title: `${slot.role.toUpperCase()} · ${slot.sensorPlatform} ${slot.capturedAt.slice(0, 10)}`,
      // No overlay id: a scene is what the sensor saw, not a product. It has no domain to ramp and
      // nothing to read off a legend.
      overlayId: null,
      valueDomain: null,
      colorRampId: slot.modality === "sar" ? ("sar-grayscale" as const) : ("true-color" as const),
      comparatorSide:
        slot.role === "t0" ? ("left" as const) : slot.role === "t1" ? ("right" as const) : ("both" as const),
      // The radar reference is loaded but off by default: it is the cross-modal comparison's input, not
      // part of the temporal one the workspace opens on.
      isVisible: slot.role !== "sar",
      tileUrlTemplate: tiles.urlTemplate,
      attribution: tiles.attribution,
      maximumZoom: tiles.maximumZoom,
      provenance: {
        modelId: slot.modality === "sar" ? "sar-preprocess" : "s2cloudless",
        modelVersion: slot.modality === "sar" ? "0.9.2" : "1.5.0",
        traceStepId: `${investigationId}-step-${slot.modality === "sar" ? "S8" : "S1"}`,
        confidence: null,
      },
    };
  });
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
  _random: () => number,
  _area: (typeof MOCK_AREAS)[number],
  bounds: { west: number; south: number; east: number; north: number },
  hasSar: boolean,
  sceneSlots: InvestigationSceneSlot[],
): AnalysisProducts {
  const layers: EvidenceLayer[] = (mumbaiRunData.layers as unknown as EvidenceLayer[]).map((layer) => {
    const isOptical = layer.id.includes("FRFS") || layer.id.includes("FRFX");
    const traceStepId = isOptical
      ? `${investigationId}-step-S12`
      : `${investigationId}-step-S15`;
    return {
      ...layer,
      bounds,
      provenance: {
        ...layer.provenance,
        traceStepId,
      },
    };
  });

  const claims: Claim[] = (mumbaiRunData.claims as unknown as Claim[]).map((claim, index) => {
    const isOptical = claim.id.includes("FRFS") || claim.id.includes("FRFX");
    return {
      ...claim,
      runId: `${investigationId}-run-initial`,
      isPrimary: index === 0,
      traceStepId: isOptical ? `${investigationId}-step-S12` : `${investigationId}-step-S15`,
    };
  });

  const evidence: EvidenceItem[] = (mumbaiRunData.evidence as unknown as EvidenceItem[]).map((item) => ({
    ...item,
  }));

  const answer = [
    "Comprehensive bi-temporal and cross-modal earth observation analysis of the Mumbai Coastal Belt and Port Zone (EPSG:32643) reveals distinct physical and spectral signatures across 10,519 hectares observed.",
    "Optical multispectral analysis (Sentinel-2B MSI L2A) isolates 1,933.2 hectares (18.4% of observed ground) of dense urban built-up surface via NDBI (> 0.05), with the largest contiguous urban mass covering 401.1 ha along the Byculla and Mazgaon Dockland corridor.",
    "Optical MNDWI (> 0.15) delineates 4,812.2 hectares (45.8%) of water bodies across Mumbai Harbour, Elephanta passage, and tidal channels.",
    "Simultaneously, Sentinel-1A C-band SAR backscatter analysis identifies 4,750.9 hectares (45.2%) of high-dielectric structural built-up (VV >= -8 dB, VH >= -15 dB) and 1,694.2 hectares (16.1%) of specular radar water (VV <= -17 dB, VH <= -22 dB).",
    "The 2,817.7-hectare variance between optical and radar built-up classifications is scientifically authentic: C-band microwave radar penetrates through optical canopy and captures strong double-bounce reflections from vertical building facades, container cranes, and gantry structures across Mazgaon Docks and Eastern Freeway, which spectral NDBI partially shadows.",
    "Conversely, optical water exceeds radar water by 3,118.0 hectares because the Sewri intertidal mudflats and shallow tidal channels exhibit high surface roughness in C-band radar that scatters microwave energy back to the receiver, raising backscatter above the water threshold while appearing dark in optical MNDWI.",
    "Cross-modal late fusion successfully corroborated urban infrastructure with zero orbital co-registration error (0.00 px RMSE), isolating an intertidal physical conflict region of 5.2 ha requiring targeted multi-temporal monitoring."
  ].join(" ");

  return {
    layers,
    evidence,
    claims,
    answer,
    traceSteps: buildTraceSteps(investigationId, hasSar, sceneSlots),
  };
}

function buildTraceSteps(
  investigationId: string,
  _hasSar: boolean,
  sceneSlots: InvestigationSceneSlot[],
): AnalysisTraceStep[] {
  const step = (
    stageCode: AnalysisTraceStep["stageCode"],
    operationId: string | null,
    rationale: string | null,
    model: { id: string; version: string } | null,
    inputs: AnalysisTraceStep["inputs"],
    outputs: AnalysisTraceStep["outputs"],
    dependsOn: string[],
    parameters: Record<string, any>,
    artefactLayerId: string | null,
  ): AnalysisTraceStep => ({
    id: `${investigationId}-step-${stageCode}`,
    operationId,
    stageCode,
    inputs,
    parameters,
    outputs,
    model,
    rationale,
    dependsOn: dependsOn.map((dep) => `${investigationId}-step-${dep}`),
    detail: null,
    state: "pending",
    durationMs: null,
    artefactLayerId,
  });

  const s1Inputs = sceneSlots.map((slot) => ({ kind: "scene" as const, id: slot.sceneId }));

  const steps: AnalysisTraceStep[] = [
    step("S1", null, "Reference scene slots resolved (Sentinel-2B Optical + Sentinel-1A SAR)", null, s1Inputs, [], [], {}, null),
    step("S3", null, "Sensor metadata validated: MSI L2A 10m bands & C-band SAR GRD RTC 10m", null, [], [], ["S1"], {}, null),
    step("S4", null, "CRS aligned to EPSG:32643 (UTM Zone 43N - Mumbai)", null, [], [], ["S3"], {}, null),
    step("S6", null, "Radiometric calibration & histogram normalization verified (nodata 0.0%)", null, [], [], ["S4"], {}, null),
    step("S7", null, "Cloud mask evaluated: 0.08% obscuration over optical scene", { id: "s2cloudless", version: "1.5.0" }, [], [], ["S6"], {}, null),
    step("S8", null, "Orthorectification & RTC terrain correction verified", { id: "sar-preprocess", version: "1.3.0" }, [], [], ["S7"], {}, null),
    step("S9", null, "Co-registration residual: 0.00 px RMSE across optical-SAR pair", { id: "co-registration", version: "0.7.1" }, [], [], ["S8"], {}, null),
    step("S11", null, "Spatial tiling grid: 512x512 windows over Mumbai Harbour AOI", null, [], [], ["S9"], {}, null),
    step("S12", "index-ndvi", "NDBI (> 0.05, 1,933.2 ha) and MNDWI (> 0.15, 4,812.2 ha) computed", { id: "index-engine", version: "1.4.0" }, [], [{ kind: "layer", id: "lyr_01M2FRFSR88QXBFXSDESV0WD87" }, { kind: "layer", id: "lyr_01M2FRFX1YK5V4X4QV2KF3FDRP" }], ["S11"], {}, "lyr_01M2FRFSR88QXBFXSDESV0WD87"),
    step("S13", "sar-analysis", "Dual-polarization SAR backscatter calibrated (VV / VH dB)", { id: "sar-preprocess", version: "1.3.0" }, [], [], ["S9"], {}, null),
    step("S14", "cross-modal", "Cross-modal late fusion agreement analysis executed: 100 evaluation zones", { id: "optical-sar-fusion", version: "0.9.3" }, [], [], ["S12", "S13"], {}, null),
    step("S15", "object-detection", "SAR thresholding: Built-up (4,750.9 ha) & Water (1,694.2 ha) classified", { id: "sar-preprocess", version: "1.3.0" }, [], [{ kind: "layer", id: "lyr_01M2FRFVG1J2WX696273KGQFPR" }, { kind: "layer", id: "lyr_01M2FRG1V18KRWB4P71RG03XHV" }], ["S13"], {}, "lyr_01M2FRFVG1J2WX696273KGQFPR"),
    step("S16", null, "Spatial conflict resolution: identified 5.2 ha optical-water / radar-builtup anomaly at Sewri mudflats", { id: "rs-vlm", version: "1.4.2" }, [], [], ["S14", "S15"], {}, null),
    step("S18", null, "Cross-sensor evidence synthesis: 0.81 confidence on water extent, 0.73 on structural backscatter", null, [], [], ["S16"], {}, null),
    step("S19", null, "Evidence graph & provenance metadata compiled with SHA-256 asset hashes", null, [], [], ["S18"], {}, null),
    step("S20", null, "Multi-modal analytical synthesis released to Mission Command", null, [], [], ["S19"], {}, null),
  ];

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

/**
 * The generated analysis products, independent of whether a run has streamed yet.
 *
 * `getMockEvidenceGraph` deliberately withholds these until a run delivers them, because in the
 * workspace the arrival of evidence IS the analysis happening. The Cross-Modal Lab has the opposite
 * premise — it opens on two analyses that already completed and reports on their agreement — so it needs
 * the products directly rather than an empty graph that would make both sensors look silent.
 */
export function getMockAnalysisProducts(investigationId: string): {
  layers: EvidenceLayer[];
  evidence: EvidenceItem[];
  claims: Claim[];
} | null {
  const generated = ensure(investigationId);
  if (!generated) {
    return null;
  }

  return {
    layers: generated.layers,
    evidence: generated.evidence,
    claims: generated.claims,
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
  operationId?: string | null,
): MockAnalysisScript | null {
  const generated = ensure(investigationId);
  if (!generated) {
    return null;
  }

  const normalisedQuery = query.toLowerCase();
  const hasSar = generated.investigation.sceneSlots.some((slot) => slot.role === "sar");

  // A named operation is authoritative. Keyword sniffing is the fallback for genuinely free text, and it
  // is exactly the guesswork the operationId exists to remove: "does the radar agree?" and "is this
  // radar-visible?" are the same intent and only one of them contains a word this could match.
  const asksForSar =
    operationId === "sar-analysis" ||
    (operationId == null &&
      (normalisedQuery.includes("sar") || normalisedQuery.includes("radar")));

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

  // A named operation reveals the product it declares it produces, and leaves everything else where it
  // was. Running NDVI and being shown a change mask instead — with NDVI sitting switched off in the
  // stack — would read as the operation having silently failed.
  const requestedOverlayId = operationId
    ? (ANALYSIS_OPERATIONS.find((operation) => operation.id === operationId)?.producesOverlayId ?? null)
    : null;

  return {
    traceSteps: generated.traceSteps,
    layers: generated.layers
      .filter((layer) => layer.kind !== "raster-tiles")
      .map((layer) =>
        requestedOverlayId && layer.overlayId === requestedOverlayId
          ? { ...layer, isVisible: true }
          : layer,
      ),
    evidence: generated.evidence,
    claims: generated.claims,
    answer: generated.answer,
    confidence: 0.91,
    insufficientEvidence: null,
  };
}

/**
 * Binds an acquisition into a comparison role.
 *
 * The layer the role renders through is reused rather than created, because the comparator binds roles to
 * layer ids: swapping which acquisition a role points at must not invalidate the binding, or the split
 * would go blank every time the operator changed a scene.
 */
export function attachMockScene(
  investigationId: string,
  sceneId: string,
  role: "t0" | "t1" | "sar",
): Investigation | null {
  const generated = investigationsById.get(investigationId);
  if (!generated) {
    return null;
  }

  const acquisition = generated.investigation.acquisitions.find(
    (candidate) => candidate.sceneId === sceneId,
  );
  if (!acquisition) {
    return null;
  }

  const existingSlot = generated.investigation.sceneSlots.find((slot) => slot.role === role);
  const layerId = existingSlot?.layerId ?? `${investigationId}-layer-${role}`;

  const nextSlot: InvestigationSceneSlot = {
    role,
    sceneId: acquisition.sceneId,
    name: `${generated.investigation.areaOfInterestName} · ${acquisition.capturedAt.slice(0, 10)}`,
    capturedAt: acquisition.capturedAt,
    modality: acquisition.modality,
    sensorPlatform: acquisition.sensorPlatform,
    groundSampleDistanceMeters: acquisition.groundSampleDistanceMeters,
    cloudCoverPercentage: acquisition.cloudCoverPercentage,
    coordinateReferenceSystem: "EPSG:32643",
    layerId,
  };

  generated.investigation = {
    ...generated.investigation,
    updatedAt: new Date().toISOString(),
    sceneSlots: existingSlot
      ? generated.investigation.sceneSlots.map((slot) => (slot.role === role ? nextSlot : slot))
      : [...generated.investigation.sceneSlots, nextSlot],
  };

  persist();
  return generated.investigation;
}

/** Band descriptors for the inspector, by modality. Real ones come from the raster header in Phase 2. */
const BAND_TEMPLATES = {
  optical: [
    { name: "B2", wavelengthNanometres: 492, description: "Blue — water penetration, haze" },
    { name: "B3", wavelengthNanometres: 559, description: "Green — vegetation vigour" },
    { name: "B4", wavelengthNanometres: 665, description: "Red — chlorophyll absorption" },
    { name: "B8", wavelengthNanometres: 833, description: "NIR — biomass, NDVI numerator" },
    { name: "B11", wavelengthNanometres: 1610, description: "SWIR — moisture, built-up" },
  ],
  sar: [
    { name: "VV", wavelengthNanometres: null, description: "Co-polarised — surface roughness" },
    { name: "VH", wavelengthNanometres: null, description: "Cross-polarised — volume scattering" },
  ],
} as const;

/** Resolves a scene id back to its acquisition and the investigation it belongs to. */
export function getMockSceneInspection(sceneId: string) {
  for (const generated of investigationsById.values()) {
    const acquisition = generated.investigation.acquisitions.find(
      (candidate) => candidate.sceneId === sceneId,
    );
    if (!acquisition) {
      continue;
    }

    return {
      acquisition,
      investigationId: generated.investigation.id,
      areaOfInterestName: generated.investigation.areaOfInterestName,
      areaOfInterest: generated.investigation.areaOfInterest,
      coordinateReferenceSystem: "EPSG:32643",
      bands: [...(acquisition.modality === "sar" ? BAND_TEMPLATES.sar : BAND_TEMPLATES.optical)],
    };
  }

  return null;
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
      operationId: null,
      inputs: [],
      outputs: [],
      parameters: {},
      dependsOn: [],
      rationale: null,
      model: { id: "changeformer", version: "3.0.1" },
      stageCode: "S15",
      isEnabled: true,
    },
    {
      id: `${investigationId}-plan-detect`,
      title: "Detect structures inside those regions",
      description: "Run building detection on the T1 observation, cropped to the change regions.",
      operationId: null,
      inputs: [],
      outputs: [],
      parameters: {},
      dependsOn: [],
      rationale: null,
      model: { id: "dota-detector", version: "2.3.4" },
      stageCode: "S13",
      isEnabled: true,
    },
    {
      id: `${investigationId}-plan-area`,
      title: "Quantify the affected area",
      description: "Compute georeferenced hectares from the intersected geometry.",
      operationId: null,
      inputs: [],
      outputs: [],
      parameters: {},
      dependsOn: [],
      rationale: null,
      model: { id: "geospatial-engine", version: "1.0.0" },
      stageCode: "S15",
      isEnabled: true,
    },
    {
      id: `${investigationId}-plan-explain`,
      title: "Explain the validated result",
      description: "Render the structured findings into language, without adding to them.",
      operationId: null,
      inputs: [],
      outputs: [],
      parameters: {},
      dependsOn: [],
      rationale: null,
      model: { id: "rs-vlm", version: "1.4.2" },
      stageCode: "S16",
      isEnabled: true,
    },
  ];

  if (hasSar) {
    steps.splice(2, 0, {
      id: `${investigationId}-plan-sar`,
      title: "Cross-check against radar",
      description: "Compare backscatter over the same regions to corroborate the optical detection.",
      operationId: null,
      inputs: [],
      outputs: [],
      parameters: {},
      dependsOn: [],
      rationale: null,
      model: { id: "optical-sar-fusion", version: "0.9.3" },
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

  return [
    {
      id: "summary",
      kind: "summary",
      heading: "Executive summary",
      body: "Comprehensive dual-sensor (Sentinel-2B Optical + Sentinel-1A SAR) bi-temporal evaluation over Mumbai Coastal Belt & Port Zone (EPSG:32643, 10,519 ha). Optical spectral index NDBI isolates 1,933.2 hectares (18.4%) of high-reflectance urban structures, with major clusters across Mazgaon Dockland, Byculla, and Eastern Freeway. SAR C-band dual-polarization backscatter thresholding identifies 4,750.9 hectares (45.2%) of high-dielectric structural built-up. Optical MNDWI delineates 4,812.2 ha of water surface, while SAR water maps 1,694.2 ha. Cross-modal late fusion successfully corroborated urban infrastructure with zero orbital co-registration error (0.00 px RMSE), isolating an intertidal physical conflict region of 5.2 ha at Sewri mudflats requiring targeted multi-temporal monitoring.",
      layerIds: [],
    },
    {
      id: "inputs",
      kind: "inputs",
      heading: "Input imagery & platforms",
      body: investigation.sceneSlots
        .map(
          (slot) =>
            `• ${slot.role.toUpperCase()} — ${slot.name} (${slot.sensorPlatform}, ${slot.groundSampleDistanceMeters}m GSD, ${slot.coordinateReferenceSystem}, Captured: ${slot.capturedAt.slice(0, 10)})`,
        )
        .join("\n"),
      layerIds: investigation.sceneSlots.map((slot) => slot.layerId),
    },
    {
      id: "findings",
      kind: "findings",
      heading: "Key analytical findings",
      body: claims.map((claim) => `• ${claim.text}`).join("\n\n"),
      layerIds: [],
    },
    {
      id: "models",
      kind: "models",
      heading: "Models & algorithms",
      body: [
        "• index-engine@1.4.0 — Normalized Difference Built-up Index (NDBI > 0.05) & Modified Normalized Difference Water Index (MNDWI > 0.15)",
        "• sar-preprocess@1.3.0 — Radiometric Terrain Correction (RTC), Refined Lee Speckle Filtering & Dual-Polarization (VV/VH) Thresholding",
        "• optical-sar-fusion@0.9.3 — Multi-Modal Late Fusion & Spatial Agreement Classification Engine",
        "• co-registration@0.7.1 — Sub-pixel phase correlation & tie-point residual verification (0.00 px RMSE)",
      ].join("\n"),
      layerIds: [],
    },
    {
      id: "confidence",
      kind: "confidence",
      heading: "Confidence & validation",
      body: "Aggregate confidence 91%, supported by 0.08% optical cloud obscuration, 0.00 px co-registration RMSE, and corroborating dual-frequency radar geometry across Mazgaon Docks and central Mumbai.",
      layerIds: [],
    },
    {
      id: "limitations",
      kind: "limitations",
      heading: "Environmental & sensor limitations",
      body: "Tidal dynamics at Sewri mudflats create periodic surface roughness that elevates C-band radar backscatter above the specular water threshold (-17 dB). Optical cloud shadow obscuration is 0.085%. Urban street canyon shadow limits optical NDBI sensitivity compared to microwave double-bounce returns.",
      layerIds: [],
    },
    {
      id: "conclusion",
      kind: "conclusion",
      heading: "Conclusion & operational recommendations",
      body: `Cross-sensor late fusion proves that optical and SAR observations provide complementary physical bounds on urban expansion and intertidal water cover in complex coastal megacities. All figures and evidence polygons in this report resolve directly through execution trace ${investigation.traceId}.`,
      layerIds: [],
    },
  ];
}

/**
 * The archive's answer to a temporal query.
 *
 * PHASE 1 ONLY, but held to the contract the backend will have to honour: it filters the generated series
 * to the requested window and modalities, reports the holes it found, and — the part that matters — is
 * allowed to DISAGREE with the operator by naming a better pair than the one currently selected.
 *
 * The recommendation is the whole reason this endpoint exists rather than the frontend simply choosing two
 * scenes. Only the side holding the catalogue can say "the pair you would have picked straddles a cloudy
 * pass, there is a clean one eleven days later" — and it can only say it if it is asked about a WINDOW
 * rather than handed a selection.
 */
export function searchMockCatalogue(query: {
  areaOfInterest: { west: number; south: number; east: number; north: number };
  from: string;
  to: string;
  modalities: string[];
  maximumCloudPercentage: number;
}) {
  // Resolved by geometry, not by investigation id, because that is how the real endpoint works: the
  // archive is asked about ground, and knows nothing about who is asking or why.
  const generated = findInvestigationCovering(query.areaOfInterest);
  if (!generated) {
    return null;
  }

  const fromMs = Date.parse(query.from);
  const toMs = Date.parse(query.to);

  const acquisitions = generated.investigation.acquisitions.filter((acquisition) => {
    const capturedMs = Date.parse(acquisition.capturedAt);
    return (
      capturedMs >= fromMs && capturedMs <= toMs && query.modalities.includes(acquisition.modality)
    );
  });

  const usable = acquisitions.filter(
    (acquisition) =>
      acquisition.isAvailable &&
      (acquisition.cloudCoverPercentage === null ||
        acquisition.cloudCoverPercentage <= query.maximumCloudPercentage),
  );

  return {
    query: { ...query, areaOfInterest: generated.investigation.areaOfInterest },
    acquisitions,
    coverageGaps: buildCoverageGaps(acquisitions, query.maximumCloudPercentage),
    recommendedPair: recommendPair(usable),
    advisory: buildAdvisory(acquisitions, usable),
  };
}

/** Spans between usable acquisitions longer than twice the median cadence. */
function buildCoverageGaps(acquisitions: Acquisition[], maximumCloudPercentage: number) {
  const usable = acquisitions
    .filter(
      (acquisition) =>
        acquisition.isAvailable &&
        (acquisition.cloudCoverPercentage === null ||
          acquisition.cloudCoverPercentage <= maximumCloudPercentage),
    )
    .map((acquisition) => Date.parse(acquisition.capturedAt))
    .sort((left, right) => left - right);

  if (usable.length < 3) {
    return [];
  }

  const intervals = usable.slice(1).map((time, index) => time - usable[index]);
  const median = [...intervals].sort((left, right) => left - right)[
    Math.floor(intervals.length / 2)
  ];

  const gaps: { from: string; to: string; days: number; reason: string }[] = [];
  for (let index = 1; index < usable.length; index += 1) {
    const span = usable[index] - usable[index - 1];
    if (span <= median * 2) {
      continue;
    }

    // Whether anything was flown but discarded is the distinction that matters to an operator: "no pass"
    // is a tasking problem, "every pass too cloudy" is a sensor-choice problem with a radar answer.
    const blockedByCloud = acquisitions.some((acquisition) => {
      const capturedMs = Date.parse(acquisition.capturedAt);
      return (
        capturedMs > usable[index - 1] &&
        capturedMs < usable[index] &&
        acquisition.cloudCoverPercentage !== null &&
        acquisition.cloudCoverPercentage > maximumCloudPercentage
      );
    });

    gaps.push({
      from: new Date(usable[index - 1]).toISOString(),
      to: new Date(usable[index]).toISOString(),
      days: Math.round(span / 86_400_000),
      reason: blockedByCloud
        ? `every pass over this window exceeded ${maximumCloudPercentage}% cloud`
        : "no acquisition over this area in this window",
    });
  }

  return gaps;
}

/** Day-of-year separation, folded so December and January read as one month apart. */
function seasonalOffsetDays(earlierMs: number, laterMs: number): number {
  const dayOfYear = (ms: number) => {
    const date = new Date(ms);
    return Math.floor(
      (Date.UTC(2001, date.getUTCMonth(), date.getUTCDate()) - Date.UTC(2001, 0, 1)) / 86_400_000,
    );
  };

  const difference = Math.abs(dayOfYear(earlierMs) - dayOfYear(laterMs));
  return Math.min(difference, 365 - difference);
}

/**
 * The widest, clearest, season-matched pair available.
 *
 * Season matching is the part that is easy to leave out and expensive to get wrong. Comparing February
 * against April over farmland produces a large, real difference that is the crop cycle rather than
 * anything anyone asked about — so a catalogue that recommends such a pair is recommending an artefact.
 * The same chooser picks the investigation's opening pair, which is what stops the mock from handing the
 * operator a selection its own interface immediately criticises.
 *
 * Season match is preferred, not required: an archive with no season-matched pair still has to answer,
 * so the constraint is relaxed rather than returning nothing.
 */
function choosePair(candidates: readonly Acquisition[]): { t0: Acquisition; t1: Acquisition } | null {
  if (candidates.length < 2) {
    return null;
  }

  const sorted = [...candidates].sort(
    (left, right) => Date.parse(left.capturedAt) - Date.parse(right.capturedAt),
  );
  const totalSpan = Math.max(
    1,
    Date.parse(sorted[sorted.length - 1].capturedAt) - Date.parse(sorted[0].capturedAt),
  );

  let best: { t0: Acquisition; t1: Acquisition; score: number } | null = null;

  for (let earlier = 0; earlier < sorted.length - 1; earlier += 1) {
    for (let later = earlier + 1; later < sorted.length; later += 1) {
      const t0 = sorted[earlier];
      const t1 = sorted[later];
      const earlierMs = Date.parse(t0.capturedAt);
      const laterMs = Date.parse(t1.capturedAt);

      const span = (laterMs - earlierMs) / totalSpan;
      const cloud = ((t0.cloudCoverPercentage ?? 0) + (t1.cloudCoverPercentage ?? 0)) / 200;
      const seasonal = seasonalOffsetDays(earlierMs, laterMs) / 182;

      // Span is what makes a comparison worth running; cloud and season are what make it trustworthy.
      const score = span - cloud - seasonal * 1.5;

      if (!best || score > best.score) {
        best = { t0, t1, score };
      }
    }
  }

  return best ? { t0: best.t0, t1: best.t1 } : null;
}

function recommendPair(usable: Acquisition[]) {
  const pair = choosePair(usable);
  if (!pair) {
    return null;
  }

  const separationDays = Math.round(
    (Date.parse(pair.t1.capturedAt) - Date.parse(pair.t0.capturedAt)) / 86_400_000,
  );
  const combinedCloud = Math.round(
    (pair.t0.cloudCoverPercentage ?? 0) + (pair.t1.cloudCoverPercentage ?? 0),
  );
  const seasonal = seasonalOffsetDays(Date.parse(pair.t0.capturedAt), Date.parse(pair.t1.capturedAt));

  return {
    t0SceneId: pair.t0.sceneId,
    t1SceneId: pair.t1.sceneId,
    separationDays,
    reason: `Widest season-matched span in the window — ${combinedCloud}% combined cloud, ${seasonal} days apart in the season, across ${pair.t0.capturedAt.slice(0, 10)} and ${pair.t1.capturedAt.slice(0, 10)}.`,
  };
}

/** One sentence when the catalogue has something to say about the window it was handed. */
function buildAdvisory(acquisitions: Acquisition[], usable: Acquisition[]): string | null {
  if (acquisitions.length === 0) {
    return "Nothing catalogued over this area in the requested window. Widen the dates or add radar.";
  }

  if (usable.length === 0) {
    return "Every acquisition in this window exceeds the cloud ceiling. Radar is unaffected by cloud and covers the same dates.";
  }

  if (usable.length === 1) {
    return "Only one usable acquisition in this window — change detection needs two. Widen the dates or raise the cloud ceiling.";
  }

  const discarded = acquisitions.length - usable.length;
  return discarded > 0
    ? `${usable.length} usable of ${acquisitions.length} catalogued; ${discarded} held back by cloud or processing state.`
    : null;
}

/** The generated investigation whose extent contains the queried centre. */
function findInvestigationCovering(bounds: {
  west: number;
  south: number;
  east: number;
  north: number;
}): GeneratedInvestigation | null {
  const centreLatitude = (bounds.north + bounds.south) / 2;
  const centreLongitude = (bounds.east + bounds.west) / 2;

  for (const generated of investigationsById.values()) {
    const area = generated.investigation.areaOfInterest;
    if (
      centreLatitude >= area.south &&
      centreLatitude <= area.north &&
      centreLongitude >= area.west &&
      centreLongitude <= area.east
    ) {
      return generated;
    }
  }

  return null;
}

/**
 * Stores the operator's saved camera pose against the investigation.
 *
 * Actually persisted rather than acknowledged and dropped: the feature's whole claim is that a reload
 * reopens the saved framing, and a mock that returned 204 without writing anything would make it look
 * broken exactly where it is supposed to prove itself.
 */
export function saveMockCameraBookmark(investigationId: string, cameraBookmark: unknown): null {
  const generated = investigationsById.get(investigationId);
  if (generated) {
    generated.investigation = {
      ...generated.investigation,
      cameraBookmark: cameraBookmark as Investigation["cameraBookmark"],
      updatedAt: new Date().toISOString(),
    };
    persist();
  }
  return null;
}
