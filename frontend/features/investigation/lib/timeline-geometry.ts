// features/investigation/lib/timeline-geometry.ts — the arithmetic and the judgement behind the temporal scrubber.
//
// what  : Maps acquisition dates to positions on a track and back, groups them into modality lanes, finds
//         holes in the archive, and decides whether a chosen pair of observations is a fair comparison.
// where : Used by use-timeline.ts and by the scrubber components. Pure — no React, no stage, no network.
// how   : Kept out of the components on purpose. Everything here is falsifiable: a gap either is or is not
//         longer than the surrounding cadence, two dates either are or are not in different seasons. That
//         is the part of a timeline worth being sure about, and it is only worth being sure about if it
//         can be read without a renderer in the way.
//
//         The pair verdict is the reason this file exists at all. A scrubber that lets an operator select
//         any two dates and says nothing about the pair is a nicer way to make the same mistakes faster —
//         comparing a cloudy scene to a clear one, or March to September over farmland, produces a large
//         real difference that means nothing. Naming that at selection time is the whole point.

import {
  TIMELINE_COVERAGE,
  TIMELINE_PAIR,
  TIMELINE_PAIR_COPY,
  type TimelinePairQuality,
} from "@/lib/constants/timeline";

import type { Acquisition } from "../types/investigation.types";

const MILLISECONDS_PER_DAY = 86_400_000;

/** The span the track covers, in epoch milliseconds. */
export interface TimelineDomain {
  startMs: number;
  endMs: number;
}

export interface TimelineLane {
  modality: Acquisition["modality"];
  label: string;
  acquisitions: Acquisition[];
}

export interface TimelineGap {
  id: string;
  startMs: number;
  endMs: number;
  days: number;
}

export interface TimelinePairAssessment {
  quality: TimelinePairQuality;
  headline: string;
  /** Specific, actionable observations. Empty when the pair is unremarkable. */
  notes: string[];
  separationDays: number | null;
}

const MODALITY_LABEL: Record<Acquisition["modality"], string> = {
  optical: "Optical",
  sar: "Radar",
  multispectral: "Multispectral",
  hyperspectral: "Hyperspectral",
};

function toMilliseconds(acquisition: Acquisition): number {
  return Date.parse(acquisition.capturedAt);
}

/**
 * The extent of the archive, padded so the first and last acquisitions are not pinned to the edges.
 *
 * A marker sitting exactly on the boundary reads as truncated data — the operator cannot tell whether the
 * archive ends there or the view does.
 */
export function computeDomain(acquisitions: readonly Acquisition[]): TimelineDomain | null {
  if (acquisitions.length === 0) {
    return null;
  }

  const times = acquisitions.map(toMilliseconds).filter(Number.isFinite);
  if (times.length === 0) {
    return null;
  }

  const earliest = Math.min(...times);
  const latest = Math.max(...times);
  // A single acquisition has no span, so it is given one rather than dividing by zero downstream.
  const span = latest - earliest || MILLISECONDS_PER_DAY * 365;
  const padding = span * 0.04;

  return { startMs: earliest - padding, endMs: latest + padding };
}

/** Fraction along the track, 0 at the domain start and 1 at its end. */
export function positionForTime(timeMs: number, domain: TimelineDomain): number {
  const span = domain.endMs - domain.startMs;
  if (span <= 0) {
    return 0;
  }
  return Math.min(1, Math.max(0, (timeMs - domain.startMs) / span));
}

export function timeForPosition(position: number, domain: TimelineDomain): number {
  return domain.startMs + (domain.endMs - domain.startMs) * Math.min(1, Math.max(0, position));
}

/**
 * Acquisitions grouped into one lane per sensing modality, in a stable order.
 *
 * Separate lanes rather than one mixed row because the two answer different questions. An operator
 * blocked by cloud in the optical lane drops to radar for the same window — a move that is only obvious
 * when the two archives are stacked against the same axis.
 */
