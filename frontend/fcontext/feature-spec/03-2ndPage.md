# Page 2 — The Investigation Workspace

> End-to-end ideation. **Nothing here is built yet.** This document exists to be argued with and
> approved before a single file is created.

Sources reconciled: `context/FirstIdea.txt` §6, §22, §23, §24, §25 · `context/idea.md` (three analysis
pillars, evidence-first pipeline) · `SatqueryAI.pdf` §15.1 (the 20-stage pipeline), §19.2 (routing
examples), §20 (evidence-grounded answers), §21 (provenance), §25.3 (SIH tier) · `design_report.md` §1–2
(aesthetic + wow factors) · `fcontext/architecture-context.md` and `fcontext/memory.md`.

---

## 0. The one-sentence thesis

> **Page 1 asks "where in the world?". Page 2 answers "what happened here, how do you know, and show me."**

The product owner's framing governs every decision below:

> *"The core idea revolves around making you feel how the changes have turned instead of just showing
> you how the changes have turned."*

So the design test for every feature here is not *does it display the result* but **does it make the
operator feel the change, and can they immediately verify it was real.** Anything that fails both is
chrome, and gets cut.

---

## 1. What this page actually is

The source documents describe Page 2 as "the primary analysis interface. Every investigation happens
here." That phrase has a structural consequence that is easy to miss:

**Pages 3 and 4 are not separate applications. They are modes of this one.**

| Page | What it really is |
|---|---|
| 2 — Investigation Workspace | Scene + evidence layers + answer + trace. The substrate. |
| 3 — Cross-Modal Lab | The same workspace, comparator bound to *optical vs SAR* instead of *T0 vs T1*, plus a fusion layer in the stack. |
| 4 — Temporal Change Explorer | The same workspace, comparator bound to *T0 vs T1*, plus a timeline scrubber over an n-date stack. |
| 5 — Evidence Explorer | The same evidence graph without the scene — a reader view over what the workspace produced. |

This is not a shortcut. `architecture-context.md` states it as a hard rule: *"no 2 pages should write the
same u.i code in two diff files for that same thing — I am very strict with this."* If the scene viewer,
the layer stack, the split comparator, the claim cards and the trace spine get built three times, the
project has three times the bugs and three times the drift.

**So Page 2 is built as a configurable workspace, and pages 3 and 4 are routes that mount it with a
different `WorkspaceMode` and a different comparator binding.** Separate URLs, separate entry points,
separate framing — one implementation. This single decision is most of the "build it to scale" answer.

---

## 2. The layout

Same three-zone grammar as Page 1 — deliberately, so the operator never has to relearn where things
live — but the *character* changes completely. Page 1 is orbital, ambient, calm. Page 2 is close, dense
and instrument-like. Chrome thins out; the scene becomes the hero.

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ ◂ AERIS   Urban Expansion — Bhiwandi Corridor          ⌘K    ⏻ Present   [Report] │
│ T0 2024-01-14 S2 optical · T1 2026-08-02 S2 optical · +SAR      trace 7f3a91 ⧉    │
├──────────────────┬────────────────────────────────────────────┬───────────────────┤
│ INPUTS           │                                            │ AERIS             │
│  ▣ T0  Sentinel-2│                                            │                   │
│  ▣ T1  Sentinel-2│              SCENE VIEWER                  │ ▸ Built-up area   │
│  ▢ SAR Sentinel-1│      ┌─────────────╫──────────────┐        │   increased       │
│  + add scene     │      │     T0      ║      T1      │        │                   │
│                  │      │             ║              │        │   +18.4 %         │
│ EVIDENCE LAYERS  │      │             ║              │        │   14.2 ha         │
│  ● Change mask   │      └─────────────╫──────────────┘        │   north-east      │
│    ChangeFormer  │             ▲ drag handle                  │   ███████░ 91 %   │
│    conf 91%      │                                            │                   │
│  ● New buildings │  [▢ draw] [⟷ split] [⛰ volumetric] [◉ spot]│  ▪ change-mask    │
│    DINO+SAM 87%  │                                            │  ▪ building-poly  │
│  ○ NDVI          │  ◂──── T0 ═════════●═══════════ T1 ────▸   │  ▪ area-stats     │
│  ○ Cloud mask    │        temporal playbar                    │                   │
│                  │                                            │ [ Investigate → ] │
│                  │                                            │ ask anything…  🎙 │
├──────────────────┴────────────────────────────────────────────┴───────────────────┤
│ TRACE  S1●─S3●─S4●─S6●─S7●─S8●─S9●─S11●─S13◉─S15○─S16○─S18○─S19○      1.84 s  ⌄  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Zone by zone

