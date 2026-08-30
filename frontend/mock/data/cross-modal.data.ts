// mock/data/cross-modal.data.ts — two independent sensor runs, and their disagreement.
//
// PHASE 1 ONLY. This entire /mock folder is deleted in Phase 2.
//
// what  : Generates an optical run and a radar run over the same investigation, classifies every region
//         into an agreement state, and produces the fused verdict — or the refusal to produce one.
// where : Served through mock/transport/routes.ts at REST_API.investigations.crossModal.
// how   : Built by reusing the investigation's OWN change features rather than inventing a second set,
//         because the two surfaces have to be talking about the same ground. The optical run takes the
//         change mask it already produced; the radar run is derived from the same regions with a
//         deliberately different opinion about some of them.
//
//         THE DEMO MUST CONTAIN A REAL CONFLICT. A generated run where everything corroborates proves
//         nothing — it exercises the happy path of a page whose entire reason for existing is the
//         unhappy one. So the generator forces at least one region into each of the four states,
//         including a genuine opposite-direction conflict and one region radar is geometrically blind to.
//
//         Determinism matters here more than usual: the agreement ledger is what a reviewer will read
//         twice, and a page that reshuffles its verdict on refresh cannot be checked.

import { AGREEMENT, SENSOR_PLATFORMS } from "@/lib/constants/cross-modal";
import {
  assessModalityPair,
  buildVerdict,
  classifyAgreement,
  shouldRefuseFusion,
  type SensorOpinion,
} from "@/features/crossModal/lib/agreement";
import type {
  AgreementRow,
  CrossModalResult,
  SensorRun,
} from "@/features/crossModal/types/cross-modal.types";
import type { EvidenceLayer } from "@/features/investigation/types/layer.types";

import { createSeededRandom, randomFloat } from "../transport/deterministic-random";
import { getMockAnalysisProducts, getMockInvestigation } from "./investigation.data";

/** Radar look geometry. Fixed per investigation so layover always falls in the same place. */
const RADAR_LOOK_AZIMUTH_DEGREES = 78;
const RADAR_INCIDENCE_DEGREES = 39;

/**
 * How the generator forces coverage of every agreement state.
 *
 * Indexed against the investigation's change regions in order. Anything past the end of this list is
 * classified naturally from the two runs, so the ledger is not entirely scripted — only its coverage is.
 */
const SCRIPTED_STATES = [
  "corroborated",
  "corroborated",
  "conflict",
  "optical-only",
  "radar-only",
  "corroborated",
  "optical-only",
] as const;

export function getMockCrossModal(investigationId: string): CrossModalResult | null {
  const investigation = getMockInvestigation(investigationId);
  const graph = getMockAnalysisProducts(investigationId);
  if (!investigation || !graph) {
    return null;
  }

  const opticalSlot =
    investigation.sceneSlots.find((slot) => slot.role === "t1") ?? investigation.sceneSlots[0];
  if (!opticalSlot) {
    return null;
  }

  // The NEAREST radar pass to the optical date, not whichever radar scene happens to be attached.
  // A cross-modal comparison is only meaningful against the closest available acquisition — reaching for
  // a radar scene years away would produce a refusal every time and teach nothing about the page.
  const radarAcquisition = nearestRadarAcquisition(investigation, opticalSlot.capturedAt);
  const radarSlot = radarAcquisition
    ? {
        sceneId: radarAcquisition.sceneId,
        capturedAt: radarAcquisition.capturedAt,
      }
    : null;

  const runId = `${investigationId}-xm-1`;
  const random = createSeededRandom(investigationId.length * 31 + 7);
  const changeLayer = graph.layers.find((layer) => layer.overlayId === "change-mask");
  const changeFeatures = changeLayer?.features ?? [];

  // ── The two runs, built independently ────────────────────────────────────────────────────────

  const opticalLayers = graph.layers.filter(
    (layer) => layer.overlayId !== "backscatter" && !isRadarMask(layer),
  );
  const radarLayers = graph.layers.filter(
    (layer) => layer.overlayId === "backscatter" || isRadarMask(layer),
  );

  const opticalRun: SensorRun = {
    sensor: "optical",
    sceneId: opticalSlot.sceneId,
    capturedAt: opticalSlot.capturedAt,
    platform: SENSOR_PLATFORMS.optical.platform,
    polarisation: null,
    lookAzimuthDegrees: null,
    incidenceAngleDegrees: null,
    layers: opticalLayers,
    evidence: graph.evidence.filter((item) => item.kind !== "cross-modal"),
    // Claims are stamped with the run that delivered them. The analysis stream does this as it emits;
    // reading the products directly bypasses that, so the Lab stamps its own run id here.
    claims: graph.claims.map((claim) => ({ ...claim, runId })),
    modelId: "changeformer",
    modelVersion: "1.2.0",
    confidence: 0.91,
    // Cloud cover on the optical date, as a fraction. This is what turns "radar only" from a
    // disagreement into an explanation.
    obscuredFraction: (opticalSlot.cloudCoverPercentage ?? 0) / 100,
  };

  const radarRun: SensorRun | null = radarSlot
    ? {
        sensor: "radar",
        sceneId: radarSlot.sceneId,
        capturedAt: radarSlot.capturedAt,
        platform: SENSOR_PLATFORMS.radar.platform,
        polarisation: "VV",
        lookAzimuthDegrees: RADAR_LOOK_AZIMUTH_DEGREES,
        incidenceAngleDegrees: RADAR_INCIDENCE_DEGREES,
        layers: radarLayers,
        evidence: graph.evidence.filter((item) => item.kind === "cross-modal"),
        claims: [],
        modelId: "sar-change",
        modelVersion: "0.9.2",
        confidence: 0.78,
        // Layover plus shadow. Radar's own blindness, and the reason some optical findings are not
        // disagreements at all.
        obscuredFraction: 0.11,
      }
    : null;

  const advisory = assessModalityPair(
    opticalRun.capturedAt,
    radarRun?.capturedAt ?? opticalRun.capturedAt,
    radarRun ? randomFloat(random, 0.4, 1.1) : null,
  );

  // ── Classify every region ────────────────────────────────────────────────────────────────────

  const rows: AgreementRow[] = changeFeatures.slice(0, SCRIPTED_STATES.length).map((feature, index) => {
    const scripted = SCRIPTED_STATES[index];
    const { optical, radar } = opinionsFor(scripted, feature.confidence, random);
    const { state, reason } = classifyAgreement(optical, radar);

    return {
      id: `${investigationId}-agree-${index}`,
      label: feature.label,
      state,
      reason,
      opticalFeatureIds: optical.hasFinding ? [feature.id] : [],
      radarFeatureIds: radar.hasFinding ? [feature.id] : [],
      opticalConfidence: optical.confidence,
      radarConfidence: radar.confidence,
      areaHectares: feature.areaHectares,
    };
  });

  // Sorted worst-first, so a conflict is never buried under agreement.
  rows.sort((left, right) => AGREEMENT[left.state].priority - AGREEMENT[right.state].priority);

  const refusedBecause = shouldRefuseFusion({
    advisory,
    hasRadar: radarRun !== null,
    questionScope: "both",
    isSeparationRequested: false,
  });

  return {
    investigationId,
    runId,
    optical: opticalRun,
    radar: radarRun,
    advisory,
    verdict: radarRun ? buildVerdict(rows, opticalRun, radarRun, refusedBecause) : null,
    generatedAt: new Date().toISOString(),
  };
}

