// lib/constants/pipeline-stages.ts — the canonical 20-stage remote-sensing analysis pipeline, as data.
//
// what  : Stage codes S1–S20, their labels and what each one actually does, plus the subset that can
//         produce an inspectable intermediate artefact.
// where : Read by the investigation feature's execution spine and by the mock analysis stream. The
//         backend emits stage codes on every trace step; the frontend looks the copy up here.
// how   : These are transcribed from SatqueryAI.pdf §15.1, which is the contract both sides work from.
//         Keeping them here rather than sending labels over the wire means the backend sends a short
//         enum value, the copy stays editable without a deploy, and a stage code that does not exist
//         fails loudly at the schema boundary instead of rendering as an empty row.
//
//         `producesArtefact` marks the stages whose intermediate output is worth putting on the map —
//         the cloud mask, the registration residual, the index map. PDF §21.2 already requires those to
//         be retained as addressable artefacts, so surfacing them costs the backend a URI it already has.

export const PIPELINE_STAGE_CODES = [
  "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10",
  "S11", "S12", "S13", "S14", "S15", "S16", "S17", "S18", "S19", "S20",
] as const;

export type PipelineStageCode = (typeof PIPELINE_STAGE_CODES)[number];

export interface PipelineStageDefinition {
  code: PipelineStageCode;
  label: string;
  description: string;
  /** True when this stage can hand back an intermediate product the operator can inspect on the scene. */
  producesArtefact: boolean;
}

export const PIPELINE_STAGES: Readonly<Record<PipelineStageCode, PipelineStageDefinition>> = {
  S1: { code: "S1", label: "Data ingestion", description: "Raw imagery referenced and stored immutably.", producesArtefact: false },
  S2: { code: "S2", label: "File identification", description: "Format, band count and driver detected.", producesArtefact: false },
  S3: { code: "S3", label: "Metadata extraction", description: "Sensor, acquisition date, processing level, nodata.", producesArtefact: false },
  S4: { code: "S4", label: "CRS detection", description: "Coordinate reference system resolved and validated.", producesArtefact: false },
  S5: { code: "S5", label: "Band identification", description: "Band indices mapped to wavelengths.", producesArtefact: false },
  S6: { code: "S6", label: "Quality check", description: "Nodata fraction, histogram sanity, resolution report.", producesArtefact: false },
  S7: { code: "S7", label: "Cloud handling", description: "Cloud and shadow masked; usable coverage flagged.", producesArtefact: true },
  S8: { code: "S8", label: "Spatial normalisation", description: "Reprojected to the analysis CRS and grid-aligned.", producesArtefact: false },
  S9: { code: "S9", label: "Co-registration", description: "Image pair geometrically aligned; residual estimated.", producesArtefact: true },
  S10: { code: "S10", label: "Resampling", description: "Band resolutions harmonised onto one grid.", producesArtefact: false },
  S11: { code: "S11", label: "Tiling", description: "Windowed reads with overlap for model inference.", producesArtefact: false },
  S12: { code: "S12", label: "Feature extraction", description: "Spectral indices and per-tile model features.", producesArtefact: true },
  S13: { code: "S13", label: "Specialist analysis", description: "Detection, segmentation, change or SAR models run.", producesArtefact: true },
  S14: { code: "S14", label: "VLM reasoning", description: "Vision-language reading of rendered tiles or regions.", producesArtefact: false },
  S15: { code: "S15", label: "Evidence localisation", description: "Outputs bound to georeferenced regions.", producesArtefact: true },
  S16: { code: "S16", label: "Answer generation", description: "Structured results rendered as constrained language.", producesArtefact: false },
  S17: { code: "S17", label: "Visualisation", description: "Overlays, change maps and comparison views prepared.", producesArtefact: false },
  S18: { code: "S18", label: "Confidence estimation", description: "Per-tool scores and validation checks aggregated.", producesArtefact: false },
  S19: { code: "S19", label: "Provenance logging", description: "Inputs, versions, parameters and timings appended.", producesArtefact: false },
  S20: { code: "S20", label: "Final response", description: "Answer, evidence, confidence and trace released.", producesArtefact: false },
} as const;

export function getPipelineStage(code: PipelineStageCode): PipelineStageDefinition {
  return PIPELINE_STAGES[code];
}