**Header — the investigation identity strip.** Editable investigation name, AOI name, and the *scene
slot chips*: T0, T1, SAR, each showing date · platform · modality. Clicking a chip focuses that scene.
On the right: `Present` (hides all chrome for the demo moment) and `Report`. Below, in mono, the **trace
ID with a copy affordance** — small, permanent, and the single most credible pixel on the page. It says:
everything you are looking at is re-executable.

**Left — Inputs & Evidence Layers.** Two collapsible sections, reusing `SectionHeader` with `onToggle`
exactly as Page 1's panel now does.

The layer stack is where most products become a generic GIS table of contents. **We refuse that.** Every
row is an *evidence layer* and carries provenance on its face: name, the model that produced it with
version, its confidence, opacity, visibility, solo. Hovering a row highlights the claim it supports. It
is a table of contents for the argument, not for the pixels.

**Centre — the scene viewer.** Full-bleed, no border; panels float over it with backdrop blur so the
operator never loses geographic context (`design_report.md` §2.4). One floating tool cluster: draw
region · split comparator · volumetric toggle · evidence spotlight. Beneath it, the temporal playbar.

**Right — AERIS.** Not a chat log. An **answer surface**: the claim, its metrics as large mono count-up
numbers, its confidence verdict, its evidence chips, and the `Investigate` action. Prior turns collapse
to one line each. A deliberate departure from Page 1's transcript, because here the current answer *is*
the workspace's subject — burying it in scrollback would be wrong.

**Bottom — the execution spine.** One line by default (stage pips + total latency), expandable to the
full S1–S20 walk. Detail in §4.3, because it is the highest-credibility feature on this page.

---

## 3. Aesthetic direction

Inherits `globals.css` wholesale — no new colours, no new radii. What changes is *density and restraint*.

- **The imagery is the only photographic thing on screen.** Every AERIS-generated pixel uses the palette.
  That contrast is what makes overlays read as *analysis* rather than as more picture.
- **Colour carries meaning, strictly.** Teal = gain / new / detected. Amber = loss / removal / caution.
  Red stays reserved for alerts alone so it never devalues. **No rainbow ramps** — they are
  colour-blind-hostile and read instantly as amateur GIS. Continuous surfaces (NDVI, confidence) use a
  perceptually uniform ramp declared once in `lib/constants/layers.ts`.
- **Numbers are typographic events.** JetBrains Mono, `tabular-nums`, counting up to their value on
  arrival. A hectare figure that animates reads as computed; one that simply appears reads as asserted.
- **Chrome recedes as the scene loads.** Panels start opaque and settle to glass once imagery is up, so
  the first impression is the place, not the interface.
- **Motion has a budget.** One thing moves at a time. Reduced-motion collapses every cinematic move to a
  150 ms fade — already wired through `hooks/use-prefers-reduced-motion.ts`.

### Signature moments (the ones a judge will remember)

1. **The descent.** Page 1 → Page 2 is one uninterrupted camera flight from orbit to the AOI. No cut, no
   loader, no cross-fade. §6 explains how.
2. **The target lock.** As the camera settles, corner brackets draw themselves around the AOI, then
   fade. Half a second. Costs nothing. Establishes "this is an instrument".
3. **The scan-in.** T1 imagery does not pop in — it **wipes** in like a satellite pass, by sweeping
   `scene.splitPosition` on the newly added layer from 0 → 1. It reuses the comparator machinery rather
   than adding any.
4. **The bloom.** Change polygons arrive staggered by magnitude — largest first, ~40 ms apart. The eye is
   led to the most significant change without a single arrow or label.
5. **The rise.** Volumetric mode extrudes each change polygon to a height proportional to its magnitude,
   animated from zero. At a low sun angle they cast real shadows. The most literal possible answer to
   *"make the change felt"*.

---

## 4. Capabilities — and which are wow

Every item traces to a source document. The tier column is the PDF's own feasibility tiering (§25); per
`.claude/CLAUDE.md` we build MVP + SIH + ADV, skip FUT — **except voice, which we build.**

