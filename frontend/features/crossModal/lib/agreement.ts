// features/crossModal/lib/agreement.ts — deciding whether two sensors agree, and why they might not.
//
// what  : Pure functions that classify a finding into an agreement state with a physical reason, assess
//         whether a cross-modal pair is comparable at all, and decide when to refuse fusion.
// where : Called by use-cross-modal.ts to turn two independent sensor runs into a verdict. No React, no
//         Cesium, no fetch — so the reasoning is testable and the same rules can move to the backend in
//         Phase 2 without being rewritten.
// how   : Two runs come in already independent. This file never re-runs an analysis; it only compares
//         what each sensor concluded, which is precisely what "late fusion" means and precisely why the
//         design document prefers it — "each modality's evidence stays separable" (§9.1).
//
//         THE REASON IS THE OUTPUT. The state alone is a label an operator still has to interpret:
//         "optical only" could mean the change had no structural component, or it could mean radar was
//         geometrically blind there. Choosing between those requires the masks, so this file reads them
//         and says which one applies. A ledger that reported states without reasons would be a table;
//         reporting the reason is what makes it an instrument.
//
//         MASK EVIDENCE OUTRANKS SILENCE. If a sensor could not see a region, its silence is not a
//         disagreement and must never be counted as one. That single rule removes most false conflicts,
//         and it is why obscuration is carried per sensor on every run.

import {
  AGREEMENT,
  CROSS_MODAL_PAIR,
  FUSION_REFUSALS,
  type AgreementState,
  type FusionRefusalId,
} from "@/lib/constants/cross-modal";

import type {
  AgreementRow,
  FusionVerdict,
  ModalityAdvisory,
  SensorRun,
} from "../types/cross-modal.types";

const MILLISECONDS_PER_DAY = 86_400_000;

/** One sensor's opinion about a region, reduced to what the comparison needs. */
export interface SensorOpinion {
  /** Did this sensor assert a finding here at all. */
  hasFinding: boolean;
  confidence: number | null;
  /** Whether the region falls under this sensor's own obscuration — cloud, layover or shadow. */
  isObscured: boolean;
  /** Direction of the asserted change, where the sensor asserts one. Used to detect true conflict. */
  direction: "increase" | "decrease" | null;
  featureIds: readonly string[];
}

/**
 * The agreement state for one region, and the physical reason behind it.
 *
 * Order of tests matters and encodes the policy:
 *   1. Obscuration first — a sensor that could not see cannot disagree.
 *   2. Opposing directions second — that is the only true conflict.
 *   3. Presence in both third — corroboration.
 *   4. Presence in one — reported with the cause that best fits the masks.
 */
export function classifyAgreement(
  optical: SensorOpinion,
  radar: SensorOpinion,
): { state: AgreementState; reason: string } {
  // ── 1. Obscuration. Silence from a blind sensor is not evidence of absence. ──────────────────
  if (optical.hasFinding && !radar.hasFinding && radar.isObscured) {
    return {
      state: "optical-only",
      reason:
        "Radar could not see this region — it falls in layover or shadow, so its silence is not disagreement.",
    };
  }
  if (radar.hasFinding && !optical.hasFinding && optical.isObscured) {
    return {
      state: "radar-only",
      reason: "The optical acquisition was obscured here, so only radar observed this region.",
    };
  }

  // ── 2. True conflict: both saw it, and they say opposite things. ────────────────────────────
  if (
    optical.hasFinding &&
    radar.hasFinding &&
    optical.direction !== null &&
    radar.direction !== null &&
    optical.direction !== radar.direction
  ) {
    return {
      state: "conflict",
      reason: `Optical reports ${optical.direction} where radar reports ${radar.direction}. Both observed the region, so one of them is wrong.`,
    };
  }

  // ── 3. Corroboration. ───────────────────────────────────────────────────────────────────────
  if (optical.hasFinding && radar.hasFinding) {
    return {
      state: "corroborated",
      reason:
        "Both sensors observed this region and independently reported the same change — spectral and structural evidence together.",
    };
  }

  // ── 4. One sensor only, with neither obscured. A real difference in what they measure. ──────
  if (optical.hasFinding) {
    return {
      state: "optical-only",
      reason:
        "Radar observed this region and found nothing. The change is spectral without a structural component — resurfacing, a crop cycle, or a change of material.",
    };
  }
  if (radar.hasFinding) {
    return {
      state: "radar-only",
      reason:
        "Optical observed this region and found nothing. The change is structural or moisture-related without a spectral signature.",
    };
  }

  // Neither found anything. Not a row — callers filter these out before building the ledger.
  return {
    state: "corroborated",
    reason: "Neither sensor reported a finding here.",
  };
}

/**
 * Whether the two acquisitions are close enough in time and alignment to describe the same ground.
 *
 * Deliberately looser than the temporal comparator. Sentinel-2 passes roughly every five days and
 * Sentinel-1 every six to twelve, so a cross-modal pair is ALWAYS offset — applying the temporal
 * threshold here would reject nearly every real pair and teach the operator to ignore the advisory.
 */
