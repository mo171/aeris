# 04 — The Workspace Model: review of the "ArcGIS Pro comparison" proposal

> **Status:** review + build plan · **v2, 2026-09-11** (incorporates senior review of v1) · **Scope:** `frontend/` only
> **Input:** the 16-point proposal comparing AERIS to ArcGIS Pro's workspace model, and the review of v1 of this document
> **Read first:** `fcontext/memory.md` (what is actually built), `architecture-context.md` (the rules every item below obeys)

**Changes from v1:** phase order rebuilt around the differentiators (contract → canvas + node inspection → re-run → versions → project → history/polish); `dependsOn` and a full `AnalysisStep` shape added to the contract; the Toolbox regrouped as intent-level operations; the evidence/operator layer distinction made visual (🔒 / ✎); and §2 now **locks** the Project / Investigation / Mission terminology with a UI access map instead of recommending one.

---

## 0. The verdict in one paragraph

The proposal is right about the destination and wrong about how far away we are. Of its 16 points, **five are already built** (some beyond what was proposed), **six are partially built and need a contract change more than a UI change**, **three are genuinely new and are the product**, and **two contradict the proposal's own §15** and should not be built. The single most important sentence in the proposal is the last one — *"AI is operating the analytical workspace for you, and you can inspect, control, reproduce, modify, and version everything it does"* — and the reason we can get there cheaply is that three decisions already in this codebase were made for exactly that: **the command bus** (every action is already an agent tool), **layers as data** (every product is already a descriptor), and **operations as a catalogue** (every analysis is already a named, typed entry). The work below extends those three seams; it does not add a fourth.

The one thing missing at the foundation, which every proposed item silently depends on: **an analysis step has no parameters and no graph relationships on the wire.** A trace step records *which model ran* but not *with what threshold*, *from which inputs*, *producing which outputs*, or *after which other steps*. Until those fields exist there is nothing to inspect in a node, nothing to edit before a re-run, nothing to diff between versions, and no graph to draw. That is Phase A, and it is a contract change, not a feature. **Do not start with a canvas UI; start with a data model that can represent one.**

---

## 1. Point-by-point: built / partial / new / don't

Legend — **✅ Built** · **🟡 Partial** · **🆕 New** · **❌ Don't build** · **⚠️ Correction to the proposal**

