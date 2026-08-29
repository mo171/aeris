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
const SESSION_STORAGE_VERSION = 2;

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
  const area = pickOne(random, MOCK_AREAS);
  const traceId = traceIdFromSeed(seed);

  const areaOfInterest = {
    west: area.longitude - AOI_HALF_SPAN_DEGREES,
    south: area.latitude - AOI_HALF_SPAN_DEGREES,
    east: area.longitude + AOI_HALF_SPAN_DEGREES,
    north: area.latitude + AOI_HALF_SPAN_DEGREES,
  };

  const hasSar = sceneIds.length >= 3;

  // Acquisitions first, because the role slots are DERIVED from them.
  //
  // A slot naming a scene the archive does not contain is exactly the incoherence the timeline exists to
  // prevent: the comparator would show imagery the scrubber cannot find, and binding a role from the
  // acquisition list would fail to match anything. Generating the archive and then choosing from it makes
  // that class of bug unrepresentable rather than merely absent today.
  const acquisitions = buildAcquisitions(investigationId, random, area);

  // The opening pair is the CLEAREST wide pair, not merely the first and last usable ones.
  //
  // That is what a backend creating an investigation would do, and it matters for more than tidiness: an
  // operator who arrives already looking at a degraded comparison has no way to tell whether the warning
  // is about their data or about the tool. Opening clean means the verdict changes when they move a
  // handle, which is the only way the warning teaches them anything.
  const usableOptical = acquisitions.filter(
    (acquisition) => acquisition.modality === "optical" && acquisition.isAvailable,
  );
  const openingPair = choosePair(usableOptical);

  const baselineAcquisition = openingPair?.t0 ?? acquisitions[0];
  const comparisonAcquisition = openingPair?.t1 ?? acquisitions[acquisitions.length - 1];
  const radarAcquisition = [...acquisitions].reverse().find((acquisition) => acquisition.modality === "sar");

  const slotFromAcquisition = (
    acquisition: Acquisition,
    role: "t0" | "t1" | "sar",
  ): InvestigationSceneSlot => ({
    role,
    sceneId: acquisition.sceneId,
    name: `${area.name} · ${acquisition.capturedAt.slice(0, 10)}`,
    capturedAt: acquisition.capturedAt,
    modality: acquisition.modality,
    sensorPlatform: acquisition.sensorPlatform,
    groundSampleDistanceMeters: acquisition.groundSampleDistanceMeters,
    // Null, not zero, for radar: it is unaffected by cloud, and zero would claim a cloud-free radar scene.
    cloudCoverPercentage: acquisition.cloudCoverPercentage,
    coordinateReferenceSystem: "EPSG:32643",
    layerId: `${investigationId}-layer-${role}`,
  });

  const sceneSlots: InvestigationSceneSlot[] = [
    slotFromAcquisition(baselineAcquisition, "t0"),
    slotFromAcquisition(comparisonAcquisition, "t1"),
  ];

  if (hasSar && radarAcquisition) {
    sceneSlots.push(slotFromAcquisition(radarAcquisition, "sar"));
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
    acquisitions,
    cameraBookmark: null,
    seedQuery,
    missionId,
    traceId,
  };

  const sceneLayers = buildSceneLayers(investigationId, areaOfInterest, sceneSlots, acquisitions);
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

/**
 * The acquisition history over the area of interest, oldest first.
 *
 * Clustered revisits separated by two long stretches with nothing usable, because that is what an optical
 * archive over one place actually looks like: regular passes, then a season lost to cloud or to nothing
 * being tasked. A perfectly even series would make the timeline look synthetic and would hide the
 * gap-handling the interface exists to do.
 *
 * Radar is interleaved rather than given its own cadence, so the operator blocked by cloud in the optical
 * lane has somewhere to drop to for roughly the same window — the move the two lanes exist to make
 * obvious.
 */