export function assessModalityPair(
  opticalCapturedAt: string,
  radarCapturedAt: string,
  coRegistrationPixels: number | null,
): ModalityAdvisory {
  const offsetDays = Math.round(
    Math.abs(new Date(opticalCapturedAt).getTime() - new Date(radarCapturedAt).getTime()) /
      MILLISECONDS_PER_DAY,
  );

  const notes: string[] = [];
  let verdict: ModalityAdvisory["verdict"] = "fair";

  if (offsetDays > CROSS_MODAL_PAIR.maximumOffsetDays) {
    verdict = "unusable";
    notes.push(
      `${offsetDays} days apart. These are two separate observations, not a cross-modal view of one state of the ground.`,
    );
  } else if (offsetDays > CROSS_MODAL_PAIR.fairOffsetDays) {
    verdict = "offset";
    notes.push(
      `${offsetDays} days apart. Anything that changed between the two passes will read as sensor disagreement.`,
    );
  } else {
    notes.push(`${offsetDays} days apart — within a normal orbital offset for these two platforms.`);
  }

  if (coRegistrationPixels !== null) {
    if (coRegistrationPixels > CROSS_MODAL_PAIR.maximumCoRegistrationPixels) {
      verdict = "unusable";
      notes.push(
        `Alignment residual is ${coRegistrationPixels.toFixed(2)} px. Cross-sensor alignment this poor puts feature edges on the wrong side of a mask.`,
      );
    } else {
      notes.push(`Aligned to ${coRegistrationPixels.toFixed(2)} px — sub-pixel across both sensors.`);
    }
  }

  return { verdict, offsetDays, coRegistrationPixels, notes };
}

/**
 * Whether to produce a fused verdict at all, per §9.2.
 *
 * Returns the refusal id, or null to proceed. Refusing is a first-class answer: both sensors are still
 * reported, they are simply not combined — which is more useful than a fused number the policy itself
 * says should not exist.
 */
export function shouldRefuseFusion(options: {
  advisory: ModalityAdvisory;
  hasRadar: boolean;
  /** Set when the operator's question is answerable by one modality alone. */
  questionScope: "spectral" | "structural" | "both";
  /** The operator explicitly asked to keep the sensors apart. */
  isSeparationRequested: boolean;
}): FusionRefusalId | null {
  if (options.isSeparationRequested) {
    return "auditability";
  }
  if (options.advisory.verdict === "unusable") {
    return "poor-co-registration";
  }
  if (options.questionScope === "spectral") {
    return "purely-spectral";
  }
  if (options.questionScope === "structural" && options.hasRadar) {
    return "purely-structural";
  }
  return null;
}

/**
 * Builds the verdict from classified rows.
 *
 * A CONFLICT BLOCKS THE HEADLINE. When the two sensors assert opposite things, the Lab declines a primary
 * claim and says what would resolve it, rather than picking a side or averaging them into a number that
 * describes neither. Supporting rows are still delivered, each tagged with the sensor behind it — rigour
 * where the reader will quote it, usefulness everywhere else.
 *
 * Fused confidence is the MINIMUM of the two sensors, never the mean. Averaging lets a confident sensor
 * carry an unconfident one, which is exactly the overclaiming that late fusion was chosen to avoid.
 */
export function buildVerdict(
  rows: readonly AgreementRow[],
  optical: SensorRun,
  radar: SensorRun | null,
  refusedBecause: FusionRefusalId | null,
): FusionVerdict {
  if (refusedBecause) {
    return {
      headline: null,
      confidence: null,
      refusedBecause,
      blockedByConflict: null,
      rows: [...rows],
    };
  }

  const conflicts = rows.filter((row) => row.state === "conflict");
  if (conflicts.length > 0) {
    return {
      headline: null,
      confidence: null,
      refusedBecause: null,
      blockedByConflict:
        conflicts.length === 1
          ? `${conflicts[0].label}: ${conflicts[0].reason} A third observation is needed before a headline can be stated.`
          : `${conflicts.length} regions where the sensors assert opposite things. A third observation is needed before a headline can be stated.`,
      rows: [...rows],
    };
  }

  const corroborated = rows.filter((row) => row.state === "corroborated");
  const opticalOnly = rows.filter((row) => row.state === "optical-only");
  const radarOnly = rows.filter((row) => row.state === "radar-only");

  const parts = [
    `${corroborated.length} of ${rows.length} regions are corroborated by both sensors`,
  ];
  if (opticalOnly.length > 0) {
    parts.push(`${opticalOnly.length} seen by optical alone`);
  }
  if (radarOnly.length > 0) {
    parts.push(`${radarOnly.length} by radar alone`);
  }

  return {
    headline: `${parts.join(", ")}.`,
    confidence: minimumConfidence(optical.confidence, radar?.confidence ?? null),
    refusedBecause: null,
    blockedByConflict: null,
    rows: [...rows],
  };
}

/** Copy for a state, kept next to the classifier so a new state cannot be added without one. */
export function agreementLabel(state: AgreementState): string {
  return AGREEMENT[state].label;
}

/** Refusal copy, resolved from the catalogue rather than restated at the call site. */
export function refusalCopy(id: FusionRefusalId) {
  return FUSION_REFUSALS[id];
}

/**
 * The lower of two confidences, treating null as "not asserted" rather than as zero.
 *
 * Minimum rather than mean, because a fused claim is only as good as its weaker leg. Averaging would let
 * a confident optical run carry an unconfident radar one and report the pair as more certain than either
 * sensor ever claimed.
 */
function minimumConfidence(left: number | null, right: number | null): number | null {
  if (left === null) {
    return right;
  }
  if (right === null) {
    return left;
  }
  return Math.min(left, right);
}