/**
 * The two sensors' opinions that produce a given state.
 *
 * Written as opinions fed THROUGH the real classifier rather than as pre-labelled rows, so the mock
 * exercises the same logic the backend will — if `classifyAgreement` changes its policy, this data
 * changes with it instead of silently disagreeing.
 */
function opinionsFor(
  target: (typeof SCRIPTED_STATES)[number],
  baseConfidence: number | null,
  random: () => number,
): { optical: SensorOpinion; radar: SensorOpinion } {
  const opticalConfidence = baseConfidence ?? randomFloat(random, 0.6, 0.95);
  const radarConfidence = randomFloat(random, 0.55, 0.88);

  switch (target) {
    case "conflict":
      return {
        optical: {
          hasFinding: true,
          confidence: opticalConfidence,
          isObscured: false,
          direction: "increase",
          featureIds: [],
        },
        radar: {
          hasFinding: true,
          confidence: radarConfidence,
          isObscured: false,
          direction: "decrease",
          featureIds: [],
        },
      };

    case "optical-only":
      // Radar observed it and found nothing — a genuine spectral-without-structural change, not blindness.
      return {
        optical: {
          hasFinding: true,
          confidence: opticalConfidence,
          isObscured: false,
          direction: "increase",
          featureIds: [],
        },
        radar: { hasFinding: false, confidence: null, isObscured: false, direction: null, featureIds: [] },
      };

    case "radar-only":
      // Optical was obscured here, so its silence is explained rather than counted against radar.
      return {
        optical: { hasFinding: false, confidence: null, isObscured: true, direction: null, featureIds: [] },
        radar: {
          hasFinding: true,
          confidence: radarConfidence,
          isObscured: false,
          direction: "increase",
          featureIds: [],
        },
      };

    default:
      return {
        optical: {
          hasFinding: true,
          confidence: opticalConfidence,
          isObscured: false,
          direction: "increase",
          featureIds: [],
        },
        radar: {
          hasFinding: true,
          confidence: radarConfidence,
          isObscured: false,
          direction: "increase",
          featureIds: [],
        },
      };
  }
}

/**
 * The radar acquisition closest in time to the optical one.
 *
 * Sentinel-1 revisits every six to twelve days and Sentinel-2 every five, so the nearest pass is
 * typically within a week — which is what makes a cross-modal pair describe one state of the ground
 * rather than two.
 */
function nearestRadarAcquisition(
  investigation: ReturnType<typeof getMockInvestigation>,
  opticalCapturedAt: string,
) {
  const opticalTime = new Date(opticalCapturedAt).getTime();
  const radarPasses = (investigation?.acquisitions ?? []).filter(
    (acquisition) => acquisition.modality === "sar",
  );

  return radarPasses.reduce<(typeof radarPasses)[number] | null>((closest, candidate) => {
    if (!closest) {
      return candidate;
    }
    const candidateGap = Math.abs(new Date(candidate.capturedAt).getTime() - opticalTime);
    const closestGap = Math.abs(new Date(closest.capturedAt).getTime() - opticalTime);
    return candidateGap < closestGap ? candidate : closest;
  }, null);
}

/** Radar's own quality masks, which belong to the radar column rather than the optical one. */
function isRadarMask(layer: EvidenceLayer): boolean {
  return layer.overlayId === "mask-sar-layover" || layer.overlayId === "mask-sar-shadow";
}
