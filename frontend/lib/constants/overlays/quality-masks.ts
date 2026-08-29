// lib/constants/overlays/quality-masks.ts — where the answer cannot be trusted, and why.
//
// what  : The validity masks a run can produce — cloud, cloud shadow, no-data, co-registration residual,
//         SAR layover and radar shadow — each with what it invalidates and what an operator should do
//         about it.
// where : Bound to mask products by the overlay catalogue; drives the MASKS section of the layer stack
//         and the caveat lines the answer panel prints alongside a claim.
// how   : A MASK IS NOT A FINDING. A change mask asserts that something happened; a cloud mask asserts
//         that nothing can be asserted. They are opposite kinds of statement and were sharing one list,
//         which is the same mistake that reference layers were already separated to avoid.
//
//         Every mask therefore carries `invalidates` — what a claim inside this region cannot say — in
//         the operator's terms rather than the pipeline's. "The surface was not observed on this date"
//         is actionable; "SCL class 9" is not.
//
//         `severity` decides whether obscuration is a footnote or a reason to refuse the question. It is
//         the field that lets the system decline to answer rather than answer confidently over cloud,
//         which is the failure mode this product exists to avoid.
//
//         Masks render as HATCHING, never as a solid fill. That is the cartographic convention for "no
//         data here", it stays legible over any imagery because it lets the imagery through, and — the
//         real reason — it cannot be mistaken at a glance for a coloured finding.

import type { PipelineStageCode } from "../pipeline-stages";

export const QUALITY_MASK_IDS = [
  "cloud",
  "cloud-shadow",
  "no-data",
  "co-registration",
  "sar-layover",
  "sar-shadow",
] as const;

export type QualityMaskId = (typeof QUALITY_MASK_IDS)[number];

/**
 * How much a mask costs an answer.
 *
 * `blocking` means a claim inside the masked region must not be made at all; `degrading` means it can be
 * made with a stated caveat; `advisory` means it is worth knowing and changes nothing.
 */
export type MaskSeverity = "blocking" | "degrading" | "advisory";

export interface QualityMask {
  id: QualityMaskId;
  label: string;
  description: string;
  severity: MaskSeverity;
  /** What a claim inside this region cannot say. Printed verbatim next to affected claims. */
  invalidates: string;
  /** What the operator can do about it. Null where nothing can be done but wait for another pass. */
  remedy: string | null;
  producedBy: PipelineStageCode;
  /** Which modality produces it, so an optical-only investigation never lists radar masks. */
  modality: "optical" | "sar" | "any";
}

export const QUALITY_MASKS: Readonly<Record<QualityMaskId, QualityMask>> = {
  cloud: {
    id: "cloud",
    label: "Cloud",
    description:
      "Pixels where cloud sits between the sensor and the ground, from the scene classification layer or an s2cloudless run.",
    severity: "blocking",
    invalidates: "The surface was not observed here on this date. Nothing about the ground can be read from it.",
    remedy: "Pick a clearer acquisition on the timeline, or compare against the radar scene, which sees through cloud.",
    producedBy: "S7",
    modality: "optical",
  },
  "cloud-shadow": {
    id: "cloud-shadow",
    label: "Cloud shadow",
    description:
      "Ground darkened by cloud rather than by its own character. Sits offset from the cloud by the sun angle.",
    severity: "degrading",
    invalidates:
      "Reflectance here is suppressed, so index values read low and a change detector sees loss that did not happen.",
    remedy: "Treat vegetation loss inside shadow as unproven until a clear date confirms it.",
    producedBy: "S7",
    modality: "optical",
  },
  "no-data": {
    id: "no-data",
    label: "No data",
    description: "Outside the acquisition footprint, or nodata-filled inside it.",
    severity: "blocking",
    invalidates: "There is no observation here at all — this is absence of data, not absence of change.",
    remedy: "Narrow the area of interest to the covered extent, or attach a scene that covers the gap.",
    producedBy: "S6",
    modality: "any",
  },
  "co-registration": {
    id: "co-registration",
    label: "Co-registration residual",
    description:
      "Where the two dates do not align to sub-pixel accuracy after geometric alignment. Concentrates on edges and steep terrain.",
    severity: "degrading",
    invalidates:
      "Apparent change along edges here may be misalignment rather than a real difference on the ground.",
    remedy: "Weigh area-based findings over edge-based ones inside this region.",
    producedBy: "S9",
    modality: "any",
  },
  "sar-layover": {
    id: "sar-layover",
    label: "Radar layover",
    description:
      "Terrain tilted toward the sensor collapses into one range bin, so slope and structure fold on top of each other.",
    severity: "blocking",
    invalidates: "Backscatter here belongs to more than one place on the ground and cannot be attributed.",
    remedy: "Use an optical observation, or a radar pass from the opposite look direction.",
    producedBy: "S7",
    modality: "sar",
  },
  "sar-shadow": {
    id: "sar-shadow",
    label: "Radar shadow",
    description: "Ground the radar beam never reached, behind terrain or tall structure.",
    severity: "blocking",
    invalidates: "No return came from here, so low backscatter means unseen, not smooth.",
    remedy: "Use an optical observation, or a radar pass from the opposite look direction.",
    producedBy: "S7",
    modality: "sar",
  },
};

/** Ordered worst-first, so the answer panel leads with the caveat that costs the most. */
export const MASK_SEVERITY_ORDER: Readonly<Record<MaskSeverity, number>> = {
  blocking: 0,
  degrading: 1,
  advisory: 2,
};

export const MASK_SEVERITY_COPY: Readonly<Record<MaskSeverity, string>> = {
  blocking: "No claim can be made inside this region",
  degrading: "Claims inside this region carry a caveat",
  advisory: "Worth knowing; does not change the reading",
};
