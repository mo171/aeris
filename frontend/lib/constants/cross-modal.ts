// lib/constants/cross-modal.ts — the vocabulary of comparing two sensors that see different physics.
//
// what  : Agreement states and their physical explanations, the conditions under which the system refuses
//         to fuse, radar polarisations, sensor platform facts, and the per-modality phrasing that stops
//         radar being described in optical words.
// where : Read by features/crossModal — the agreement ledger, the sensor cards, the fusion verdict and
//         the stage controls. The overlay catalogue already owns how each sensor's PRODUCTS are drawn;
//         this file owns how their DISAGREEMENT is reasoned about.
// how   : The design document settled the fusion strategy and gave a reason that is as much a user
//         interface argument as a modelling one: late (decision-level) fusion is "the most auditable,
//         since each modality's evidence stays separable" (§9.1). AERIS's default is therefore "late
//         fusion with joint explanation: optical evidence + SAR evidence → fused conclusion, with each
//         side inspectable" (§9.2).
//
//         THE CONSEQUENCE IS A RULE THE INTERFACE CANNOT BREAK: there is no blended product anywhere.
//         No averaged confidence, no composite raster, no single fused mask presented as the finding.
//         Every pixel on screen belongs to exactly one sensor, and the fusion lives entirely in the
//         verdict — which is language and geometry, never colour.
//
//         DISAGREEMENT IS THE PRODUCT. A system that averages a conflict into a mid-confidence number has
//         destroyed the most informative signal it had. Every agreement state below therefore carries a
//         physical reason, because "optical saw it and radar did not" is only useful once you know it can
//         mean either "no structural change happened" or "radar could not have seen it from that angle".

import type { PipelineStageCode } from "./pipeline-stages";

// ── Agreement ───────────────────────────────────────────────────────────────────────────────────

/**
 * How the two sensors relate on one candidate finding.
 *
 * Four states, and the ordering is deliberate: `conflict` sorts first everywhere it is listed, because it
 * is the one an analyst must read rather than scan.
 */
export const AGREEMENT_STATES = ["conflict", "corroborated", "optical-only", "radar-only"] as const;

export type AgreementState = (typeof AGREEMENT_STATES)[number];

export interface AgreementDefinition {
  id: AgreementState;
  label: string;
  /** What the state asserts, in the operator's terms. */
  summary: string;
  /**
   * Why it can happen, physically. Plural because the whole point is that a single state has more than
   * one cause and the operator has to pick between them — the page's job is to name the candidates.
   */
  causes: readonly string[];
  /** What to do about it. Null where the state needs no action. */
  action: string | null;
  /** Semantic tone. Maps to the theme's existing roles rather than introducing new colours. */
  tone: "positive" | "neutral" | "warning";
  /** Sorting weight. Conflict first, then the states that need reading, then the plain agreement. */
  priority: number;
}

export const AGREEMENT: Readonly<Record<AgreementState, AgreementDefinition>> = {
  conflict: {
    id: "conflict",
    label: "Conflict",
    summary: "The two sensors assert opposite things about this region.",
    causes: [
      "One sensor is wrong, and nothing in this pair says which.",
      "The two acquisitions are far enough apart in time to be describing different states of the ground.",
      "Co-registration between the sensors is worse than the size of the feature in question.",
    ],
    action: "Resolve with a third observation — another date, or the opposite radar look direction.",
    tone: "warning",
    priority: 0,
  },
  "optical-only": {
    id: "optical-only",
    label: "Optical only",
    summary: "The optical run found it; the radar run did not.",
    causes: [
      "Colour changed without structure — a crop cycle, resurfacing, or a coat of paint.",
      "The region sits in radar layover or shadow, where radar could not have seen it at all.",
      "The change is smaller than radar can resolve against its own speckle.",
    ],
    action: "Check the radar geometry masks before treating the absence as disagreement.",
    tone: "neutral",
    priority: 1,
  },
  "radar-only": {
    id: "radar-only",
    label: "Radar only",
    summary: "The radar run found it; the optical run did not.",
    causes: [
      "Structure changed without a spectral signature the optical bands record.",
      "The optical acquisition was under cloud — which the cloud mask can confirm outright.",
      "Surface moisture changed, which radar reads strongly and optical barely at all.",
    ],
    action: "Check the optical cloud mask; if it covers the region, this is not a disagreement.",
    tone: "neutral",
    priority: 2,
  },
  corroborated: {
    id: "corroborated",
    label: "Corroborated",
    summary: "Both sensors found it independently.",
    causes: [
      "Spectral change and structural change together — construction, demolition, or inundation.",
    ],
    action: null,
    tone: "positive",
    priority: 3,
  },
};