export function buildLanes(acquisitions: readonly Acquisition[]): TimelineLane[] {
  const order: Acquisition["modality"][] = ["optical", "multispectral", "hyperspectral", "sar"];
  const byModality = new Map<Acquisition["modality"], Acquisition[]>();

  for (const acquisition of acquisitions) {
    const existing = byModality.get(acquisition.modality);
    if (existing) {
      existing.push(acquisition);
    } else {
      byModality.set(acquisition.modality, [acquisition]);
    }
  }

  return order
    .filter((modality) => byModality.has(modality))
    .map((modality) => ({
      modality,
      label: MODALITY_LABEL[modality],
      acquisitions: [...(byModality.get(modality) ?? [])].sort(
        (left, right) => toMilliseconds(left) - toMilliseconds(right),
      ),
    }));
}

/** Whether an acquisition can be used as an analysis input under the operator's cloud ceiling. */
export function isSelectable(acquisition: Acquisition, maximumCloudPercentage: number): boolean {
  if (!acquisition.isAvailable) {
    return false;
  }
  return (
    acquisition.cloudCoverPercentage === null ||
    acquisition.cloudCoverPercentage <= maximumCloudPercentage
  );
}

/**
 * Stretches of the archive with no usable acquisition in them.
 *
 * Adaptive to the cadence around them rather than measured against a fixed number of days: a gap means
 * something different for a five-day revisit than for an annual mosaic, and a fixed threshold would
 * report either everything or nothing depending on which archive was loaded.
 */
export function computeCoverageGaps(
  acquisitions: readonly Acquisition[],
  maximumCloudPercentage: number,
): TimelineGap[] {
  const usable = acquisitions
    .filter((acquisition) => isSelectable(acquisition, maximumCloudPercentage))
    .map(toMilliseconds)
    .filter(Number.isFinite)
    .sort((left, right) => left - right);

  // Two points define one interval, which is its own median — every archive would report either no gaps
  // or one enormous one depending on nothing. Below three usable acquisitions the shortage is the finding,
  // and the catalogue's advisory says so in words rather than this drawing a hole across the whole track.
  if (usable.length < 3) {
    return [];
  }

  const intervals: number[] = [];
  for (let index = 1; index < usable.length; index += 1) {
    intervals.push(usable[index] - usable[index - 1]);
  }

  const sorted = [...intervals].sort((left, right) => left - right);
  const median = sorted[Math.floor(sorted.length / 2)];
  const threshold = Math.max(
    TIMELINE_COVERAGE.minimumGapDays * MILLISECONDS_PER_DAY,
    median * TIMELINE_COVERAGE.gapIntervalFactor,
  );

  const gaps: TimelineGap[] = [];
  for (let index = 1; index < usable.length; index += 1) {
    const startMs = usable[index - 1];
    const endMs = usable[index];
    if (endMs - startMs > threshold) {
      gaps.push({
        id: `gap-${startMs}-${endMs}`,
        startMs,
        endMs,
        days: Math.round((endMs - startMs) / MILLISECONDS_PER_DAY),
      });
    }
  }

  return gaps;
}

/**
 * The acquisition closest to a position on the track.
 *
 * Snapping rather than free positioning, because a date with no observation behind it is not a thing the
 * operator can be shown. A handle that can rest between two passes implies imagery that does not exist.
 */
export function nearestAcquisition(
  acquisitions: readonly Acquisition[],
  position: number,
  domain: TimelineDomain,
  options?: { onlySelectable?: boolean; maximumCloudPercentage?: number },
): Acquisition | null {
  const candidates =
    options?.onlySelectable && options.maximumCloudPercentage !== undefined
      ? acquisitions.filter((acquisition) =>
          isSelectable(acquisition, options.maximumCloudPercentage as number),
        )
      : acquisitions;

  if (candidates.length === 0) {
    return null;
  }

  const targetMs = timeForPosition(position, domain);
  let closest = candidates[0];
  let smallestDistance = Math.abs(toMilliseconds(closest) - targetMs);

  for (const candidate of candidates.slice(1)) {
    const distance = Math.abs(toMilliseconds(candidate) - targetMs);
    if (distance < smallestDistance) {
      closest = candidate;
      smallestDistance = distance;
    }
  }

  return closest;
}

