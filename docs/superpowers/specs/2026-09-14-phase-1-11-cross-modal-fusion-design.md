# Phase 1.11 Cross-Modal Fusion Design

## Goal

Build an auditable backend graph that accepts one optical and one SAR acquisition over the same ground, analyses each independently, and only then produces a spatial agreement ledger and fused answer. Phase 1.11 covers a single ground state; four-image temporal fusion remains outside this phase.

## Decisions

- Use decision-level late fusion. Raw optical reflectance and SAR backscatter are never mixed.
- Use deterministic, physically interpretable measurements at Sentinel resolution instead of the out-of-domain LoveDA segmenter.
- Optical water is measured with MNDWI and built-up evidence with NDBI, using cloud-masked L2A reflectance.
- Radar water is a dark-target measurement and built-up evidence is a strong-return/roughness measurement using terrain-corrected VV and VV/VH evidence.
- Each branch completes without reading the other branch's masks, claims, confidence, or thresholds.
- A fusion row is created from spatial components on the common grid. Rows are derived from masks; no state is scripted to satisfy the gate.
- An affine-grid residual of `>= 1.0` pixel refuses fusion. This verifies the supplied raster grids; it does not claim image-content co-registration.
- A sensor's silence is informative only where its quality mask says the sensor observed the ground and its measurements have usable dynamic range.
- Fused confidence is the minimum of the contributing sensor confidences. It is never an average.
- A genuine conflict blocks a fused headline and requests a third observation.

## Inputs and metadata

The existing two-input request remains the external shape. For `CROSS_MODAL`, input roles are normalized by inspected modality, not CLI order. Exactly one optical scene directory and one SAR scene directory are required. Both must be georeferenced.

The graph accepts SAR assets already materialized on the optical analysis grid, verifies and records their affine-grid residual, and refuses other grids with an actionable reprojection error. This is deliberately not an image-content registration claim. Acquisition timestamps and platforms are read from standard Sentinel scene identifiers; unknown timestamps are refused because `offsetDays` cannot otherwise be stated honestly.

Required assets:

- Optical: `B03`, `B08`, `B11`, and `SCL`; `B02` and `B04` are used for the evidence figure.
- SAR: `VV` and `VH` RTC power. The RTC input is already calibrated, so the graph must not square or recalibrate it.

## Graph

```text
S1 validate and normalize modalities
  -> S9 measure cross-sensor registration
  -> [optical S7/S12/S15] || [radar S10/S13/S15]
  -> S15 build spatial agreement ledger
  -> S16 generate constrained answer from ledger
  -> S18 aggregate confidence
  -> S19 persist provenance, evidence graph, and cross-modal result
```

The two sensor branches fan out after registration and fan in only at ledger construction. LangGraph reducers merge lists; sensor-specific products use distinct state keys to prevent last-writer-wins corruption.

## Scientific kernels

Pure functions under `services/optical_sar/math/` own equations and mask comparison:

- Optical masks apply SCL exclusion before index arithmetic. MNDWI is `(green - swir) / (green + swir)` and NDBI is `(swir - nir) / (swir + nir)` with invalid denominators excluded.
- SAR masks operate on linear power after fixed-order preprocessing. Dark water requires VV <= -17 dB and VH <= -22 dB; built-up requires VV >= -8 dB and VH >= -15 dB. These are fixed, documented physical thresholds; dynamic-range checks prevent a flat scene from making sensor silence look like evidence.
- Agreement uses connected components from the union of optical and radar masks. Intersection-over-union and obscuration determine corroborated, optical-only, or radar-only. Opposing class assignments on observed ground are conflicts.
- Areas use the existing equal-area measurement service, never pixel-count guesses.

## Contract and outputs

Backend Pydantic models mirror `crossModalResultSchema` exactly:

- `optical` and `radar` sensor runs retain their own layers, evidence, claims, model identity, confidence, and obscured fraction.
- `advisory` contains temporal offset, measured affine-grid residual, and physical notes.
- `verdict.rows` contain feature identifiers for both sensors, per-sensor confidence, area, state, and reason.
- `verdict` carries a headline only when fusion is admissible and unconflicted. When it cannot, S15 emits one confidence-null primary claim that says why no fused conclusion is available, so S16 cannot quietly substitute independent branch readings for a fused answer.

The completed result is checkpointed as plain wire data and saved as a run artefact. Figures show the optical masks, SAR masks/quality exclusions, and a categorical fusion overlay. Normal claim/layer/figure events remain the live audit trail.

## Refusals

Fusion refuses while retaining independent sensor results when:

- the pair is missing a modality, is not georeferenced, is not already on one common grid, or lacks required bands;
- acquisition time cannot be established or exceeds 30 days;
- residual registration is `>= 1.0` pixel;
- optical observed fraction or radar observable fraction is too small;
- either sensor has insufficient finite samples or dynamic range for its measurement;
- the query is purely spectral, purely structural, or explicitly asks to keep sensors separate.

## Verification

- Unit tests use hand-derived arrays for every formula, threshold boundary, obscuration precedence, agreement state, confidence rule, and refusal.
- Contract tests validate serialized results against the vendored frontend schema.
- Integration tests run the graph with synthetic GeoTIFF fixtures through checkpointing, MinIO artefacts, journals, figures, and provenance.
- Refusal integration tests cover swapped input order, missing modality, missing band, unusable registration, time offset, and uninformative sensor data.
- The real gate acquires a close Sentinel-2/Sentinel-1 pair over a Mumbai AOI containing coast and dense urban ground, runs the user question, and verifies at least one corroborated and one single-sensor/disagreement row with non-empty physical reasons.
- The best complete real run remains under `backend/runs/` with its result JSON, journal, figures, evidence graph, and provenance.

## Deferred Phase 1.10 debt

These findings are recorded but deliberately not mixed into Phase 1.11 implementation:

- enforce model training-domain safeguards for 10 m land-cover and learned change requests;
- refresh the vendored analysis event contract so `figure-ready` production journals validate;
- validate complete figure-bearing production journals, not only the probe graph.