/** Ordered worst-first, so every list of agreement states leads with what has to be read. */
export const AGREEMENT_ORDER: readonly AgreementState[] = [...AGREEMENT_STATES].sort(
  (left, right) => AGREEMENT[left].priority - AGREEMENT[right].priority,
);

// ── When not to fuse ────────────────────────────────────────────────────────────────────────────

/**
 * Conditions under which the system declines to produce a fused verdict, from §9.2.
 *
 * A page that always fuses is not following its own policy. "These should not be combined, and here is
 * why" is a better answer than a fused number nobody should trust — and it is the cross-modal twin of the
 * timeline's fair-comparison advisory, which already refuses to call a seasonally-offset pair fair.
 */
export const FUSION_REFUSAL_IDS = [
  "poor-co-registration",
  "purely-spectral",
  "purely-structural",
  "auditability",
] as const;

export type FusionRefusalId = (typeof FUSION_REFUSAL_IDS)[number];

export interface FusionRefusal {
  id: FusionRefusalId;
  label: string;
  /** What the operator is told. Written as a statement about the data, not about the system. */
  reason: string;
  /** What is offered instead. Fusion being declined never means no answer. */
  instead: string;
}

export const FUSION_REFUSALS: Readonly<Record<FusionRefusalId, FusionRefusal>> = {
  "poor-co-registration": {
    id: "poor-co-registration",
    label: "Alignment too poor to fuse",
    reason:
      "The two sensors are not aligned to sub-pixel agreement, so a region in one does not reliably correspond to the same ground in the other.",
    instead: "Both sensors' findings are reported separately, with no agreement state asserted.",
  },
  "purely-spectral": {
    id: "purely-spectral",
    label: "A spectral question",
    reason:
      "This asks about reflectance — vegetation vigour, water colour, material. Radar does not measure it, so radar silence is not evidence either way.",
    instead: "Answered from optical alone, with radar available as context rather than as corroboration.",
  },
  "purely-structural": {
    id: "purely-structural",
    label: "A structural question",
    reason:
      "This asks about roughness, geometry or moisture. Optical does not measure it directly, so optical agreement would be coincidence rather than confirmation.",
    instead: "Answered from radar alone, with optical available as context.",
  },
  auditability: {
    id: "auditability",
    label: "Kept separate on purpose",
    reason:
      "The operator asked for per-sensor evidence. Fusing would remove exactly the separability that makes the answer checkable.",
    instead: "Both sensors reported side by side with no combined verdict.",
  },
};

// ── Radar specifics ─────────────────────────────────────────────────────────────────────────────

/**
 * Sentinel-1 IW polarisations, and what each one is actually sensitive to.
 *
 * Offering only one throws away half of what the sensor recorded. VV and VH answer different questions,
 * and their ratio is standard practice for separating built-up from vegetation.
 */
export const POLARISATIONS = ["VV", "VH", "ratio"] as const;
export type Polarisation = (typeof POLARISATIONS)[number];

export interface PolarisationDefinition {
  id: Polarisation;
  label: string;
  /** The physics, in one line. */
  sensitiveTo: string;
  /** When an analyst reaches for it. */
  useWhen: string;
}

export const POLARISATION_DETAIL: Readonly<Record<Polarisation, PolarisationDefinition>> = {
  VV: {
    id: "VV",
    label: "VV",
    sensitiveTo: "Surface roughness and water. Smooth water returns almost nothing and reads black.",
    useWhen: "Mapping open water, flooding, and bare or sealed surfaces.",
  },
  VH: {
    id: "VH",
    label: "VH",
    sensitiveTo: "Volume scattering — vegetation canopy and structurally complex targets.",
    useWhen: "Separating vegetation from bare ground, and finding structure under canopy.",
  },
  ratio: {
    id: "ratio",
    label: "VV/VH",
    sensitiveTo: "The balance between surface and volume scattering.",
    useWhen: "Separating built-up from vegetation at a glance — the standard composite.",
  },
};

/**
 * Facts about the two platforms that the interface has to state rather than assume.
 *
 * Revisit intervals matter here specifically: Sentinel-2 passes roughly every five days and Sentinel-1
 * every six to twelve, so the two lanes almost never have an acquisition on the same day. A cross-modal
 * pair is therefore ALWAYS offset, and the only honest thing to do is show by how much.
 */