/** The next usable acquisition after this one, wrapping to the start. Drives play-through and arrow keys. */
export function stepAcquisition(
  acquisitions: readonly Acquisition[],
  fromSceneId: string | null,
  direction: 1 | -1,
  maximumCloudPercentage: number,
): Acquisition | null {
  const usable = acquisitions
    .filter((acquisition) => isSelectable(acquisition, maximumCloudPercentage))
    .sort((left, right) => toMilliseconds(left) - toMilliseconds(right));

  if (usable.length === 0) {
    return null;
  }

  const currentIndex = usable.findIndex((acquisition) => acquisition.sceneId === fromSceneId);
  if (currentIndex === -1) {
    return direction === 1 ? usable[0] : usable[usable.length - 1];
  }

  const nextIndex = (currentIndex + direction + usable.length) % usable.length;
  return usable[nextIndex];
}

/** Absolute difference in day-of-year, folded so December and January read as one month apart. */
function seasonalOffsetDays(earlier: Date, later: Date): number {
  const dayOfYear = (date: Date) =>
    Math.floor(
      (Date.UTC(2001, date.getUTCMonth(), date.getUTCDate()) - Date.UTC(2001, 0, 1)) /
        MILLISECONDS_PER_DAY,
    );

  const difference = Math.abs(dayOfYear(earlier) - dayOfYear(later));
  return Math.min(difference, 365 - difference);
}

/**
 * Whether these two observations can be honestly compared, and what to warn about if not.
 *
 * Returned as a verdict plus specific notes rather than a score. "0.62 comparability" tells an operator
 * nothing they can act on; "94 days apart in the season — vegetation difference may be phenological"
 * tells them to move a handle.
 */
export function assessPair(
  t0: Acquisition | null,
  t1: Acquisition | null,
): TimelinePairAssessment {
  if (!t0 || !t1) {
    return {
      quality: "unusable",
      headline: TIMELINE_PAIR_COPY.unusable,
      notes: ["Select a baseline and a comparison observation."],
      separationDays: null,
    };
  }

  const earlierMs = Math.min(toMilliseconds(t0), toMilliseconds(t1));
  const laterMs = Math.max(toMilliseconds(t0), toMilliseconds(t1));
  const separationDays = Math.round((laterMs - earlierMs) / MILLISECONDS_PER_DAY);

  const notes: string[] = [];
  let quality: TimelinePairQuality = "clean";

  const downgradeTo = (next: TimelinePairQuality) => {
    if (next === "unusable" || quality === "clean") {
      quality = next;
    }
  };

  if (!t0.isAvailable || !t1.isAvailable) {
    downgradeTo("unusable");
    notes.push("One of these acquisitions is catalogued but not processed to a usable product.");
  }

  if (separationDays < TIMELINE_PAIR.minimumSeparationDays) {
    downgradeTo("unusable");
    notes.push(
      `Only ${separationDays} day${separationDays === 1 ? "" : "s"} apart — too close to separate change from noise.`,
    );
  }

  const combinedCloud = (t0.cloudCoverPercentage ?? 0) + (t1.cloudCoverPercentage ?? 0);
  if (combinedCloud > TIMELINE_PAIR.degradedCombinedCloudPercentage) {
    downgradeTo("degraded");
    notes.push(
      `${Math.round(combinedCloud)}% combined cloud — masked pixels will be dropped from the comparison.`,
    );
  }

  if (t0.modality !== t1.modality) {
    downgradeTo("degraded");
    notes.push(
      `Cross-modal pair (${MODALITY_LABEL[t0.modality]} against ${MODALITY_LABEL[t1.modality]}) — differences in backscatter are not differences in reflectance.`,
    );
  } else if (t0.modality !== "sar") {
    // Seasonality only distorts reflectance. Radar backscatter has its own seasonal behaviour, but it is
    // not the crop-cycle artefact this warning is about, so it is not claimed here.
    const offset = seasonalOffsetDays(new Date(earlierMs), new Date(laterMs));
    if (offset > TIMELINE_PAIR.seasonalOffsetDays) {
      downgradeTo("degraded");
      notes.push(
        `${offset} days apart in the season — vegetation difference may be phenological rather than real change.`,
      );
    }
  }

  if (t0.groundSampleDistanceMeters !== t1.groundSampleDistanceMeters) {
    notes.push(
      `Resolutions differ (${t0.groundSampleDistanceMeters} m against ${t1.groundSampleDistanceMeters} m) — the comparison runs at the coarser of the two.`,
    );
  }

  return { quality, headline: TIMELINE_PAIR_COPY[quality], notes, separationDays };
}