function buildAcquisitions(
  investigationId: string,
  random: () => number,
  area: (typeof MOCK_AREAS)[number],
): Acquisition[] {
  let capturedMs = ARCHIVE_START;

  return Array.from({ length: ACQUISITION_COUNT }, (_, index) => {
    if (index > 0) {
      const interval = ACQUISITION_INTERVAL_DAYS[(index - 1) % ACQUISITION_INTERVAL_DAYS.length];
      // A few days of jitter on top, so no two archives land on the same calendar dates.
      capturedMs += (interval + Math.floor(randomFloat(random, -6, 6))) * 86_400_000;
    }

    const isSar = index % 4 === 3;
    // Cloud is bimodal, not uniform: most optical passes over a place are usable and a minority are
    // written off entirely. A uniform spread produces an archive with no clear scenes at either end,
    // which is both unrealistic and useless for a demo — every pair would open degraded.
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
      quicklookUrl: buildQuicklookUrl(source.url, area.latitude, area.longitude),
      // Where the scrubber fetches this date's pixels from. Two genuinely different sources across the
      // series so scrubbing reveals a real difference rather than reloading the same picture.
      tiles: {
        urlTemplate: source.url,
        attribution: source.attribution,
        minimumZoom: 3,
        maximumZoom: source.maximumZoom,
      },
      // Heavy cloud makes an acquisition catalogued but not analysable, which the timeline must show
      // rather than silently offering a scene that cannot answer anything.
      isAvailable: cloud === null || cloud < 40,
    };
  });
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
        modelId: slot.modality === "sar" ? "sar-preprocess" : "ingest",
        modelVersion: slot.modality === "sar" ? "0.9.2" : "1.4.0",
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
      // The share of the region that actually changed. Correlated with magnitude but NOT equal to it:
      // magnitude ranks the finding, this is the measurement the answer quotes and the bin scheme reads.
      value: Math.min(1, (radius / 0.0018) * randomFloat(random, 0.55, 0.95)),
      classId: null,
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
        value: null,
        classId: "building",
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
      value: randomFloat(random, 0.55, 0.95),
      // Opaque cloud blocks a claim outright; the thin ones only degrade it. The severity is what the
      // hatch colour carries, so it has to be per feature rather than per layer.
      classId: index % 3 === 0 ? "degrading" : "blocking",
    };
  });

  const residualFeatures: EvidenceFeature[] = Array.from(
    { length: RESIDUAL_POINT_COUNT },
    (_, index) => {
      const residualPixels = randomFloat(random, 0.2, 1.1);

      return {
      id: `${residualLayerId}-f${index}`,
      label: `Tie point ${index + 1} · ${residualPixels.toFixed(2)} px residual`,
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
      value: residualPixels,
      classId: "degrading",
      };
    },
  );


  // ── Catalogue products ─────────────────────────────────────────────────────────────────────────
  // One layer per encoding, so nothing in the overlay catalogue is unexercisable in Phase 1.

  const ndviLayerId = `${investigationId}-layer-ndvi`;
  const landCoverLayerId = `${investigationId}-layer-landcover`;
  const waterLayerId = `${investigationId}-layer-water`;
  const densityLayerId = `${investigationId}-layer-density`;

  // NDVI: a continuous field, laid out as a grid of cells so the ramp reads as a surface rather than as
  // scattered blobs. Values run the full interpretable range — negative over water, high over canopy —
  // because a demo field that never crosses a threshold never proves the thresholds work.
  const ndviFeatures: EvidenceFeature[] = Array.from({ length: NDVI_CELL_COUNT }, (_, index) => {
    const columns = 4;
    const column = index % columns;
    const row = Math.floor(index / columns);
    const cellWidth = (bounds.east - bounds.west) / columns;
    const cellHeight = (bounds.north - bounds.south) / Math.ceil(NDVI_CELL_COUNT / columns);
    const centreLongitude = bounds.west + cellWidth * (column + 0.5);
    const centreLatitude = bounds.south + cellHeight * (row + 0.5);
    // Vegetation thins toward the north-east, which is where the change run says building happened.
    const vigour = 0.72 - (column / columns) * 0.55 - randomFloat(random, 0, 0.35);

    return {
      id: `${ndviLayerId}-f${index}`,
      label: `NDVI cell ${index + 1}`,
      geometry: {
        type: "polygon" as const,
        ring: buildPolygonRing(random, centreLatitude, centreLongitude, cellWidth * 0.42),
      },
      magnitude: Math.min(1, Math.abs(vigour)),
      confidence: null,
      areaHectares: null,
      value: Number(vigour.toFixed(3)),
      classId: null,
    };
  });

  const landCoverFeatures: EvidenceFeature[] = Array.from(
    { length: LAND_COVER_PATCH_COUNT },
    (_, index) => {
      const centreLatitude = randomFloat(random, bounds.south + 0.003, bounds.north - 0.003);
      const centreLongitude = randomFloat(random, bounds.west + 0.003, bounds.east - 0.003);
      const ring = buildPolygonRing(random, centreLatitude, centreLongitude, randomFloat(random, 0.002, 0.005));

      return {
        id: `${landCoverLayerId}-f${index}`,
        label: `Segment ${index + 1}`,
        geometry: { type: "polygon" as const, ring },
        magnitude: randomFloat(random, 0.2, 0.8),
        confidence: randomFloat(random, 0.61, 0.94),
        areaHectares: hectaresForRing(ring),
        // Categorical products have no scalar. Emitting one anyway would invent an ordering across
        // classes that have none — water is not more than cropland.
        value: null,
        classId: pickOne(random, MOCK_LAND_COVER_CLASSES),
      };
    },
  );

  const waterFeatures: EvidenceFeature[] = Array.from({ length: WATER_PATCH_COUNT }, (_, index) => {
    const centreLatitude = randomFloat(random, bounds.south + 0.004, area.latitude);
    const centreLongitude = randomFloat(random, bounds.west + 0.004, bounds.east - 0.004);
    const ring = buildPolygonRing(random, centreLatitude, centreLongitude, randomFloat(random, 0.0015, 0.004));

    return {
      id: `${waterLayerId}-f${index}`,
      label: `Water body ${index + 1}`,
      geometry: { type: "polygon" as const, ring },
      magnitude: randomFloat(random, 0.3, 0.9),
      confidence: randomFloat(random, 0.7, 0.96),
      areaHectares: hectaresForRing(ring),
      value: null,
      classId: MOCK_WATER_STATES[index % MOCK_WATER_STATES.length],
    };
  });

  // Concentric contour bands around the change centroid — the shape a density surface actually takes.
  // Generated inner-first with descending values so the extruded relief peaks at the centre, which is
  // what makes the heat map read as a hill rather than as a stack of discs.
  const densityCentreLatitude = area.latitude + 0.008;
  const densityCentreLongitude = area.longitude + 0.01;
  const densityFeatures: EvidenceFeature[] = Array.from(
    { length: DENSITY_BAND_COUNT },
    (_, index) => {
      const step = (DENSITY_BAND_COUNT - index) / DENSITY_BAND_COUNT;
      const ring = buildPolygonRing(
        random,
        densityCentreLatitude,
        densityCentreLongitude,
        0.0035 + index * 0.0022,
      );

      return {
        id: `${densityLayerId}-f${index}`,
        label: `Density band ${index + 1}`,
        geometry: { type: "polygon" as const, ring },
        magnitude: step,
        confidence: null,
        areaHectares: hectaresForRing(ring),
        value: Number((step * randomFloat(random, 0.75, 1) * 0.95).toFixed(3)),
        classId: null,
      };
    },
  ).reverse();

  const layers: EvidenceLayer[] = [
    {
      id: changeLayerId,
      kind: "polygon-vector",
      renderMode: "draped",
      title: "Change mask · built-up gain",
      overlayId: "change-mask",
      valueDomain: { minimum: 0, maximum: 1 },
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
      renderMode: "classified",
      title: "New structures",
      overlayId: "detected-objects",
      valueDomain: null,
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
      renderMode: "classified",
      title: "Cloud mask (T1)",
      overlayId: "mask-cloud",
      valueDomain: { minimum: 0, maximum: 1 },
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
      renderMode: "classified",
      title: "Co-registration residual",
      overlayId: "mask-co-registration",
      valueDomain: { minimum: 0, maximum: 2 },
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
    {
      id: ndviLayerId,
      kind: "polygon-vector",
      renderMode: "heatmap",
      title: "NDVI · vegetation",
      overlayId: "ndvi",
      // The observed range, narrower than NDVI's theoretical −1..+1. The legend ramps across THIS, so the
      // whole bar is spent on values the scene actually contains.
      valueDomain: { minimum: -0.2, maximum: 0.75 },
      colorRampId: "index-vegetation",
      opacity: 0.78,
      isVisible: false,
      comparatorSide: "both",
      tileUrlTemplate: null,
      attribution: null,
      bounds,
      minimumZoom: null,
      maximumZoom: null,
      features: ndviFeatures,
      provenance: {
        modelId: "index-engine",
        modelVersion: "1.1.0",
        traceStepId: `${investigationId}-step-S12`,
        confidence: null,
      },
    },
    {
      id: landCoverLayerId,
      kind: "polygon-vector",
      renderMode: "classified",
      title: "Land cover",
      overlayId: "land-cover",
      valueDomain: null,
      colorRampId: "artefact-neutral",
      opacity: 0.62,
      isVisible: false,
      comparatorSide: "both",
      tileUrlTemplate: null,
      attribution: null,
      bounds,
      minimumZoom: null,
      maximumZoom: null,
      features: landCoverFeatures,
      provenance: {
        modelId: "segformer-lulc",
        modelVersion: "3.0.1",
        traceStepId: `${investigationId}-step-S13`,
        confidence: 0.84,
      },
    },
    {
      id: waterLayerId,
      kind: "polygon-vector",
      renderMode: "classified",
      title: "Water extent",
      overlayId: "water-extent",
      valueDomain: null,
      colorRampId: "artefact-neutral",
      opacity: 0.65,
      isVisible: false,
      comparatorSide: "both",
      tileUrlTemplate: null,
      attribution: null,
      bounds,
      minimumZoom: null,
      maximumZoom: null,
      features: waterFeatures,
      provenance: {
        modelId: "mndwi-threshold",
        modelVersion: "1.0.4",
        traceStepId: `${investigationId}-step-S13`,
        confidence: 0.79,
      },
    },
    {
      id: densityLayerId,
      // The one heatmap-surface in the set: contour bands the renderer extrudes by VALUE rather than by
      // significance, which is what builds relief over the concentration instead of a flat wash.
      kind: "heatmap-surface",
      renderMode: "heatmap",
      title: "Detection density",
      overlayId: "detection-density",
      valueDomain: { minimum: 0, maximum: 1 },
      colorRampId: "confidence-magma",
      opacity: 0.72,
      isVisible: false,
      comparatorSide: "both",
      tileUrlTemplate: null,
      attribution: null,
      bounds,
      minimumZoom: null,
      maximumZoom: null,
      features: densityFeatures,
      provenance: {
        modelId: "density-kernel",
        modelVersion: "0.4.0",
        traceStepId: `${investigationId}-step-S15`,
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