export const SENSOR_PLATFORMS = {
  optical: {
    id: "optical" as const,
    label: "Optical",
    platform: "Sentinel-2",
    measures: "Reflected sunlight in discrete bands",
    reads: "Colour, vegetation, water, materials",
    blindTo: "Anything under cloud, and anything at night",
    revisitDays: 5,
    groundSampleDistanceMeters: 10,
  },
  radar: {
    id: "radar" as const,
    label: "Radar",
    platform: "Sentinel-1",
    measures: "Active C-band microwave backscatter, VV/VH",
    reads: "Structure, roughness, moisture",
    blindTo: "Terrain in layover or shadow, and detail finer than its own speckle",
    revisitDays: 9,
    groundSampleDistanceMeters: 10,
  },
} as const;

export type SensorId = keyof typeof SENSOR_PLATFORMS;

/**
 * How far apart a cross-modal pair can be before it stops describing the same state of the ground.
 *
 * Looser than the temporal comparator's threshold, and deliberately so: a twelve-day gap between two
 * optical dates is a different week's weather, while a twelve-day gap between an optical and a radar pass
 * is simply what the orbits allow. Tightening this to the temporal value would reject almost every real
 * cross-modal pair and teach the operator to ignore the advisory.
 */
export const CROSS_MODAL_PAIR = {
  /** Beyond this the pair is reported as offset, and any agreement state is downgraded. */
  fairOffsetDays: 12,
  /** Beyond this the pair is not treated as cross-modal at all — it is two separate observations. */
  maximumOffsetDays: 30,
  /**
   * Co-registration residual, in pixels, past which fusion is refused outright.
   *
   * Cross-sensor alignment is harder than same-sensor: different geometry, different resolution, and
   * radar's own terrain distortions. One pixel of residual between two optical dates is tolerable; one
   * pixel between optical and radar routinely means a building edge lands on the wrong side of a mask.
   */
  maximumCoRegistrationPixels: 1.5,
} as const;

// ── Phrasing ────────────────────────────────────────────────────────────────────────────────────

/**
 * Per-modality vocabulary, because the same word means different things to the two sensors.
 *
 * The design document is explicit: "SAR outputs must never be interpreted with optical intuition; the
 * explanation layer needs modality-aware phrasing." Dark in an optical scene is shadow or water; dark in
 * radar is smooth — OR UNSEEN. Those are different statements and no single legend can serve both.
 */
export const SENSOR_PHRASING: Readonly<
  Record<SensorId, { high: string; low: string; unit: string; caution: string }>
> = {
  optical: {
    high: "bright — high reflectance",
    low: "dark — low reflectance, shadow or water",
    unit: "reflectance",
    caution: "Reflectance is biased under thin cloud and in shadow.",
  },
  radar: {
    high: "strong return — rough or structured",
    low: "weak return — smooth, or not seen at all",
    unit: "dB",
    caution:
      "Speckle is multiplicative noise, not texture. Low return can mean smooth ground or radar shadow.",
  },
};

/**
 * Zoom past which speckle dominates a radar pixel and the readout should say so.
 *
 * Speckle looks exactly like texture to anyone reading radar with optical habits, and the mistake is
 * confident rather than tentative — which is what makes it worth one line of interface to prevent.
 */
export const SPECKLE_WARNING_METERS_PER_PIXEL = 8;

/** Which pipeline stage produces the cross-modal verdict, linking the Lab to the same trace spine. */
export const CROSS_MODAL_STAGE: PipelineStageCode = "S13";

/**
 * The operation id under which the cross-modal reading appears in the Toolbox and on the command bus.
 *
 * Named here rather than written inline because three places need to agree on it: the operation catalogue
 * that lists it, the workspace that toggles the lens when the row is pressed, and the Toolbox that renders
 * that row as pressed while the reading is open.
 */
export const CROSS_MODAL_OPERATION_ID = "cross-modal";

/**
 * The question an agreement row hands to the assistant.
 *
 * A template rather than a sentence built at the call site, because the phrasing is a product decision:
 * it states the row's own reason back and asks what would SETTLE it, which is the action every agreement
 * state's guidance points at. Asking "what is this?" would send the operator round the same loop they
 * just read.
 */
export function agreementQuestion(input: {
  stateLabel: string;
  label: string;
  reason: string;
}): string {
  return `The optical and radar runs are marked "${input.stateLabel.toLowerCase()}" over ${input.label}. ${input.reason} What should I conclude from this, and what would settle it?`;
}