| # | Proposal | Status | What exists today | What is actually missing |
|---|---|---|---|---|
| 1 | "Where AERIS is today" | ✅ | Accurate. Omits that the left panel already has a **Toolbox tab**, a **Masks** section, a **Sensors** section (lens), and that the trace already has per-step model + rationale + artefact peek. | — |
| 2 | ArcGIS Pro's workspace model as the reference | — | Framing. Agreed as a *reference for completeness*, not as a target. | — |
| 3 | **Layers panel** with visibility / opacity / order / group / rename / remove / zoom-to / style / metadata / isolate / compare | 🟡 | `InputsPanel` already has FINDINGS / MASKS / CONTEXT (reference) sections, each row with visibility, opacity slider, solo/isolate, focus, per-layer stats (count, area, mean confidence) and **provenance** (model@version). Base rasters come from the timeline. Building style exists. `comparatorSide` exists on the descriptor. | **Reorder** and **basemap switcher** (open since audit item 11), a per-layer **metadata drawer**, per-layer **ramp override UI**. ⚠️ **Rename and Remove must not exist for evidence layers** — §2.3, now with a visual rule. |
| 4 | **Toolbox** with ANALYSIS / TEMPORAL / MULTIMODAL / VECTOR / RASTER / AI sections | 🟡 / ❌ | `ANALYSIS_OPERATIONS` has 11 entries with declared requirements and reasons; 36 registry commands; overlay browser; search. Measurement lives in the draw tools. Report generation exists. | **Grounding**, **describe scene**, **trend analysis**, **change explanation** as named operations; **parameters per operation** (the real gap); regrouping as intent-level categories (§3.7). ❌ VECTOR and RASTER sections — §2.4. |
| 5 | Don't make the user go through the Toolbox; AI interprets the goal | ✅ | This *is* the design: free text is primary, `operationId` is the typed shortcut, both hit **one pipeline**. The autonomous plan is fetched, shown and editable *before* execution. | Nothing except making the plan *visible as a graph* — point 6. |
| 6 | **Analysis Canvas** — AI builds the workflow, human inspects/edits, AI executes | 🆕 | Two halves exist separately: the **plan** (pre-execution, strike-out editable) and the **trace** (S1–S20 linear spine, live). | The **graph**: nodes with inputs → outputs and `dependsOn` edges; one component that is the plan *before*, the live trace *during*, the record *after*. §3.2. |
| 7 | **Node inspection** — inputs, method, threshold, output, runtime, evidence links, re-run / edit | 🟡 | `TraceStepNode` row: stage, model + version, **routing rationale**, duration, artefact peek. Claims carry `traceStepId`. | **Parameters**, **inputs/outputs by reference**, reverse links, **Re-run with overrides** and downstream re-execution. §3.2–3.3. |
| 8 | **Project → Investigation → Run** hierarchy | 🆕 | Investigation → Run exists. **Mission** exists as a promoted investigation with globe markers. | A **Project** container and a sharp meaning for Mission. **Locked in §2.5.** |
| 9 | **Analysis History** | 🟡 | Run history: reopenable rows with time, duration, confidence. | Non-run events. The command bus is the source — §3.6. |
| 10 | **Version snapshots + compare** | 🆕 | Every run is *almost* a snapshot; `traceId` is the provenance identity. | Named immutable checkpoints and a pure diff. §3.4. |
| 11 | Right panel with ANALYSIS / EVIDENCE / CHAT modes | 🟡 | Answer surface with claims → spotlight → evidence; run history; composer; lens verdict slot. | A per-claim **provenance chain** view. ⚠️ CHAT must not become the default. Polish tier. |
| 12 | Observation timeline with clickable acquisitions | ✅ | Built beyond the proposal: markers, snap handles, play-through, cloud ceiling, coverage gaps, archive query, recommended pair, comparability advisory, cited-scene marks, SAR auto-fetch, pop-out inspector. | **Event annotations** on the axis. Polish tier. |
| 13 | **Data / Catalog view** | 🆕 | Mission Command has the global imagery catalogue. Derived products live in the layer stack. | The **Project page** — 8 and 13 are one item. |
| 14 | No ribbon; command search that suggests operations | ✅ / 🟡 | `CommandPalette` over the registry, Toolbox search. | ⚠️ Operations are **not in the palette** (parameterised commands are hidden by rule). §3.7. |
| 15 | What NOT to build | ✅ | Agreed in full. | ⚠️ The proposal's own §4 (VECTOR / RASTER) violates its §15. |
| 16 | Six surfaces + target layout | ✅ | All exist except the canvas, which is a **zone**, not a route (§2.2). | — |

**Prerequisite not in the proposal:** `navigation.ts` still carries the comment that `/evidence` does not hydrate while the flag reads `isAvailable: true`. Someone must click a filter chip on `/evidence` on a clean production build and either delete the comment or flip the flag back.

---

## 2. Corrections and locked decisions

### 2.1 The proposal under-counts what exists
Points 3, 5, 12 and 14 read as gaps because the screenshot shows the collapsed state. The honest new-work list is in §4.

### 2.2 The Analysis Canvas is a zone, not a page
It opens **in the bottom zone** where the spine sits (`INVESTIGATION_LAYOUT.traceExpandedHeightPx`, plus a full-height toggle), never as a route. The "surface must be a place" test applies: a canvas for *this* investigation needs an id the rail cannot supply, and an operator reading a node's threshold will immediately want the scene, the layers and the composer — the exact mistake cross-modal made and undid.

### 2.3 Evidence layers are locked; operator layers are editable — and it must be visible
An **evidence** layer's title is provenance: the model produced it under that name, the trace step names it, the report cites it. Renaming breaks the join; removing deletes evidence from an investigation whose whole claim is that evidence is retained. **Reference** layers and **drawn regions** are the operator's and may be renamed and removed.

The distinction becomes a visual rule in the Layers tab, not a hidden capability difference:

```
EVIDENCE                                OPERATOR
────────────────────────                ────────────────────────
🔒 Built-up change                       ✎ AOI
   change-detection@2.1 · 39.7 ha           drawn 14:21 · 226.9 km²
   S13 · trace step 15                   ✎ Reference polygon
🔒 Detected structures                   ✎ Administrative boundaries (reference)
   object-detection@1.8 · 18 objects
```

