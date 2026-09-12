// features/investigation/lib/version-diff.ts — pure diff between two investigation versions.
//
// what  : Compares two InvestigationVersion snapshots and returns a list of DiffSection[],
//         covering inputs, workflow, parameters, models, result metrics, and confidence.
// where : Called by VersionCompareSheet (UI) and available to the agent for narration.
// how   : Pure function — no side effects, no API calls, no React dependencies.
//         The rule from the spec: only sections with at least one changed item are included.
//         Empty diff → empty array; the caller renders "No differences found."
//
//         The diff is always client-side. No backend round-trip is needed because the version
//         snapshot carries the full recorded graph, including parameters and model versions.

import type { InvestigationVersion, DiffSection, DiffRow } from "../types/version.types";

/**
 * Compares two investigation versions and returns an array of changed sections.
 * Sections with no changes are omitted entirely.
 */
export function diffVersions(a: InvestigationVersion, b: InvestigationVersion): DiffSection[] {
  const sections: DiffSection[] = [];

  // ── 1. Inputs ─────────────────────────────────────────────────────────────────────────────────
  const inputRows: DiffRow[] = [];

  // Scene slots — compare by role
  const rolesA = new Map(a.snapshot.sceneSlots.map((s) => [s.role, s.sceneId]));
  const rolesB = new Map(b.snapshot.sceneSlots.map((s) => [s.role, s.sceneId]));
  const allRoles = new Set([...rolesA.keys(), ...rolesB.keys()]);
  for (const role of allRoles) {
    const sceneA = rolesA.get(role) ?? "—";
    const sceneB = rolesB.get(role) ?? "—";
    if (sceneA !== sceneB) {
      inputRows.push({ label: `Scene (${role})`, before: sceneA, after: sceneB });
    }
  }

  // Timeline pair
  const tlA = a.snapshot.timelinePair;
  const tlB = b.snapshot.timelinePair;
  if (tlA.baselineSceneId !== tlB.baselineSceneId) {
    inputRows.push({
      label: "Timeline baseline",
      before: tlA.baselineSceneId ?? "—",
      after: tlB.baselineSceneId ?? "—",
    });
  }
  if (tlA.comparisonSceneId !== tlB.comparisonSceneId) {
    inputRows.push({
      label: "Timeline comparison",
      before: tlA.comparisonSceneId ?? "—",
      after: tlB.comparisonSceneId ?? "—",
    });
  }

  if (inputRows.length > 0) {
    sections.push({ kind: "inputs", title: "Inputs", rows: inputRows });
  }

  // ── 2. Workflow (steps added / removed by operationId) ────────────────────────────────────────
  const workflowRows: DiffRow[] = [];
  const opIdsA = new Set(a.snapshot.steps.map((s) => s.operationId ?? s.stageCode));
  const opIdsB = new Set(b.snapshot.steps.map((s) => s.operationId ?? s.stageCode));

  for (const opId of opIdsA) {
    if (!opIdsB.has(opId)) {
      workflowRows.push({ label: opId, before: "present", after: "removed" });
    }
  }
  for (const opId of opIdsB) {
    if (!opIdsA.has(opId)) {
      workflowRows.push({ label: opId, before: "absent", after: "added" });
    }
  }

  if (workflowRows.length > 0) {
    sections.push({ kind: "workflow", title: "Workflow", rows: workflowRows });
  }

  // ── 3. Parameters (per step, only changed keys) ───────────────────────────────────────────────
  const paramRows: DiffRow[] = [];
  const stepsMapA = new Map(a.snapshot.steps.map((s) => [s.operationId ?? s.stageCode, s]));
  const stepsMapB = new Map(b.snapshot.steps.map((s) => [s.operationId ?? s.stageCode, s]));

  for (const [opId, stepA] of stepsMapA) {
    const stepB = stepsMapB.get(opId);
    if (!stepB) continue;

    const allParamKeys = new Set([
      ...Object.keys(stepA.parameters),
      ...Object.keys(stepB.parameters),
    ]);

    for (const key of allParamKeys) {
      const valA = String(stepA.parameters[key] ?? "—");
      const valB = String(stepB.parameters[key] ?? "—");
      if (valA !== valB) {
        paramRows.push({ label: `${opId} · ${key}`, before: valA, after: valB });
      }
    }
  }

  if (paramRows.length > 0) {
    sections.push({ kind: "parameters", title: "Parameters", rows: paramRows });
  }

  // ── 4. Models (id@version per step) ──────────────────────────────────────────────────────────
  const modelRows: DiffRow[] = [];

  for (const [opId, stepA] of stepsMapA) {
    const stepB = stepsMapB.get(opId);
    if (!stepB) continue;
    if (!stepA.model && !stepB.model) continue;

    const modelStrA = stepA.model ? `${stepA.model.id}@${stepA.model.version}` : "—";
    const modelStrB = stepB.model ? `${stepB.model.id}@${stepB.model.version}` : "—";

    if (modelStrA !== modelStrB) {
      modelRows.push({ label: opId, before: modelStrA, after: modelStrB });
    }
  }

  if (modelRows.length > 0) {
    sections.push({ kind: "models", title: "Models", rows: modelRows });
  }

  // ── 5. Result metrics ─────────────────────────────────────────────────────────────────────────
  const resultRows: DiffRow[] = [];
  const metricsMapA = new Map(
    a.snapshot.resultSummary.claimMetrics.map((m) => [m.label, m]),
  );
  const metricsMapB = new Map(
    b.snapshot.resultSummary.claimMetrics.map((m) => [m.label, m]),
  );
  const allMetricLabels = new Set([...metricsMapA.keys(), ...metricsMapB.keys()]);

  for (const label of allMetricLabels) {
    const mA = metricsMapA.get(label);
    const mB = metricsMapB.get(label);
    const valA = mA != null ? `${mA.value} ${mA.unit}` : "—";
    const valB = mB != null ? `${mB.value} ${mB.unit}` : "—";
    if (valA !== valB) {
      resultRows.push({ label, before: valA, after: valB });
    }
  }

  if (resultRows.length > 0) {
    sections.push({ kind: "result", title: "Result Metrics", rows: resultRows });
  }

  // ── 6. Confidence ─────────────────────────────────────────────────────────────────────────────
  const confA = a.snapshot.resultSummary.confidence;
  const confB = b.snapshot.resultSummary.confidence;
  const confStrA = confA != null ? `${Math.round(confA * 100)}%` : "—";
  const confStrB = confB != null ? `${Math.round(confB * 100)}%` : "—";

  if (confStrA !== confStrB) {
    sections.push({
      kind: "confidence",
      title: "Confidence",
      rows: [{ label: "Overall confidence", before: confStrA, after: confStrB }],
    });
  }

  return sections;
}
