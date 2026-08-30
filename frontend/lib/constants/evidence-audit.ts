// lib/constants/evidence-audit.ts — the confidence bands the claim corpus is triaged by.
//
// what  : Named confidence ranges, with what each one means for a reader deciding whether to quote a claim.
// where : Read by the Evidence Audit's filter row and its rows; sent on the wire as `band`.
// how   : Bands rather than a free slider, because the question an auditor asks is categorical — "show me
//         what I should not be quoting" — and a slider makes them invent a threshold the system has an
//         opinion about. The boundaries are the same ones the answer surface already treats differently.
//
//         `unasserted` is a band, not a gap. A null confidence means AERIS declined to state one, which is
//         a first-class result everywhere else in this codebase and has to be findable here too — it is
//         precisely the set an auditor wants to see.

export const CONFIDENCE_BAND_IDS = ["all", "low", "moderate", "high", "unasserted"] as const;

export type ConfidenceBandId = (typeof CONFIDENCE_BAND_IDS)[number];

export interface ConfidenceBand {
  id: ConfidenceBandId;
  label: string;
  /** Inclusive lower bound, exclusive upper. Null bounds mean the band does not filter on confidence. */
  minimum: number | null;
  maximum: number | null;
  /** Matches only claims with no asserted confidence. */
  isUnasserted: boolean;
  /** What this band means for someone deciding whether to rely on the claim. */
  guidance: string;
}

export const CONFIDENCE_BANDS: Readonly<Record<ConfidenceBandId, ConfidenceBand>> = {
  all: {
    id: "all",
    label: "All",
    minimum: null,
    maximum: null,
    isUnasserted: false,
    guidance: "Every claim in the corpus.",
  },
  low: {
    id: "low",
    label: "Below 60%",
    minimum: 0,
    maximum: 0.6,
    isUnasserted: false,
    guidance: "Treat as a lead, not a finding. Corroborate before it leaves the building.",
  },
  moderate: {
    id: "moderate",
    label: "60–85%",
    minimum: 0.6,
    maximum: 0.85,
    isUnasserted: false,
    guidance: "Usable with its caveats attached. Check the masks over the region first.",
  },
  high: {
    id: "high",
    label: "85% and above",
    minimum: 0.85,
    maximum: null,
    isUnasserted: false,
    guidance: "Strong enough to quote, provided the inputs behind it were fair.",
  },
  unasserted: {
    id: "unasserted",
    label: "No confidence stated",
    minimum: null,
    maximum: null,
    isUnasserted: true,
    guidance:
      "AERIS declined to assert a confidence. That is a refusal, not a zero — read the claim's evidence before using it at all.",
  },
};

export const CONFIDENCE_BAND_ORDER: readonly ConfidenceBandId[] = [
  "all",
  "low",
  "moderate",
  "high",
  "unasserted",
];

/** Whether a claim's confidence falls in a band. Shared by the mock filter and the UI's own checks. */
export function isConfidenceInBand(confidence: number | null, bandId: ConfidenceBandId): boolean {
  const band = CONFIDENCE_BANDS[bandId];

  if (band.isUnasserted) {
    return confidence === null;
  }
  if (bandId === "all") {
    return true;
  }
  if (confidence === null) {
    return false;
  }

  return (
    (band.minimum === null || confidence >= band.minimum) &&
    (band.maximum === null || confidence < band.maximum)
  );
}