🔒 rows: hide, solo, opacity, focus, metadata, **annotate** (an operator note stored beside the descriptor, never in it). ✎ rows: all of that plus rename and remove. The lock is rendered from the row's *kind* (`EvidenceLayer` vs reference/region), so it cannot be applied inconsistently. This is what makes the product read as trustworthy rather than merely powerful.

### 2.4 VECTOR and RASTER toolbox sections are the ArcGIS trap
Buffer / intersect / clip / reproject / resample / band math are either pipeline stages the system already performs (S8, S10, S12), backend-only computation by the architecture's hard rule, or generic GIS verbs with no evidence semantics. Exposing S8/S10 as manual tools tells the operator the system is *not* handling them, which reverses the thesis. The Toolbox exposes **intent-level operations only** (§3.7). The single later exception: **custom spectral index** as an operation, because it yields a product with a legend and a claim.

### 2.5 LOCKED: Project · Investigation · Mission — what each is, and whether all three are needed

**Yes, all three — but only because Mission stops being a container.** With three containers the nouns collide; with one container, one unit of work and one standing order, each answers a different question.

| Noun | The question it answers | Lifetime | Contains | Belongs to |
|---|---|---|---|---|
| **Project** | *Where and about what am I working?* | Long-lived; months to years | Data (observations attached to the area), Investigations, Reports, Versions, Missions | — (top level) |
| **Investigation** | *What is the answer to this question, and how was it reached?* | Days to weeks; can be reopened | Scene slots, timeline pair, runs, evidence graph, claims, canvas, versions, report | exactly one Project |
| **Mission** | *Keep watching this and tell me when it changes* | Standing; until archived | A **schedule** (cadence), a **template** (an investigation version to re-execute), an **alert rule** (metric + threshold), the run log it produces | exactly one Project; references one Investigation version |

What this changes from today:

- **Mission is no longer "a saved investigation".** `useSaveAsMission` becomes **Monitor this** and requires a cadence. Its existing schema already carries `nextRunAt`, `lastRunAt`, `openAlertCount`, `status: active | monitoring | alert | archived` — those are schedule fields, so the rename is honest about what the record already is. `analysisKind` is replaced by `templateVersionId` (what to re-run) once versions exist; until then it stays.
- **Globe markers are Project markers.** A project with an active mission carries a badge; a mission in alert carries the alert pulse. Today's marker LOD rules (alert first, archived last) map onto this unchanged.
- **Continuous execution of missions is still later-tier scope** (`design_report.md`, PDF §44). Nothing here builds the scheduler; it builds the *record* so that when the scheduler lands, the queue is already a place (`navigation.ts` revival condition).
- **No "Unfiled" bucket.** An investigation always has a project. The Investigate action on Mission Command gets one field: a project picker defaulting to the existing project whose area contains the selected scenes, else "New project · *AOI name*". One choice, one right default.

**Where each is reached in the UI:**

```
RAIL
├── Mission Command  (/)                the globe. Left panel: imagery catalogue (unchanged) +
│                                       RECENT PROJECTS (replaces the missions list) + an ALERTS strip
│                                       (missions in `alert`). Click a project marker → fly + open it.
├── Projects         (/projects)        the shelf. Search, sort by last activity. Replaces the
│                                       "Investigation" rail entry — the investigation index becomes a
│                                       tab inside a project (below) and a "recent" list on Mission
│                                       Command. Rail stays at four entries.
├── Evidence Audit   (/evidence)        unchanged; rows link into investigations.
└── Model Observatory (/models)         unchanged.

PROJECT PAGE  (/projects/:id)           the catalogue view from proposal #13
├── Data            observations attached to this area (a filtered view of the global catalogue,
│                   NOT a second corpus), derived products across its investigations, vectors
├── Investigations  the list; "New investigation" here pre-fills the project
├── Reports         every generated report, by investigation and version
├── Versions        every saved version across investigations, with Compare
└── Missions        the standing orders on this project; alert state; "Monitor this" lands here

INVESTIGATION  (/investigation/:id)     unchanged route
└── header breadcrumb: Project › Investigation · v3   [Save version] [Compare] [Monitor this] [Report]
```

Old work is therefore reached three ways: **spatially** (globe marker → project), **by shelf** (Projects rail → project → Investigations tab), or **by claim** (Evidence Audit → investigation). A mission is only ever reached *through* its project or the alert strip, because it is not a place of its own.

