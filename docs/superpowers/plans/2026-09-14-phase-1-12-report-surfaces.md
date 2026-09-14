# Phase 1.12 Research Report Rebuild Plan

**Goal:** Make every completed investigation read like a concise professional research briefing while
preserving the evidence-first contract and the backend's documented module boundaries.

**Architecture:** `services/reports/generator.py` turns validated claims, evidence, figures, and model records
into one typed reader narrative. The only LLM instructions live in `services/prompts/report.py`; the complete
draft is rejected if it introduces a numeral or transport identifier. Markdown, voice preparation, GeoJSON,
and modular PDF layout consume the same narrative and never compute scientific values.

## Acceptance checklist

- [x] Reopen Phase 1.12 and document why the previous output failed the quality gate.
- [x] Remove `services/reporting/`; align implementation to the authoritative `services/reports/` package.
- [x] Move all report LLM instructions to `services/prompts/report.py`.
- [x] Define typed objective, executive summary, question/answer, key fact, per-image explanation, model role,
  limitation, final assessment, and voice fields.
- [x] Add numeric and internal-identifier guards around the whole LLM editorial pass.
- [x] Split PDF theme, reusable components, and page composition.
- [x] Fix page roles: cover; decision brief; paired visual evidence; model rationale; limitations/final assessment.
- [ ] Run a strongly supported investigation end to end, inspect every detailed and summary PDF page, and retain it.
- [ ] Run an out-of-domain or evidence-limited investigation end to end, keep useful findings in the body, place
  non-grounded boundaries on the last page, inspect every page, and retain it.
- [ ] Validate Markdown, voice prose, JSON, GeoJSON, internal-reference hygiene, and all claim numbers.
- [ ] Run focused tests, full backend tests, Ruff, doctor, and diff checks before marking Phase 1.12 done.