### 4.1 The comparator — "feel the change" made mechanical

| | |
|---|---|
| Source | FirstIdea §8 (before/after slider), PDF #10, #21 |
| Tier | SIH |
| Cesium | `ImageryLayer.splitDirection` + `scene.splitPosition` — native, two properties |

Drag a handle; T0 becomes T1 under the cursor. `memory.md` already records why this alone justified
staying on one engine: it is the most direct expression of felt change available, and MapLibre has no
equivalent.

**Three enhancements that take it past stock:**

- **Magnetic snap.** The handle snaps to the screen-x of the highest-magnitude change polygon. The
  operator drags vaguely; the system lands them exactly on the thing that matters.
- **It is a command, so AERIS can drive it.** `investigation.setSplitPosition` is registered on the
  command bus. When the assistant says *"here is where it changed"*, **the slider sweeps itself** while
  the sentence streams. Nobody else demos that.
- **Auto-play.** The temporal playbar loops T0↔T1 with an eased dissolve while the camera slowly orbits.
  In `Present` mode, with no chrome, that is the money shot.

### 4.2 Evidence spotlight — the product thesis, visible

| | |
|---|---|
| Source | PDF §20 ("every claim traceable to pixels"), Phase 6 gate, FirstIdea §24 |
| Tier | SIH |

Hover any claim in the answer panel → **the entire scene dims except the geometry that supports it**, and
a reticle settles on it. Click → the camera frames it.

Implementation is cheap and clean: animate `imageryLayer.brightness` down to ~0.35 and raise the
supporting polygons' alpha. No HTML scrim fighting a 3D canvas, no masking geometry.

Why it matters more than it looks: the PDF's Phase 6 gate is literally *"every claim in a session is
clickable to pixels."* This is that gate, rendered. It converts "evidence-first" from a slide into
something a judge can do with their own mouse.

### 4.3 The execution spine — trace as instrument, not decoration

| | |
|---|---|
| Source | PDF §15.1 (S1–S20), §21.1 (auditable trace), §21.2 (intermediate outputs retained as addressable artefacts) |
| Tier | MVP for the trace, SIH for artefact peek |

Most systems render a pipeline trace as a checklist. Ours is a **spine**: a thin rail with a node per
active stage showing stage code, state and latency. The running node carries a travelling shimmer — the
same GLSL technique already shipped in `satellite-arc-layer.ts`, applied to a different surface, so the
visual language stays consistent across pages for free.

**The feature that makes it an instrument: every node is clickable, and clicking it loads that stage's
intermediate artefact into the viewer as a temporary layer.**

- S7 cloud handling → the cloud mask, over the scene
- S9 co-registration → the residual field, plus the numeric residual
- S12 indices → the NDVI / NDBI map
- S13 specialist analysis → raw model output, before validation

PDF §21.2 *already requires* those artefacts to be retained as addressable URIs. **We are only asking the
backend to hand us the URI it is already storing.** Near-zero backend cost, and the effect on a technical
evaluator is hard to overstate: *click any step, see exactly what the machine saw at that moment.*
Highest credibility per engineering hour on this page.

### 4.4 Ask this region

| | |
|---|---|
| Source | FirstIdea §22, PDF #22 + #23 |
| Tier | SIH |