### 2.6 Version compare is computed, not stored
A pure `diffVersions(a, b)` in `features/investigation/lib/version-diff.ts`, same shape as `agreement.ts`. The backend stores snapshots; the client diffs; the agent narrates the same output.

### 2.7 History is a command log, not a second event system
Every analytical action already dispatches through the command bus. History subscribes to dispatches, filters to the analytical subset, persists those. Agent actions land in the same log because the agent uses the same bus.

---

## 3. The build, in the order that produces the product first

Order rationale (from the review, adopted): **Canvas + Versioning are the differentiators.** A project page, a layers panel and a nicer toolbox are useful and do not make AERIS special. So the sequence follows the one interaction that does —

```
"Find new construction."  →  plan appears as a graph  →  runs node by node  →  click Change Detection
→  threshold 0.35  →  edit to 0.45  →  re-run from here, downstream re-executes  →  save as v2
→  compare v1 ↔ v2: threshold moved, area 39.7 → 41.2 ha, confidence 87 → 92 %
```

— and everything not on that path comes after it.

Rules every phase obeys (all already in `architecture-context.md`): constants are catalogues and the wire carries ids; every affordance is a command; server state in the query cache, view state in the store; third-party renderers behind an adapter folder; mock first through the one seam.

### PHASE A — The analysis contract (no UI)

**`lib/constants/analysis-operations.ts`** — `AnalysisOperation` gains:

```ts
/** Tunable inputs. A Zod object: one schema renders the form, validates a re-run, and is emitted as
 *  JSON Schema to the agent. z.object({}) for operations with no knobs. */
parameters: z.ZodObject<z.ZodRawShape>;
defaultParameters: Record<string, ParameterValue>;
/** Search vocabulary — what an operator might type when they want this. */
keywords: readonly string[];
/** Intent-level grouping for the Toolbox and the palette (§3.7). */
group: OperationGroup;
```

Parameter kinds are a closed set in `lib/constants/parameters.ts` (`number-range`, `enum`, `boolean`, `layer-ref`, `scene-ref`, `band-list`, `text`) so **one form renderer covers every operation** — the overlay catalogue's "one branch per shape, never one per product" rule applied again. React Hook Form + Zod are already in the stack; this is their first real use.

**`analysis.schema.ts`** — plan steps and trace steps converge on one shape. This is the review's addition and it is the load-bearing one:

```ts
export const nodeRefSchema = z.object({
  kind: z.enum(["scene", "region", "layer", "figure", "claim", "step"]),
  id: z.string().min(1),
});

export const analysisStepSchema = z.object({
  id: z.string().min(1),
  /** Catalogue operation, when the step corresponds to one. Null for infrastructure stages (S1–S11). */
  operationId: z.string().nullable(),
  stageCode: pipelineStageCodeSchema,
  inputs: z.array(nodeRefSchema),
  /** Resolved values the step ran (or will run) with — never the request, always the truth. */
  parameters: z.record(z.string(), parameterValueSchema),
  outputs: z.array(nodeRefSchema),
  model: z.object({ id: z.string(), version: z.string() }).nullable(),
  /** Why this step / this model, authored by the planner. Catalogue rationale is the fallback. */
  rationale: z.string().nullable(),
  /** Step ids this step consumes. THE GRAPH. Without it the trace is a list; with it, a canvas. */
  dependsOn: z.array(z.string()),
});

// plan step = analysisStep + { isEnabled }
// trace step = analysisStep + { state, durationMs, detail, artefactLayerId }
```

