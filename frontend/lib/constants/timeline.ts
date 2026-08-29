// lib/constants/timeline.ts — tuning for the temporal scrubber and the archive query behind it.
//
// what  : Layout of the timeline track, playback pacing, the defaults of the catalogue query, and the
//         thresholds that decide when a pair of acquisitions is a fair comparison.
// where : Read by features/investigation/lib/timeline-geometry.ts, the scrubber components and the
//         catalogue search hook.
// how   : The judgement thresholds live here rather than inside the geometry code because they are
//         editorial, not mathematical. "How far apart may two acquisitions be before comparing them stops
//         being like-for-like" is a decision an analyst should be able to argue with and an operator
//         should be able to change — burying it in a comparison would make it unarguable.

/** Sizing of the track. Lanes are thin on purpose: the timeline is a control, not a chart. */
export const TIMELINE_LAYOUT = {
  laneHeightPx: 16,
  laneGapPx: 3,
  axisHeightPx: 14,
  /** Horizontal room left inside the track so a marker at either extreme is not clipped by the border. */
  trackInsetPx: 10,
  markerWidthPx: 7,
  handleWidthPx: 2,
} as const;

/**
 * Playback steps from acquisition to acquisition rather than sliding continuously.
 *
 * Continuous motion would imply the archive is continuous, which it is not — there is nothing to show
 * between two passes. Stepping tells the truth about the sampling and gives every frame time to load.
 */
export const TIMELINE_PLAYBACK = {
  dwellMs: 1_100,
  rates: [0.5, 1, 2] as const,
  defaultRate: 1,
} as const;

export const TIMELINE_QUERY = {
  /** Above this, an optical acquisition is offered but not selectable as an analysis input. */
  defaultMaximumCloudPercentage: 40,
  cloudCeilingStepPercentage: 5,
  /** Modalities requested when the operator has not narrowed the search. */
  defaultModalities: ["optical", "sar"] as const,
} as const;

/**
 * When a stretch of archive counts as a hole.
 *
 * Adaptive rather than absolute, because "a gap" means something different for a five-day revisit than
 * for an annual mosaic. A fixed threshold would report every Sentinel pair as a gap or no gap at all
 * depending on which archive was loaded.
 */
export const TIMELINE_COVERAGE = {
  /** Multiple of the median usable interval above which a span is drawn as a hole. */
  gapIntervalFactor: 2.2,
  /** No span shorter than this is a gap, however dense the surrounding coverage. */
  minimumGapDays: 21,
} as const;

/**
 * The tests a chosen pair has to pass before its answer can be trusted.
 *
 * Seasonal offset is the one operators most often miss. Comparing March against September over farmland
 * produces a large, real, and completely uninteresting difference: the crop cycle. Naming it at selection
 * time is the difference between an analysis and a phenology artefact wearing an analysis's confidence.
 */
export const TIMELINE_PAIR = {
  /** Day-of-year separation above which the two observations are in different seasons. */
  seasonalOffsetDays: 45,
  /** Below this separation the two observations are too close to show anything but noise. */
  minimumSeparationDays: 5,
  /** Combined cloud across the pair above which the comparison is called degraded. */
  degradedCombinedCloudPercentage: 35,
} as const;

/** Copy for the pair verdicts, kept beside the thresholds that produce them. */
export const TIMELINE_PAIR_COPY = {
  clean: "Fair comparison",
  degraded: "Degraded comparison",
  unusable: "Not comparable",
} as const;

export type TimelinePairQuality = keyof typeof TIMELINE_PAIR_COPY;