Draw a rectangle or polygon on the scene. A popover anchors to the shape with 3–4 suggested questions
**scoped to that geometry** ("What changed here?", "Is this construction?", "How much vegetation was
lost?"), plus a free composer. The geometry rides along as query context; the backend crops to it.

Suggestions are backend-driven, exactly like Page 1's — what is worth asking about a polygon depends on
what imagery covers it. Cesium provides the drawing (`ScreenSpaceEventHandler` + a `CallbackProperty`
polygon), the picking, and the geometry in real coordinates.

### 4.5 Autonomous investigation — the agentic wow

| | |
|---|---|
| Source | FirstIdea §23, PDF #24 |
| Tier | ADV |

Every answer carries an `Investigate` action. Pressing it does **not** just fire another query. It:

1. Shows the **plan first** — an editable checklist of the steps AERIS intends to run and the models each
   will use. The operator can strike a step out before it runs.
2. Executes. As each step completes the spine lights up, layers appear in the stack, **and the camera
   moves on its own** to whatever the current step is about.
3. Ends with a synthesised answer whose every claim links back into the graph built along the way.

**The architectural payoff, and why this is cheap:** the macro is not a special code path. It is a
sequence of `dispatchCommand()` calls against the same bus a human's clicks go through. The agent
literally presses the same buttons. That is exactly what `lib/command-bus` was built for
(`architecture-context.md` — "The UI Command Bus"), and it means the autonomous mode cannot drift from
the manual mode, because there is only one mode.

### 4.6 Volumetric change (2.5D)

| | |
|---|---|
| Source | The engine rationale ("cesium has 2.5D compatibility"), backend contract item 6 in `memory.md` |
| Tier | ADV |

Change polygons extrude by magnitude. A flat mask says *"18.4%"*. A skyline of extruded blocks with
shadows *makes you feel* 18.4%.

**Known constraint to design around (verify at build time):** Cesium's terrain-draped classification
(`ClassificationType.TERRAIN`) and `extrudedHeight` are mutually exclusive — a classified ground
primitive cannot be extruded. So `flat ⇄ volumetric` is not a property toggle; it swaps between **two
representations** of the same evidence polygon. The layer registry (§5.2) must model that as a
`renderMode` on the descriptor, not as a boolean on a primitive.

### 4.7 Spatial confidence — where the model is unsure

| | |
|---|---|
| Source | PDF §20 (the low-confidence UX), FirstIdea §25 |
| Tier | SIH |

A percentage badge tells you the model's confidence. It does not tell you *where* it is unconfident. A
confidence render mode hatches the low-confidence regions of a mask.

And the state everyone else skips: **insufficient evidence**. When the backend declines to assert, the
answer panel does not show 0%. It shows the refusal, the reason, and **actions** — *Use SAR instead* ·
*Request newer imagery* · *Narrow the region*. Page 1 already establishes that confidence is
`number | null` and null renders as "not asserted"; this page promotes it to a first-class card. Honest
refusal in front of judges reads as engineering maturity, not as a gap.

### 4.8 Report generation

| | |
|---|---|
| Source | FirstIdea §28, PDF #38 + #40 |
| Tier | SIH |

Not a download button. A drawer where the report **assembles in front of you** — sections appearing as
the generator emits them, figures dropping in from the actual layers on screen, the trace ID stamped at
the bottom. Then PDF · JSON · GeoJSON.

The demo line writes itself: *"and every number in this PDF walks back to pixels."*

### 4.9 Voice

| | |
|---|---|
| Source | FirstIdea §26, PDF #2/#32 (FUT — but explicitly in scope per `.claude/CLAUDE.md`) |
| Tier | FUT, built anyway |

Voice needs **no new UI on this page at all**. It is a thin adapter: ASR → intent → `dispatchCommand()`.
The workspace's registered command set *is* the vocabulary:

| Spoken | Command |
|---|---|
| "Show me the change" | `investigation.toggleLayer` |
| "Sweep" / "Compare" | `investigation.sweepSplit` |
| "Zoom to the biggest change" | `investigation.focusEvidence` (magnitude-ranked) |
| "Why?" | `investigation.spotlightClaim` |
| "Use the SAR" | `investigation.setComparator` |
| "Investigate" | `investigation.runAutonomous` |
| "Generate a report" | `investigation.openReport` |

The microphone is already rendered and explicitly disabled with a tooltip on Page 1 — same component,
same treatment, until the ASR layer lands.

### 4.10 Wow, ranked by return

Judges see five minutes. These four are the demo spine; everything else is depth behind them.

| # | Feature | Demo impact | Cost | Verdict |
|---|---|---|---|---|
| 1 | Cinematic descent, globe → AOI | Very high | Medium (one-viewer refactor) | **Spine** |
| 2 | Split comparator + AERIS driving it | Very high | Low (native Cesium) | **Spine** |
| 3 | Evidence spotlight (claim → pixels) | Very high | Low | **Spine** |
| 4 | Trace spine + artefact peek | High; with technical judges, highest | Low–medium | **Spine** |
| 5 | Volumetric change | High | Medium | Strong add |
| 6 | Autonomous investigation | High | Medium | Strong add |
| 7 | Ask this region | Medium–high | Medium (draw tooling) | Core utility |
| 8 | Insufficient-evidence card | Medium, disproportionate credibility | Very low | Do it early |
| 9 | Report drawer | Medium–high | Medium | Closes the story |
| 10 | Present mode | Medium | Very low | Do it early |

---

## 5. How it is built to scale

### 5.1 One Cesium viewer, shared across routes — the central decision

The largest architectural change this page requires, and what actually cashes the cheque written when we
chose one engine.

**The problem.** In the App Router, navigating from `/` to `/investigation/[id]` unmounts Page 1's tree.
If the viewer lives inside `features/missionCommand/`, it dies mid-flight. The descent then degrades to
freeze → boot a second Cesium context (~1.5–2 s and a second WebGL context) → fade in. That is exactly the
*simulated* continuity `memory.md` rejected when it declined the MapLibre split. It would be absurd to
reintroduce it here by accident.

**The fix.** A **route group** whose layout owns one viewer for its whole lifetime:

```
app/(geospatial)/layout.tsx                                  ← owns the single Cesium stage
app/(geospatial)/page.tsx                                    ← Mission Command   (URL stays "/")
app/(geospatial)/investigation/[investigationId]/page.tsx    ← Investigation Workspace
```

Route groups do not appear in the URL, so `/` and `/investigation/:id` are unchanged. Each page
**attaches and detaches its own layer sets** against the shared stage; the camera never stops.

Scope it deliberately: only geospatial surfaces (2, 3, 4 and the globe) join the group. The Model
Observatory must not pay for a WebGL context it never uses.

**Architecture amendment this requires — flagged, not smuggled.** `architecture-context.md` currently
says *"No file outside `features/missionCommand/components/globe/` may import `cesium`."* The boundary
**moves**; it does not weaken:

> No file outside `components/sharedUI/functionalComponent/geoStage/` may import `cesium`.

The globe's marker and arc layers relocate there as *layer modules registered against the stage*. Both
`GlobeViewerHandle` and the new `SceneViewerHandle` are satisfied by that one owner. If this is approved,
`architecture-context.md` and `memory.md` are updated in the same change.

**Honest cost:** this is a real refactor of working, reviewed code. It is worth it because it is the only
way to get the descent, and because it is the prerequisite for pages 3 and 4 being nearly free.

### 5.2 Layers are data, not components

The number of overlay types on this page grows forever — change masks, buildings, roads, vehicles, water,
NDVI, NDWI, NDBI, NBR, SAR backscatter, fusion products, cloud masks, registration residuals, confidence
fields. If each is a React component, the codebase grows linearly with the science.

So a layer is a **descriptor**:

```ts
interface EvidenceLayerDescriptor {
  id: string;
  kind: "raster-tiles" | "raster-mask" | "polygon-vector" | "point-vector" | "bbox-vector";
  renderMode: "draped" | "extruded";       // §4.6 — different primitives, not a flag
  title: string;
  source: { tileUrlTemplate?: string; geojsonUrl?: string };
  bounds: GeoBoundingBox; minZoom: number; maxZoom: number;   // from TileJSON — never guessed
  colorRampId: ColorRampId;                 // from lib/constants/layers.ts
  opacity: number; isVisible: boolean;
  comparatorSide: "left" | "right" | "both";
  extrudeByProperty?: string;
  provenance: { modelId: string; modelVersion: string; traceStepId: string; confidence: number | null };
}
```

One renderer factory maps `kind` → Cesium primitive. **Adding a new analysis product means the backend
emits one more descriptor. Zero frontend files change.** That is the scalability answer for this page,
and it is also what makes pages 3 and 4 configuration rather than code.

### 5.3 The evidence graph is normalised

Claims ↔ evidence ↔ layers ↔ trace steps is a graph, not a tree. Nested objects would make the spotlight
interaction (§4.2) an O(n) scan and re-render the whole answer panel on every hover.

Store it as `byId` maps plus id arrays. Hover writes a single `spotlightClaimId`; only the affected rows
and the viewer subscribe. Same discipline as Page 1's marker feed — the renderer gets the minimum shape
it needs, the full record is fetched on demand.

### 5.4 State placement — no new rules, existing ones applied

| State | Home | Why |
|---|---|---|
| Investigation record, scenes, evidence graph, report | TanStack Query | Server state. Cached, refetched, invalidated. |
| Analysis run (streaming) | SSE → append-only cache mutation | Same shape as Page 1's assistant stream. Never refetch a running trace. |
| Split position, layer opacity, draw mode, spotlight, comparator binding, panel collapse | `investigation-store` (Zustand, feature-scoped) | View state. Changes at 60 Hz while dragging; must never touch the query cache. |
| `SceneViewerHandle` | Published into the feature store on mount | Established pattern — imperative handles live in the store so the agent can reach them from outside React. |
| Camera pose | **Neither** — lives in the viewer, sampled on save | Updates every frame. React state or URL sync here is the classic way to destroy a frame budget. |

### 5.5 The URL is the investigation

`/investigation/[investigationId]` is shareable and restores the workspace: scenes, layers, transcript,
and the saved camera bookmark. Ephemeral view state (drag position, hover) stays out of the URL — it is
noise, and it would thrash history.

### 5.6 Rendering cost rules (extending those in `architecture-context.md`)

- **Cross-fade imagery, never swap it.** Add the new layer, ramp `alpha`, then remove the old. Swapping
  gives a black frame — the definition of glitchy.
- **Prefetch T1 tiles during the descent.** The camera flight is ~2 s of otherwise idle network. The
  reveal must be instant, not a spinner.
- **Never rebuild a `GeoJsonDataSource` on an opacity change.** Mutate the material.
- **`requestRenderMode` on**, disabled only while the camera or the playbar is animating.
- **Vector cap.** Above ~100k features, that is the deck.gl trigger `memory.md` names — not before.
- **Bound every tile request** with the TileJSON `bounds` / `minzoom` / `maxzoom`. Unbounded providers
  hammer the tiler with planet-wide 404s.
- **Skeletons match final dimensions**, or data arrival jumps the layout.

---

## 6. Connecting Page 1 → Page 2

### Four entry paths, one mechanism

1. Select scenes in the catalogue → **Investigate**
2. Click a globe marker → its mission → **Open investigation**
3. Ask AERIS a question on Page 1 that needs imagery → it proposes an investigation → accept
4. Command palette or voice: *"investigate the Sundarbans scene"* → `investigation.create`

All four converge on one command, so there is exactly one code path to test and one for the agent to
call:

```
dispatchCommand("investigation.create", { sceneIds, seedQuery?, aoi? })
   ↓  POST /api/v1/investigations           → { investigationId, aoi, cameraTarget }
   ↓  store.beginHandoff({ target: cameraTarget })
   ↓  globeViewer.flyTo(cameraTarget)        ← the descent starts on Page 1
   ↓  router.push(/investigation/:id)        ← fires immediately; the flight is NOT awaited
   ↓  Page 2 mounts around a camera already in motion, attaches its layers
   ↓  target-lock brackets → scan-in wipe → change polygons bloom
```

**The critical detail: the navigation is not awaited.** Waiting for the flight to finish before routing
produces a dead pause. Because the viewer lives in the shared layout (§5.1), Page 2 can mount underneath a
moving camera and start populating while the descent is still happening. The operator sees one continuous
move; the network requests hide inside it.

**Going back** reverses it: the workspace's layers detach, the camera climbs to orbit, Page 1's marker
layer re-attaches — and the marker for the investigation just left is briefly highlighted, so the operator
lands oriented rather than lost.

### Continuity of the assistant

The Page 1 conversation is not thrown away. The seed query becomes the investigation's first turn, so the
operator's question follows them down. Asking on the globe and answering in the workspace is one thought,
not two sessions.

---

## 7. Proposed file layout

```
app/(geospatial)/
  layout.tsx                                   # owns the shared Cesium stage
  page.tsx                                     # Mission Command  (URL unchanged: "/")
  investigation/[investigationId]/
    page.tsx                                   # thin — mounts InvestigationScreen
    loading.tsx

components/sharedUI/functionalComponent/geoStage/     # the ONLY place importing cesium
  CesiumStageProvider.tsx                      # single Viewer lifecycle, publishes handles
  stage-viewer.ts                              # camera, picking, render-mode policy
  layer-renderers/
    raster-tile-layer.ts   raster-mask-layer.ts
    polygon-vector-layer.ts   extruded-polygon-layer.ts   bbox-layer.ts
    marker-layer.ts   arc-layer.ts             # relocated from missionCommand/globe
  split-comparator.ts                          # splitDirection + splitPosition + sweep
  region-draw.ts                               # rectangle / polygon capture

features/investigation/
  components/
    InvestigationScreen.tsx
    header/        InvestigationHeader.tsx  SceneSlotChips.tsx  TraceRibbon.tsx  PresentModeToggle.tsx
    inputsPanel/   InputsPanel.tsx  SceneSlotCard.tsx  EvidenceLayerStack.tsx  EvidenceLayerRow.tsx
    viewer/        SceneViewport.tsx  ViewerToolCluster.tsx  SplitHandle.tsx  TemporalPlaybar.tsx
                   RegionDrawOverlay.tsx  RegionPromptPopover.tsx  TargetLockOverlay.tsx
    answerPanel/   AnswerPanel.tsx  ClaimCard.tsx  MetricStat.tsx  ConfidenceVerdict.tsx
                   EvidenceChipRow.tsx  InsufficientEvidenceCard.tsx  InvestigatePlanSheet.tsx
    tracePanel/    ExecutionSpine.tsx  TraceStepNode.tsx  ArtefactPeekButton.tsx
    report/        ReportDrawer.tsx  ReportSection.tsx  ExportMenu.tsx
  hooks/
    use-investigation.ts        use-analysis-run.ts        use-evidence-graph.ts
    use-scene-layers.ts         use-split-comparator.ts    use-region-selection.ts
    use-evidence-spotlight.ts   use-autonomous-investigation.ts
    use-investigation-commands.ts   use-report.ts
  services/   investigation.service.ts  analysis.service.ts  evidence.service.ts  report.service.ts
  store/      investigation-store.ts
  schemas/    investigation.schema.ts  analysis.schema.ts  evidence.schema.ts
              layer.schema.ts  report.schema.ts
  types/      (inferred from the schemas, per existing convention)

lib/constants/
  investigation.ts        # panel sizes, split defaults, animation timings, playbar rates
  layers.ts               # layer kinds, colour ramps, opacity defaults, extrusion scale
  pipeline-stages.ts      # S1–S20 codes, labels, descriptions — from PDF §15.1
```

Everything hardcoded goes in `lib/constants/`; every tunable goes through `lib/env.ts`. No exceptions,
per project rules.

---

## 8. Backend contract

The COG + TiTiler + CORS + alpha + TileJSON-bounds requirements already recorded in `memory.md` all still
hold. New for this page:

| Endpoint | Shape | Notes |
|---|---|---|
| `POST /api/v1/investigations` | `{sceneIds, seedQuery?, aoi?}` → `{investigationId, aoi, cameraTarget}` | Must return **fast** — the descent is already flying. Heavy work happens after. |
| `GET /api/v1/investigations/:id` | full record | Scenes, layers, camera bookmark, run history. |
| `PATCH /api/v1/investigations/:id` | name, camera bookmark, layer visibility | Workspace persistence. |
| `POST /api/v1/investigations/:id/scenes` | attach a scene to a role slot | `t0` / `t1` / `sar` / `aux`. |
| `POST /api/v1/investigations/:id/runs` | **SSE** | Discriminated union on `type`: `run-start`, `trace-step`, `layer-ready`, `claim`, `run-complete`, `run-error`. |
| `GET /api/v1/investigations/:id/evidence` | the graph | `{claims[], evidence[], layers[], traceSteps[]}` — flat arrays with ids, already normalised. |
| `GET /api/v1/investigations/:id/plan?from=:claimId` | the autonomous plan | Returned **before** execution so it can be reviewed and edited. |
| `POST /api/v1/investigations/:id/report` | SSE or poll | Sections stream so the drawer assembles live. |
| `GET /api/v1/investigations/:id/report.{pdf,json,geojson}` | export | Trace ID embedded in all three. |
| `GET /api/v1/regions/suggestions?investigationId&geometry` | suggested questions for a drawn polygon | Backend-driven, like Page 1's. |

### Five requirements that matter more than they look

1. **`layer-ready` must be its own SSE event, separate from `trace-step`.** The viewer should render a
   change mask the moment it exists, not after the whole run finishes. That is the difference between a
   workspace that feels alive and one that feels like a form submission.
2. **Every trace step carries its artefact URI.** PDF §21.2 already requires retaining them. Surfacing the
   URI costs nothing and buys §4.3 entirely.
3. **Every evidence polygon carries numeric properties** — `areaHectares`, `magnitude`, `confidence`,
   `modelId`, `modelVersion`, `traceStepId`. `magnitude` drives extrusion; the rest drive the layer row.
4. **Masks need both representations.** Raster tiles for display *and* vectorised GeoJSON for evidence.
   Raster alone gives a picture; polygons give a clickable, auditable answer.
5. **Claims carry `evidenceIds`, and confidence stays `number | null`.** Null means AERIS declines to
   assert — it renders as §4.7's refusal card, never as 0%.

---

## 9. Build sequence

One vertical slice at a time, each with a gate checkable in a browser. Per `ai-workflow-rules.md`: *"if a
change cannot be verified end to end quickly, the scope is too broad."*

| # | Unit | Gate |
|---|---|---|
| 1 | Route group + shared Cesium stage; relocate globe layers; `SceneViewerHandle` | `/` behaves exactly as today; globe → `/investigation/:id` is one uninterrupted camera flight |
| 2 | Scene viewer: imagery layers, split comparator, inputs panel, layer stack | T0/T1 load and the slider sweeps between them at 60 fps |
| 3 | Answer panel: claims, metrics, confidence verdict, **evidence spotlight** | Hovering a claim dims the scene and lights its polygons |
| 4 | Execution spine + artefact peek | Clicking S9 shows the co-registration residual on the scene |
| 5 | Region draw + ask-this-region | Draw a box, ask a scoped question, get a scoped answer |
| 6 | Volumetric mode, temporal playbar, present mode, target-lock / scan-in / bloom | Full cinematic run with chrome hidden, no dropped frames |
| 7 | Autonomous investigation (plan sheet + command macro) | `Investigate` drives camera, layers and spine with zero bespoke rendering code |
| 8 | Report drawer + exports | PDF carries the trace ID; GeoJSON opens in QGIS |
| 9 | Voice adapter | The seven phrases in §4.9 drive the workspace with no new UI |
| 10 | Pages 3 and 4 as workspace modes | Cross-Modal and Temporal ship as configuration, not new components |

Units 1–4 are the demo spine. If time runs out after unit 4, there is still a complete, credible story.

---

## 10. Risks and honest limits

| Risk | Reality | Mitigation |
|---|---|---|
| Shared-stage refactor destabilises Page 1 | Real. Page 1 works today and this moves its renderer. | Unit 1 ships alone with the gate "Page 1 behaves exactly as today". No new features in that unit. |
| Draped vs extruded are different primitives (§4.6) | A design constraint that needs build-time verification against Cesium 1.144 | Modelled as `renderMode` in the descriptor from day one, so discovering the detail late costs nothing |
| Cesium's split is a straight line only | No circular "magnifier lens" without a second context or a custom shader | Deferred and recorded. The straight sweep is the stronger interaction anyway. |
| deck.gl has no depth interleaving on Cesium | Already recorded in `memory.md`. Fine for nadir overlays. | Never use deck.gl for anything that must sit *inside* the 3D scene |
| Large COG over a slow link | Progressive tiles help, but first paint can lag | Prefetch during the descent; low-zoom tiles first; skeleton matches final dimensions |
| Autonomous investigation looks scripted | Fair criticism if the plan is fixed | The plan is server-generated and **editable before it runs** — a scripted demo cannot let a judge delete a step |
| **Nothing has been verified visually by me** | Still true. One product-owner screenshot is the only visual evidence to date. | Confirm Page 1 renders correctly before building anything on top of it |

---

## 11. Decisions needed before implementation

1. **Approve the shared-stage refactor (§5.1)?** The load-bearing one. Declining it means the globe→AOI
   descent becomes a cross-fade, and the "one engine" rationale loses its best argument.
2. **Answer surface or transcript on the right?** This document proposes an answer *surface* — current
   claim prominent, prior turns collapsed — which differs from Page 1's transcript.
3. **Do pages 3 and 4 become modes of this workspace (§1)?** Cheap now, expensive to retrofit later.
4. **Is `Present` mode in scope for the first pass?** Very low cost, high demo value, zero analytical value.
5. **Ion token.** Still unset. Without it the workspace shows a flat dark basemap under the operator's
   scene instead of real satellite Earth with elevation — which materially changes how §3's signature
   moments land.