`dependsOn` is carried explicitly rather than derived from `inputs` because two steps can share an input without one depending on the other (S12 and S14 both read S10's output and run in parallel), and because a re-run needs the closure "everything downstream of this node" to be a graph walk, not an inference.

`analysisRunRequestSchema` gains `parameterOverrides: Record<stepId, Record<param, value>> | null` and `rerunFromStepId: string | null`. A re-run is the same run request with two more fields — one pipeline, three ways in.

`figure-ready` loses its two `z.any()` fields; `legend` and `renderSpec` get real schemas now because canvas figure nodes will draw from them.

**`mock/streams/analysis-stream.ts`** emits a non-trivial DAG (T0 + T1 → S9 → S13 → S15 → claims; S12 and S14 as parallel branches) with real `parameters` (threshold 0.35, method, resolution). `SESSION_STORAGE_VERSION` bumps.

**Done when:** `tsc` clean; the mock↔schema self-test asserts every `outputs`/`dependsOn` ref resolves and the graph is acyclic.

### PHASE B — Analysis Canvas + node inspection

**`features/investigation/lib/workflow-graph.ts`** — pure: `buildWorkflowGraph({ steps, layersById, claimsById, sceneSlots, regions }) → { nodes, edges }`. Node kinds are a closed set in `lib/constants/workflow.ts` (`scene`, `region`, `operation`, `layer`, `figure`, `claim`). Layout is computed (dagre), never hand-placed — the operator cannot drag nodes into meaningless positions and the agent never reasons about coordinates.

**`components/sharedUI/functionalComponent/workflowCanvas/`** — `@xyflow/react` behind an adapter folder with the Cesium rule: *no file outside this folder imports `@xyflow/*`*. Node components are dumb, receive a typed descriptor, dispatch commands on click. Swap the library later and the blast radius is the folder.

**`AnalysisCanvas`** — one component, three states over one `run`/`plan`:

| State | Source | Editable |
|---|---|---|
| **Planned** | `activePlan` | strike steps (exists), edit parameters (opens the node inspector in edit mode) |
| **Running** | `runs.at(-1)` while `isRunning` | no — nodes light up as `trace-step` frames arrive, layer/claim nodes attach as `layer-ready`/`claim` frames arrive. The canvas *is* the live trace |
| **Recorded** | any past run | inspect, re-run from a node (Phase C) |

Freeform edge editing is out of scope by design: the AI proposes the graph, the human inspects, strikes and tunes, the AI executes. A canvas the human can wire arbitrarily is one the backend must validate arbitrarily — the ModelBuilder surface §15 warns against.

Placement: bottom zone. Collapsed = pip strip (exists) → expanded = row list *or* canvas (toggle) → full-height with panels collapsed. Store: `traceView: "rows" | "canvas"`, `selectedNodeId`. The running node shimmers like the spine pip and the satellite arc — one motion language.

**`StepInspector`** — click a node or a row → panel in the free column, opposite corner to `FeatureInspector`:

| Section | Source |
|---|---|
| Inputs | `step.inputs` resolved; each clickable (focus scene, solo layer, select upstream node) |
| Method / model | `getModel(step.model.id)` + `step.rationale ?? selectionRationale` |
| Parameters | `step.parameters` through the shared parameter renderer — read-only until **Edit** |
| Outputs | `step.outputs` → layer rows (peek), figures, claims (spotlight) |
| Runtime | `durationMs`, state |
| Evidence | claims whose `traceStepId === step.id` — one reverse scan per open, same trade as `inspection` in `InvestigationScreen` |
| Actions | View output · **Edit → Re-run** (Phase C) |

Commands: `investigation.toggleCanvas`, `investigation.selectNode { nodeId }`, `investigation.focusNode { nodeId }`.

**Done when:** a mock run renders as a DAG with parallel branches, lights up live, and clicking Change Detection shows `threshold: 0.35` read from the wire.

### PHASE C — Edit parameter → re-run → downstream re-executes

`investigation.rerunStep { stepId, parameterOverrides }` → `ask(run.query, { operationId, parameterOverrides, rerunFromStepId })`. A **new run** appended to `runs[]` — the previous answer stays reopenable, so the re-run is its own audit trail.

The canvas shows the re-run as the same graph with the edited node and its `dependsOn` closure marked *re-executing*; upstream nodes are marked *reused* — the backend states which in the trace (`state: "skipped"` with `detail: "reused from run …"`), the frontend never assumes caching.

"Change threshold to 0.45" typed into the composer is the same command reached by the agent: the planner emits a `ui-command` frame (already in the stream schema) carrying `investigation.rerunStep`. No new agent code.

**Done when:** editing a threshold produces a second run, the answer panel shows both, the canvas marks reused vs re-executed nodes from wire state.

### PHASE D — Version snapshots + compare

```ts
investigationVersionSchema {
  id, label, createdAt, actor: "operator" | "agent", parentVersionId: string | null,
  snapshot: {
    sceneSlots, timelinePair,
    steps: AnalysisStep[],            // the recorded graph, parameters and model versions included
    resultSummary: { claimMetrics, confidence },
    layerIds, traceId,
  }
}
```

- **Explicit saves only** — `investigation.saveVersion { label }`. A version is a decision that this state is worth a name, never a side effect of running.
- `features/investigation/lib/version-diff.ts` — pure `diffVersions(a, b) → DiffSection[]` over inputs, workflow (steps added/removed, by `operationId`), parameters (per step, before → after), models (id@version), result (metrics), confidence. Rendered by `VersionCompareSheet`; narrated by the agent through the same function.
- `investigation.compareVersions { a, b }`, `investigation.restoreVersion { id }` — restore puts back *inputs and parameters* and leaves the operator to run; it never fabricates results.
- Header: `v3` badge → version list → Compare. `parentVersionId` makes branching a data fact now and a feature later (P3).

**Done when:** v1 → edit → v2 → Compare shows exactly the threshold, the area and the confidence deltas, nothing else.

### PHASE E — Project (§2.5) + the catalogue view

- `features/project/` — schema, service, hook, `ProjectIndexScreen`, `ProjectScreen` with the five tabs. Every tab is an existing query with a `projectId` filter; **no second corpus in the mock.**
- `investigation.projectId` (required), `mission.projectId`, `mission.templateVersionId`. Breadcrumb in `InvestigationHeader`. Investigate action gets the project picker with the containing-project default.
- Mission Command left panel: missions list → **Recent projects** + **Alerts** strip. Globe markers keyed by project. `useSaveAsMission` → **Monitor this** with a cadence field (record only; no scheduler).
- Rail: `Investigation` → `Projects`. `ROUTES.PROJECTS`, `buildRoute.project(id)`. The `/investigation` index route stays reachable (palette, links) but leaves the rail.
- Commands: `project.open`, `project.create`, `investigation.moveToProject`, `mission.create`.

### PHASE F — History + polish

- **History:** `subscribeToDispatches` on the registry; `recordsHistory: true` on the analytical commands (`ask`, `runOperation`, `rerunStep`, scene role assignment, `setTimelinePair`, `completeDraw`, `saveVersion`, `setCloudCeiling`, lens open/close). `use-investigation-history.ts` turns each into `InvestigationEvent { at, actor, commandId, summary, params }` (summaries templated per command in the catalogue — "Changed detection threshold 0.30 → 0.35"), `POST`s it, query cache holds the list. Shown in the right panel's history area grouped by day, each row jumping to its run / node / layer.
- **Layers tab** (proposal #3, audit item 11): INPUTS · LAYERS · TOOLBOX tabs (icon-only under a width threshold rather than abbreviated labels); BASE / FINDINGS / MASKS / REFERENCE sections with the 🔒/✎ rule; reorder by drag (`@dnd-kit`) as view state consumed by the single stage writer; basemap catalogue + switcher; metadata drawer; annotate.
- **Palette + Toolbox** (§3.7).
- **Evidence tab** in the right panel: per-claim chain metric → evidence → layer/feature → figure → model → step → source scenes, every link live. **Timeline event annotations** if the wire carries them.

### 3.7 The Toolbox, regrouped as intent (applies in Phase F; the `group` field lands in Phase A)

```
ANALYSIS     Change detection · Built-up detection · Vegetation analysis · Water detection ·
             Object detection · Land-cover segmentation · Burn severity
TEMPORAL     Compare observations (= the timeline pair) · Trend analysis (N-date series; the
             acquisitions[] contract already supports it) · Change explanation (CHANGE_VQA intent)
MULTIMODAL   SAR backscatter · Cross-modal agreement (lens)
AI           Ask scene · Describe scene · Ground object (GROUND intent) · Ask region (draw → ask)
MEASURE      Area · Distance · Bearing (the draw tools, listed so they can be found)
3D           — not listed. Reconstruct site / point cloud / 3D scene have no backend capability in
             the PDF. Rows appear only when the catalogue declares an operation the pipeline can run;
             a Toolbox that advertises capabilities that do not exist teaches the operator to
             distrust the rows that do.
```

"Vegetation analysis" and "Water detection" are the existing index operations (NDVI/NBR, NDWI/MNDWI) presented by intent with the index as a parameter, not five sibling rows named after formulas. The overlay browser keeps the formula-level detail.

**Palette:** `CommandPalette` reads `ANALYSIS_OPERATIONS` alongside the registry and dispatches `investigation.runOperation { operationId }` — parameterised at the source, so the hidden-when-parameterised rule holds. With `keywords`, "vegetation loss" surfaces Vegetation analysis, Change detection and Burn severity. The same list is the agent's tool list already.

---

## 4. Priorities

| Phase | Item | Proposal said | Now |
|---|---|---|---|
| **A** | Analysis contract: parameters, inputs/outputs, `dependsOn`, overrides | *(absent)* | **P0** — everything reads from it |
| **B** | Analysis Canvas + node inspector | P0 / P1 | **P0** — ship together; a canvas without inspectable nodes is a diagram |
| **C** | Edit → re-run → downstream re-executes | *(inside 7)* | **P0** — the interaction that is the product |
| **D** | Versions + compare | P1 / P2 | **P1** — the second half of the differentiator |
| **E** | Project + Mission redefinition + catalogue view | P0 / P2 | **P1** — the *decision* is locked now (§2.5) so the contract can carry `projectId` from Phase A; the pages come after D |
| **F** | History, Layers tab + reorder + basemap, palette ops, Evidence tab, timeline events | P0 / P1 | **P2** — useful, not special |
| — | Branching hypotheses | P2 | **P3** — `parentVersionId` makes it a data fact now; the UI waits for a case |
| ❌ | Vector/raster toolbox, rename/remove evidence layers, chat-as-default, ribbon, symbology, geometry editing, 3D rows without a backend | P1 / P3 | not built |

---

## 5. Decisions — locked, and the two that remain

**Locked by this document (v2):**
1. Project = container · Investigation = unit of work · Mission = standing order (schedule + template + alert rule) on a project. §2.5.
2. Evidence layers 🔒 (hide / solo / opacity / focus / metadata / annotate); operator layers ✎ (all of that + rename / remove). §2.3.
3. Versions are explicit saves; compare is a client-side pure diff. §3 D.
4. Canvas is a bottom-zone view over the same run data; no freeform wiring. §2.2, §3 B.
5. Toolbox is intent-level; no VECTOR/RASTER; no rows for capabilities the backend cannot run. §3.7.

**Still the product owner's:**
1. Graph renderer — `@xyflow/react` behind an adapter (recommended) or hand-rolled SVG + dagre.
2. Reorder — `@dnd-kit` (recommended) or pointer-sort by hand.

---

## 6. Message for the backend developer

Additive only; nothing existing changes shape.

| Where | Addition |
|---|---|
| plan steps, `trace-step` frames | the `AnalysisStep` shape: `operationId`, `parameters` (resolved), `inputs[]`, `outputs[]` as `{ kind, id }`, `model { id, version }`, `rationale`, **`dependsOn[]`** |
| `POST /investigations/:id/runs` | `parameterOverrides`, `rerunFromStepId`; steps upstream of the re-run point come back `state: "skipped"` with `detail` naming the run they were reused from |
| `figure-ready` | typed `legend` and `renderSpec` |
| `investigation` | `projectId` (required), `events[]` (optional timeline annotations), `layerNotes` |
| `mission` | `projectId`, `templateVersionId`, `cadence`, `alertRule` — record only; the scheduler is later-tier |
| new | `GET/POST /investigations/:id/versions` — server stores the snapshot the client sends; diff is client-side |
| new | `GET/POST /investigations/:id/history` — append-only `{ at, actor, commandId, params, summary }` |
| new | `GET/POST /projects`, `GET /projects/:id`; every existing list endpoint accepts `projectId` |
| `GET /operations` (optional) | if the backend prefers to own parameter schemas, return JSON Schema per operation; the frontend catalogue becomes a 5-minute-stale fetch and the rendering path is identical |

---

## 7. What this turns the product into

After Phases A–D an operator can: type a question → watch the AI's workflow appear as a graph and light up node by node → click any node and read the threshold it used → change it and re-run from that node, with downstream steps re-executing and upstream ones visibly reused → see the new answer beside the old one → save the state as `v2` → compare `v1 ↔ v2` and see exactly which input, parameter or model version moved the number. After E, that investigation lives in a project the operator can find again from the globe, the shelf or a claim, and can hand to a mission to keep watching. And the agent does every one of those steps through the same commands, with every step landing in the same history.

That is the partial shift from a desktop GIS: not "AERIS does what ArcGIS does" but "the analytical part of the job — choosing, sequencing, parameterising, checking and versioning an analysis — happens here, inspectably, with the map as the evidence surface rather than the tool surface."
