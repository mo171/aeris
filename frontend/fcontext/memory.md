# Frontend Memory

Running handover log. Newest session at the top.

---

## Session — 2026-08-30 (f) · Seven surfaces cut to four, and a hydration bug I did not solve

### The audit: which pages actually need to be pages

Applied the test session (e) produced — *could an operator arrive here with nothing open?* — to the four
remaining rail entries. Three of the original seven failed it:

- **Temporal Explorer** — already shipped inside the workspace. The timeline, the split comparator and
  change detection are all there; the route would have been page 2 with its tools amputated.
- **Mission Library** — redundant three ways: Mission Command lists missions and draws their globe
  markers, and the investigation index is the shelf. Continuous monitoring is later-tier scope, so the
  half that would justify a surface does not exist. **Revival condition:** if scheduled runs and an alert
  queue get built, that queue IS a place — bring it back then.
- **Cross-modal** — done in session (e).

**Rail is now four: Mission Command · Investigation · Model Observatory · Evidence Audit.** `ROUTES` lost
`TEMPORAL` and `MISSION_LIBRARY`; `navigation.ts` carries the test and what each entry failed on.

I also dropped the planned "missions tab on the investigation index". Mission Command already does it
better, and a second worse list is noise.

### `lib/constants/models.ts` — the model catalogue

The trace said `changeformer` while the fleet said `mdl_changeformer`, so **"which model produced this
claim, and why was it chosen" could not be answered by joining the two.** There is now one id vocabulary,
declared here, and `model.schema.ts` builds its wire enums from it — an unknown id fails at the boundary.

Same split as `pipeline-stages.ts`: **the wire carries the id, the copy lives in the catalogue.** The
status payload shrank to `id / version / health / latency / queueDepth`; name, family, capability,
`selectionRationale` and `limitations` are authored text. That is what lets the trace and the Observatory
give one account of a model instead of two.

`selectionRationale` is written as the **routing rule** — the condition under which this model wins —
because the operator reading it is asking why they got this model and not another.

### Runs and lenses are different verbs

`AnalysisOperation` now carries `kind: "run" | "lens"`. A run produces evidence; a lens re-reads what
exists. **A lens that dispatched a run would fabricate a trace step for work nobody did.** The branch is
duplicated in `InvestigationScreen.handleRunOperation` and in the `investigation.runOperation` command
handler on purpose — the latter is the agent's entry point and has no component above it.

### Also shipped

- **Selection rationale on every trace step**, resolved from the catalogue by id.
- **Save as mission** — `POST /api/v1/missions`, `investigation.saveAsMission` on the command bus, a
  header toggle that keeps its saved state rather than firing a toast. Lives in `features/missionCommand`
  because the work is mission-domain; only the trigger belongs to the workspace.
- **Model Observatory** (`/models`) — verified in the browser: 12 models, live health joined to the
  catalogue, `not deployed` for entries with no status row, rationale and limitations side by side.
- **`app/(reference)/`** — a route group with the shell but no Cesium stage, per the rule in
  `(geospatial)/layout.tsx` that the Observatory must not pay for a WebGL context it never draws into.

### THE UNSOLVED BUG — read this before touching either page

Two component shapes make a page in `app/(reference)/` **stop hydrating entirely**: the server HTML stays
on screen, no query ever fires, no error is logged anywhere.

1. `PanelSkeleton` as the loading state — broke `/models`.
2. A local `<FilterChip>` / `<FilterRow>` component around the filter markup — broke `/evidence`.

Inlining the identical markup fixed `/models` completely. It did **not** fix `/evidence`: with the
components inlined and literal class strings, the page still fails, and the last remaining delta is the
**Model filter row** (`MODEL_ORDER.map` over `SPECIALIST_MODELS`). That is where the next bisect starts.

Ruled out by clean per-test production builds: the dev server, `force-dynamic`, `VirtualizedList`, the
shadcn `Input`, the hook, the service, the schema and the mock. The hook was proven correct in isolation
— a minimal screen calling `useEvidenceAudit` renders `loading=false claims=0 total=0` and hydrates.

**`/evidence` is therefore `isAvailable: false`.** The route, contract, service, hook, mock and filters are
complete and correct; only the screen fails to come alive. Do not flip the flag until a filter chip
responds to a click.

### The process lesson, which cost more than the bug

I deleted `.next` while the dev server was running and then ran `next build` against the same directory.
For a long stretch afterwards I was testing stale servers and drew several confident, wrong conclusions
from them. **Verify each hypothesis on its own isolated build** — `AERIS_DIST_DIR=… next build` plus
`next start` on a fresh port — rather than trusting a dev server that has been disturbed. Once I did that,
the bisect converged in a handful of steps.

`tsc` clean · eslint clean (one pre-existing TanStack Virtual warning) · `next build` green at 7 routes.

---

## Session — 2026-08-30 (f) · Seven surfaces cut to four, and a model catalogue that the trace can join to

Audited the remaining rail entries against the test session (e) produced — *could an operator arrive here
with nothing open?* Three of the original seven failed it. **The rail is now four: Mission Command,
Investigation, Model Observatory, Evidence Audit.**

### What was deleted, and why each one failed the test

- **Temporal Explorer** — the doc asks for T0/T1 comparison, change maps, a timeline scrubber and a
  before/after slider. All four already shipped inside the workspace: `TimelineScrubber` +
  `TimelineTrack` over the archive, `SplitHandle` with `comparatorBinding: "temporal"`, the
  `change-detection` operation, and the fair-comparison advisory. **There was nothing left to build** — the
  route would have been the workspace with its tools amputated.
- **Mission Library** — redundant three ways: Mission Command lists missions and draws their globe
  markers, and the investigation index is the shelf. The half that would justify a surface (scheduled runs,
  an alert queue) is later-tier scope by an explicit earlier decision (`design_report.md:108`). **Revival
  condition recorded in `navigation.ts`:** if an alert queue gets built, that queue *is* a place.
- **Cross-Modal** — collapsed in session (e).

`ROUTES.TEMPORAL` and `ROUTES.MISSION_LIBRARY` were referenced only by `navigation.ts`, so removal was
clean.

### The model id vocabulary was broken, and nobody could have noticed from the UI

The design document asks the Observatory to explain "why they were selected". Building it surfaced a real
defect: **the trace steps, the claims and the fleet status feed named models differently.** A claim said
`changeformer`; the fleet said `mdl_changeformer`. Others were pure inventions with no fleet entry at all
— `registration`, `segformer-lulc`, `mndwi-threshold`, `density-kernel`, `geospatial-engine`, `sar-change`.
Joining "which model produced this claim" to "what is that model" was impossible.

**`lib/constants/models.ts` is now the single vocabulary**, following `pipeline-stages.ts` exactly: the
wire carries the id, the copy lives in the catalogue. Twelve models, each with `family`, `role`,
`selectionRationale` (written as the ROUTING RULE — the condition under which this model wins) and
`limitations`. `MODEL_CAPABILITIES` and `MODEL_IDS` are declared there and `model.schema.ts` builds its
enums from them, so **an unknown model id now fails at the schema boundary** instead of rendering as a
nameless row.

`modelStatusSchema` lost `name` and `capability` — the wire carries id, version, health, latency and queue
depth, nothing else. Every mock (`model.data`, `investigation.data`, `cross-modal.data`, `assistant.data`)
was canonicalised onto the catalogue ids.

**Consequence worth keeping:** `TraceStepNode` now resolves its step's model to the catalogue and prints
the routing rationale under the row, and the model id links to the Observatory. The trace answers *what
happened*; the Observatory answers *what exists*. Neither can contradict the other because there is one
source.

### Merged into the workspace instead of built as pages

- **Save as mission** — `useSaveAsMission` lives in `features/missionCommand/hooks/`, not the
  investigation feature: the work is mission-domain, only the trigger belongs to the workspace. That is the
  mirror of `use-investigation-launch.ts`. The analysis kind is derived from the investigation's own mode
  rather than asked for — a dialog with one right answer is not a question.
- **"Why this model"** — into `TraceStepNode`, above.

### New surfaces

**Model Observatory** (`/models`) — verified working. Joins the catalogue with live status: `8 online ·
2 degraded · 0 offline`, per-model version, latency, queue depth, stage chips, and `not deployed` for a
catalogue entry with no status row. The fleet strip on Mission Command now links to it.

**Evidence Audit** (`/evidence`) — **built but NOT working. See below.** Cross-investigation claim search
over a new `GET /api/v1/evidence/claims`, filterable by model, confidence band and free text, with rows
linking back to their investigation. The mock reads the *same* generated investigations the workspace
reads rather than generating a second corpus — an audit that can show a claim the linked investigation
does not have is the one failure this surface must not have.

### New route group: `(reference)`

`app/(reference)/` hosts both, with `AppShell` and **no `GeoStage`** — the `(geospatial)` layout's own
comment says to scope it deliberately and names the Model Observatory as the example. A surface belongs in
`(reference)` when it answers a question about the SYSTEM rather than about a place. Rows that need
geometry deep-link into the workspace, which already owns a viewer.

### UNRESOLVED — read this before touching either surface

**`PanelSkeleton` stops these pages hydrating.** Reproduced on a clean production build (`next build` +
`next start`, separate `distDir`, fresh port each time):

- Model Observatory with `<PanelSkeleton />` in its loading branch: page renders server-side, **never
  hydrates**, so the status query never fires and the skeleton never resolves. No console error, no error
  boundary, all chunks 200.
- Same file with the skeleton replaced by plain markup: hydrates, query runs, 12 cards render.
- Wrapping the skeleton in a `GlassPanel` did **not** help. `export const dynamic = "force-dynamic"` did
  **not** help. Swapping `VirtualizedList` for a plain list did **not** help.

Both new screens now use plain loading markup, which fixed the Model Observatory. **The Evidence Audit
still does not hydrate** — its filter chips are inert and the corpus never loads — so its rail entry is
left `isAvailable: false` rather than advertising a surface that cannot be used. Root cause not found.

Next person: bisect `EvidenceAuditScreen` the way `ModelObservatoryScreen` was bisected — replace the body
with a minimal component that only calls `useEvidenceAudit`, confirm it hydrates, then add JSX back in
halves. The probe technique that worked: assign to `globalThis` **inside the service function**, not in a
render body — React Compiler appears to elide side effects written in component bodies, which is why
`console.log` probes there silently never ran and cost an hour.

### Process notes, both mine

- **I ran `next build` against a running `next dev`.** They share `.next`; I then deleted `.next` under the
  live server to "fix" it, which broke the running app and sent me chasing a phantom hydration bug across
  several ports. **Verification builds must use a separate `distDir`** — do that from the start, and never
  delete `.next` while dev is running. I could not restart the user's dev server afterwards (owned by
  another session, `Access is denied`), so it was left for them.
- **I skipped `node_modules/next/dist/docs/`**, which this repo's CLAUDE.md tells me to read before writing
  code. Reading `route-groups.md` afterwards confirmed the group layout was fine, but it should have come
  first.

### Verified

`tsc --noEmit` clean · eslint clean (one pre-existing TanStack Virtual warning) · `next build` green at
7 routes, with `/models` and `/evidence` dynamic. Model Observatory verified visually on a production
build. **Phase A and the Phase B merges compile but were not browser-verified** — the dev server was in a
bad state by then.

---

## Session — 2026-08-30 (e) · Page 3 collapsed into page 2 — cross-modal is a LENS, not a surface

The product owner called this: the Cross-Modal Lab should never have been its own page. It is now a lens
inside the Investigation Workspace. **The 2026-08-30 (d) entry below is superseded** — the reasoning in
its "Correcting an earlier decision" section was wrong, and the correction is the most useful thing here.

### Why the standalone route was wrong, and how I talked myself into it

I planned page 3 from the design document's routing example 4, which describes cross-modal as its own
flow, and let **"distinct flow" mean "distinct route"**. Then I reinforced it with an argument that does
not hold: *a workspace claim carries one provenance, a cross-modal claim carries two that can disagree,
so it needs its own surface*. Two provenances is a property of the **result object**, not of the
**surface it is read on**. The workspace already renders layers with three different encodings; it can
hold a result with two provenances. I confused the shape of the data with the shape of the page.

**The code said so before the owner did.** Three comments I wrote on that page:

- `use-cross-modal.ts` — "Read-only against an EXISTING investigation. The Lab never creates one."
- `buildRoute.crossModalLab` — "Same evidence graph, same scenes, a different reading of them."
- `CrossModalHeader` — the back-arrow exists "otherwise the two surfaces start to feel like two copies of
  the same imagery."

That last one is the tell. **A page that needs a permanent "return to the thing I am actually about"
button is a panel that got promoted to a route.** I noticed the problem three times and routed around it
each time.

### The process failure, which is the part worth keeping

I evaluated the new page against the design document and against itself. I never asked **what does the
operator lose by leaving the workspace** — the one question that catches this class of mistake. When the
owner asked "is anything left on page 2" I audited page 2 before moving on; the mirror-image audit on the
page I had just built never happened.

What it cost, concretely: on the standalone route the operator had no Toolbox (could not run
`sar-analysis` on a page *about* SAR), no assistant (saw a conflict, could not ask why), no draw tools
(could not scope a question to the disagreement), **and no timeline** — the page computed an advisory
saying the pair was 4 days apart, told the operator that mattered, and withheld the only control that
changes it.

### What a LENS is, as a first-class idea

`AnalysisOperation` now carries `kind: "run" | "lens"`.

- A **run** dispatches an analysis and appends to the evidence graph.
- A **lens** re-reads evidence that already exists. No model executes, no trace step appears, nothing is
  added to the graph.

They share `lib/constants/analysis-operations.ts` because they share a question ("what can I do here?")
and a requirements vocabulary. The branch matters: **a lens that dispatched a run would fabricate a trace
step for work nobody did**, which is the opposite of auditable. The branch is duplicated in
`InvestigationScreen.handleRunOperation` and in the `investigation.runOperation` command handler on
purpose — the command handler is the AGENT's entry point and has no component above it.

### Three entry points, no rail item

`cross-modal` is an entry in `ANALYSIS_OPERATIONS` with `requires: ["optical", "sar"]`, so it appears in
the Toolbox, in the command palette, and to the agent for free. Requirements are declared, not enforced,
so an investigation with no radar sees the row with "Needs a radar scene attached to this investigation"
attached — **which does the old `CrossModalIndexScreen`'s job better**, because the explanation now sits
where the operator already is instead of on a picker they had to find first.

The header radar button became a **toggle** (`aria-pressed`) instead of a `<Link>`.

**The rail went from seven surfaces to six.** The test `lib/constants/navigation.ts` now states: *could an
operator arrive here with nothing open?* If not, it is not a rail item. Cross-modal needed an
investigation id the rail could not supply, and the index route added last session to paper over that was
a symptom, not a fix. Last session's checklist (route + index + flag + icon) still holds — but the
question that comes before it is whether the thing is a place at all.

### One stage writer

`useCrossModalStageBinding` used to call `stage.sceneLayers.setLayers` at the same time as
`useSceneStageBinding` did — two hooks, one stage, resolved by whichever effect ran last. That is a race,
not a design, and it only existed because the Lab was a separate route with no workspace binding beneath
it.

It is now `features/crossModal/lib/sensor-stage-layers.ts`: a **pure function**, `composeSensorLayers`,
that `useSceneStageBinding` calls through a new `sensorLayers` option. Spotlighting by agreement row goes
through a matching `spotlightFeatureIds` option, because a row spans both sensors and has no single claim
behind it to resolve from. **Rule: exactly one thing in the application pushes layers to the stage.**

### `displacedBinding` — the field that is easy to leave out

Opening the lens forces `comparatorBinding` to `"crossModal"` (radar left, optical right). The lens
records what it displaced and restores it on close. Without that, closing the lens leaves a radar/optical
split on a temporal investigation and the operator has no way to know why. Verified: set Temporal → open
lens (Cross-modal) → close → Temporal.

### Slots, so the panels stay ignorant

`InputsPanel` takes `sensorsSection?: ReactNode`; `AnswerPanel` takes `verdictSection?: ReactNode`. Both
receive already-composed elements and learn nothing about cross-modal. The dependency is one-way —
investigation composes crossModal — which also resolved a latent module cycle, since the only two files
importing *from* investigation (`CrossModalHeader`, `CrossModalIndexScreen`) were deleted.

**The verdict sits ABOVE the runs, not instead of them.** A verdict is a standing fact about the
evidence; a run is an answer to a question somebody asked. Both belong on screen, and having them
together is the entire point.

### Net-new capability: every agreement row can be acted on

Expanding a ledger row now offers **Ask about this** (hands `agreementQuestion(...)` to the workspace
composer) and **Focus** (frames the union of the features BOTH sensors contributed). The old ledger could
name a conflict and advise "resolve with a third observation" on a surface with no composer and no camera
control — advice the operator had to leave the page to act on.

### Deleted

`app/(geospatial)/cross-modal/**` (both routes) · `CrossModalScreen` · `CrossModalIndexScreen` ·
`CrossModalHeader` · `use-cross-modal-stage-binding` · `ROUTES.CROSS_MODAL` · `buildRoute.crossModalLab` ·
the `cross-modal` navigation entry.

**No redirect and no `?lens=` URL parameter**, deliberately. Nothing has shipped, and the investigation
store's stated rule is that a shared URL restores *the investigation and its camera*, not view state. A
lens parameter would contradict it.

Kept and untouched: `lib/agreement.ts`, the schemas, the service, `lib/constants/cross-modal.ts`, and
`GET /api/v1/investigations/:id/cross-modal`. **The whole logic layer moved without a single edit** —
none of it ever knew what a route was. Only composition changed.

### Verified in the browser

Toolbox shows `11 + 36` with the cross-modal row carrying an **eye** icon, not a play button; pressing it
flips the row to `open · S13`. Left panel gains **SENSORS** (`4d · FAIR`, both cards, close control) above
Inputs / History / Findings / Masks / Reference — all still present. Right panel shows **NO HEADLINE —
THE SENSORS DISAGREE** with the tally 1 conflict / 2 optical-only / 1 radar-only / 3 corroborated, and a
7-row ledger sorted conflict-first. Expanding a conflict spotlights the polygon on the scene across both
sensors. **Ask about this** dispatched a real run whose answer streamed in below the verdict, with six
evidence layers, the legend and a 14/14 trace — the exact flow that was impossible a route away.

While the lens is open: 20 timeline acquisition markers live, prev/next/play/archive controls live, draw
tools (Rectangle / Polygon / Circle) live, composer live, layer solo controls live.

`tsc --noEmit` clean · eslint clean (one pre-existing TanStack Virtual warning) · `next build` green at
**5 routes**.

### Known Phase-1 limit, not a UI bug

`GET /api/v1/investigations/:id/cross-modal` is keyed on the investigation alone, so moving the timeline
while the lens is open does not recompute the offset advisory. The timeline IS live and operable — the
verdict simply does not yet depend on the selected pair. Phase 2 should take the baseline and comparison
scene ids as query parameters.

### Harness note (still true)

Cesium stops initialising after roughly a dozen reloads in one pane — WebGL context exhaustion, not a
regression. Open a fresh tab. Also: the mock only attaches a SAR slot when **three or more scenes** are
selected on Mission Command (`hasSar = sceneIds.length >= 3`), so a two-scene selection can never produce
a cross-modal investigation to test against.

---

## Session — 2026-08-30 (d) · Page 3 — the Cross-Modal Analysis Lab

> **SUPERSEDED by session (e) above.** The Lab was collapsed into the Investigation Workspace as a lens.
> Everything below about the AGREEMENT MODEL, the fusion policy and the mock bugs still holds and is still
> the reference for those; everything about the ROUTE, the index screen and the standalone screen does
> not. The "Correcting an earlier decision" section immediately below is itself the wrong correction.

Planned first (artifact: claude.ai/code/artifact/bcf472f5-4468-43b4-a750-9a96bef80b36), then built all
three tiers. Route: `/cross-modal/:investigationId`, inside the `(geospatial)` group so it shares the one
Cesium viewer.

### Correcting an earlier decision

A previous session recorded "pages 3 and 4 ship as workspace modes, not new components". That is right
for page 4 and WRONG for page 3. A comparator binding swaps which two rasters the split reveals — one
analysis, one claim set. The design document's routing example 4 specifies something else entirely:
per-sensor analysis, then joint interpretation, and "the answer must say which sensor supports which
claim". A workspace claim carries one model, one version and one confidence; a cross-modal claim has two
of each and they can disagree. Different shape, so a different page.

### The thesis, taken from §9.1–9.2

Late fusion was chosen because it is "the most auditable, since each modality's evidence stays separable".
That is a user-interface argument as much as a modelling one, so the rule the page cannot break is:
**there is no blended product anywhere**. No composite raster, no averaged confidence. Optical renders in
the system accent, radar stays achromatic, and the fusion lives entirely in the verdict — language and
geometry, never colour.

### The four agreement states, each with a physical cause

CONFLICT · OPTICAL-ONLY · RADAR-ONLY · CORROBORATED, sorted conflict-first everywhere.
`features/crossModal/lib/agreement.ts` classifies them, and the ORDER OF TESTS IS THE POLICY:

1. **Obscuration first — a sensor that could not see cannot disagree.** If radar is in layover/shadow, its
   silence is not evidence of absence. This one rule removes most false conflicts.
2. Opposing directions second — the only true conflict.
3. Present in both — corroboration.
4. Present in one, neither obscured — a real difference in what the two instruments measure.

The reason string is the output, not the state. "Optical only" is a label the operator still has to
interpret; "radar could not see this region — it falls in layover or shadow" is what they can act on.

### Two product decisions, both mine to make and both flagged

- **A conflict BLOCKS the headline.** When the sensors assert opposite things the Lab declines a primary
  claim and names what would resolve it, rather than picking a side or averaging. Supporting rows are
  still delivered, tagged per sensor. Rigour where the reader will quote it, usefulness everywhere else.
- **Fused confidence is the MINIMUM of the two sensors, never the mean.** Averaging lets a confident
  sensor carry an unconfident one and reports the pair as more certain than either ever claimed.
- **The Lab READS an existing investigation** rather than owning one — the id travels in the URL, so the
  two surfaces are two readings of one evidence graph and imagery never lives in two places.

### Additions beyond the spec

Radar look-direction arrow and incidence readout (layover and shadow are PREDICTABLE from geometry, so an
operator who sees the azimuth anticipates blindness instead of discovering it inside a wrong answer);
VV / VH / ratio polarisation selector with what each is sensitive to; the four §9.2 "do not fuse"
refusals as a first-class answer; a modality-pair advisory with radar-appropriate thresholds.

### Three real bugs found while verifying, all worth keeping fixed

1. **Generated claims carry an empty `runId`** — the analysis stream stamps it as it emits. The Lab reads
   products directly, so it stamps its own. Cost twenty minutes because `parseApiResponse` retried
   silently and the UI just said "no result"; the empty state now shows the error message.
2. **`getMockEvidenceGraph` withholds analysis products until a run streams them.** Correct for the
   workspace, where evidence arriving IS the analysis happening; wrong for the Lab, whose premise is two
   completed runs. Added `getMockAnalysisProducts`.
3. **The mock archive gave radar every 4th slot instead of its own cadence**, leaving radar passes 100+
   days from the nearest optical one — so the Lab refused every pair it was offered. Sentinel-1 flies an
   independent 6–12 day repeat, so radar now gets companion acquisitions 2–9 days after every 4th optical
   pass. The old comment claimed radar was interleaved "for roughly the same window"; the data never did
   that.

### Verified in the browser

`4D APART · FAIR`; optical 78 findings / 8% unreadable / 91%; radar with `looking E · 78° · 39°
incidence`; **NO HEADLINE — THE SENSORS DISAGREE** with the conflict named; ledger of 7 rows, conflict
first, each carrying separate OPT and SAR confidences; expanding a radar-only row gives the reason plus
the amber action "check the optical cloud mask; if it covers the region, this is not a disagreement".
tsc clean, eslint clean, build green (6 routes).

### Shipping a page is not the same as unlocking it — I got this wrong

Built the whole Lab and left `NAVIGATION_ITEMS` at `isAvailable: false`, so the rail still said
"Cross-Modal Lab · Not built yet" and the surface was unreachable except from the investigation header.
The file's own comment says "flipping the flag is the only change needed when a page ships" — which was
almost true and made it easy to skip.

It was not quite only the flag, because the rail links to a SURFACE and the Lab needs an investigation
id. So `/cross-modal` needed an index too: `CrossModalIndexScreen`, same shape as the investigation
index and for the same reason — pointing the rail at a route that 404s is worse than a short list.
Investigations without radar are LISTED AND DISABLED with "no radar observation attached", not filtered
out, following the same rule the Toolbox uses for operations it cannot run.

**Checklist for every future page: route + index route + `isAvailable: true` + the icon.** Three of the
four are invisible in the page's own diff, which is exactly why they get missed.

### Harness note

Cesium stops initialising after roughly a dozen reloads in one pane — WebGL context exhaustion, not a
regression. Close the tab and `preview_start` again; it clears immediately.

---

## Session — 2026-08-30 (c) · Confidence hatching, and the legend moved off the scene

Two follow-ups after the catalogue landed, both raised by the product owner.

### The legend was parked in the middle of the scene

It sat in the centre column's flow, which was fine at two layers and became a wall across the middle of
the view at six. Now anchored `absolute top-0 left-0` in the free column — the corner opposite the feature
inspector, both anchored to the column rather than the viewport so neither can slide under a panel at any
panel width. Capped at `40vh` with internal scroll, and collapsible to a `LEGEND · n` header. A key is
something you glance at; it must never occlude the thing it describes.

### Confidence hatching — the last real gap on this page

Correcting my own plan text: I wrote that mask hatching "also finally delivers the confidence hatching
deferred from §4.7". It did not. Masks hatched; a weakly-supported finding still rendered as a plain
muted fill, so uncertainty read as "faint" — a rendering artefact an operator learns to ignore rather
than a statement. In a system whose argument is that every claim is auditable, evidence the model is
unsure about has to LOOK unsure. Now built.

**Two marks, two axes.** Masks stripe VERTICALLY at repeat 26 and mean "nothing can be asserted here".
Low confidence stripes HORIZONTALLY at repeat 10 and means "something is asserted here, weakly". Hatch
angle is how cartography has always separated different statements; using one angle for both would
collapse a distinction the product depends on.

**Repeat is relative to the GEOMETRY, not the screen.** Cesium repeats stripes across the polygon's own
texture coordinates, so the count is proportional to the shape. Masks are large blobs and carry 26; a
change region is a fraction of that size and the same count moirés into a grey wash at oblique angles.
Hence 10 for findings — coarser, and it leaves dense-vertical unambiguously the mask's mark.

**A NULL confidence is never hatched.** "The model declined to assert one" is a different statement from
"the model is unsure", and only one of them is a claim. Same rule the inspector already followed.

**Bounding boxes dash instead.** A box has no fill to hatch, so uncertainty moves into the channel that
geometry actually has — `PolylineDashMaterialProperty`. A solid box around a weak detection asserts more
than the detector did.

`CONFIDENCE_HATCHING.threshold` is 0.7 and lives in `lib/constants/layers.ts`. It is a PRODUCT decision,
not a scientific constant — the point past which an analyst should verify before acting rather than after
— and is meant to be tuned per deployment without touching the renderer.

The legend states `hatched = below 70% confidence`, computed from the same constant, and only when the
visible layers actually contain such a feature. A permanent note explaining a mark nobody can see teaches
the operator to stop reading the legend.

Mock confidence ranges were widened to straddle the threshold (change 0.44–0.97, detections 0.41–0.95,
land cover 0.52–0.94). A generated run where every finding is confident leaves the uncertainty rendering
unexercisable, and a real change run is not uniformly sure of itself.

### Verification technique worth reusing

Hatching at production density is hard to confirm in an 800×475 pane screenshot. Setting `repeat` to 4
temporarily made the banding unmistakable, proving the material and the orientation, after which the
constant was restored and tuned. Vary the parameter and observe the change — far cheaper than hunting
pixels at the intended setting.

### Still open on this page, deliberately

- **Layer reordering** (audit Tier 3, item 11) — draw order is descriptor order plus `stackHint`. More
  relevant now that six overlays stack freely, but the default order is sensible.
- **Basemap switcher** — the other half of item 11. Reference layers, terrain and land use all landed.

---

## Session — 2026-08-30 (b) · The overlay catalogue — masking and highlighting, rebuilt

Product owner asked for "a folder where we keep everything that we can mask or show data of" — buildings
by type, clouds, water change, heat maps, indices — and for the answer to what NDVI means ("is the ground
fertile"). Planned first (artifact: claude.ai/code/artifact/2fb643a2-24fb-4ef5-a0e1-b4bc42f9aa25), then
built all three tiers.

### The diagnosis, which is the reason for the shape

`colorRampId` was doing three jobs at once — choosing a palette, declaring what a product IS, and driving
the legend copy. Consequences: NDVI, NDWI and NDBI all mapped to `index-vegetation`, so a water map
rendered green; a feature carried magnitude but never a VALUE, so nothing could show a scale, a unit or a
threshold; and there was no class concept at all, so land-cover segmentation and building types were not
merely unbuilt, they were unexpressable.

### Three encodings, and only three

CONTINUOUS (one number over a domain) · CATEGORICAL (one class from a closed set) · GRADUATED (continuous
cut into ordered bands — the "different increments" that was asked for). Every product is one of the
three, so the renderer and the legend each need one branch per shape and never a case per product.

### `lib/constants/overlays/` — a dictionary, NOT a list of layers

The catalogue says what "ndvi" MEANS when a descriptor arrives; the backend still decides what a run
produces. Adding a product is one entry and zero component changes — the promise `layer.schema.ts` already
made and could not keep, because `EvidenceLegend.tsx` held a hardcoded ramp-id → meaning map.

Files: `overlay-catalogue.ts` (registry, groups, sections) · `color-ramps.ts` (stops + `sampleRamp`, the
one place a ramp is evaluated) · `class-palettes.ts` · `bin-schemes.ts` · `spectral-indices.ts` ·
`quality-masks.ts` · `building-attribution.ts` · `overlay-units.ts`.

`spectral-indices.ts` is transcribed from §3.3 of the design document — formula, Sentinel-2 bands,
meaning, thresholds and stated limitations for all seven indices. `analysis-operations.ts` now BUILDS its
index rows from it rather than restating them, so NDVI has one definition instead of two.

### Contract changes

`overlayId` (catalogue key, nullable so an unknown product still draws) and `valueDomain` (observed range,
narrower than theoretical) on the layer; `value` and `classId` on the feature; `classified` / `heatmap`
render modes; `heatmap-surface` layer kind. Feature `value` is the load-bearing addition — magnitude ranks,
value reads.

### Rendering

`lib/overlay-style.ts` resolves fill/outline/readout from the encoding, shared by the Cesium layer, the
legend and the inspector, so a key can never describe a picture nobody is looking at. Diverging ramps
normalise PIECEWISE around their neutral stop — a linear map over an observed −0.2..+0.8 would paint
unchanged ground in the colour of loss.

Masks hatch via Cesium's `StripeMaterialProperty` (native, no texture generation) so obscuration can never
read as a coloured finding. `heatmap-surface` extrudes by VALUE, not magnitude. Building massing is
restyled by `Cesium3DTileStyle` from the same palettes — colour by OSM `building` tag or by
`cesium#estimatedHeight` band, no refetch. **Gotcha:** that property contains a `#`, so the style must use
bracket form `${feature['cesium#estimatedHeight']}` — the `${name}` shorthand fails silently and every
building falls through to the last condition.

### Panels

Layer stack split FINDINGS / MASKS / CONTEXT, filed by `sectionForOverlay` so a new product lands in the
right section without editing the component. Legend is data-driven in all three forms. New
`OverlayBrowser` in the Toolbox lists what the system CAN show (the layer stack only lists what a run
happened to produce) with formula, reading and limitations per product. Inspector gained a Reading row
with the value, its band and a marker on the ramp.

### Overlays stack freely — decided by the product owner

Asked whether to add a conflict rule (one continuous surface at a time). Answer: no — "gives access all at
once, also the analyst can see layer by layer also, or he can hide few layers and keep few other layers
on." So no exclusion anywhere; `stackHint` only orders the draw. "Layer by layer" is served by the
existing solo/isolate toggle, which already worked and now spans the new sections.

### Two bugs found while verifying, both worth keeping

1. **Stale sessionStorage silently poisoned everything.** `aeris.mock.investigations` rehydrated
   pre-schema-change data into new code; every `layer-ready` frame failed validation and was dropped, and
   the workspace showed "no evidence yet" with nothing saying why. Fixed with `SESSION_STORAGE_VERSION`
   (bump it on any generated-shape change) plus a dev-only warn in `safeParseStreamFrame` naming the
   rejected paths. Silent drops are correct in production, silent drops in development are not.
2. **The mock stream emitted only the FIRST layer per trace step** (`.find`). One stage routinely produces
   several products — change mask, land cover and water extent all come from S13 — so three of the six new
   products never reached the scene. Now `.filter`.

### Verified in the browser

Six products stream (FINDINGS 6 · MASKS 2). NDVI renders as a green field with a ramp bar reading
`−0.2 … 0.75` and `0.4 to 1 = dense healthy vegetation`; land cover renders a six-class swatch key; change
mask renders a stepped bar `Negligible … Severe`; all three keys visible simultaneously. Clicking an NDVI
cell gives `0.56 · dense healthy vegetation` with a marker on the ramp. Building style toggles Plain →
By type → By height with visible recolouring. tsc clean, eslint clean, build green (5 routes).

---

## Session — 2026-08-30 (a) · Drawing was dead in photoreal mode — fixed

Product owner: "in 3d google map I cant draw and send message like it dosent do anything." Correct, and
the cause was one line written three sessions earlier.

### Cause — the ground stopped being the globe

`setBuildingMode("photorealistic")` sets `scene.globe.show = false`, because the Google tileset carries
its own ground. `region-draw.ts` picked exclusively with `globe.pick`, which returns nothing for a hidden
globe. Every click resolved to null, so no vertex was ever placed — no error, no shape, nothing. Because
the AOI is what scopes a question, the assistant then had nothing to scope to, which is why "send message"
looked broken too. One dead pick killed the whole workflow.

### Fix 1 — layered picking

`pickGround` now tries three surfaces in order, and the order is the point:

1. `globe.pick` — terrain. Cheap and correct, skipped entirely when the globe is hidden.
2. `scene.pickPosition` — the depth buffer, so it hits 3D tiles and building faces. Not first, because
   it is only valid where something was actually rendered.
3. `camera.pickEllipsoid` — bare WGS84. Always answers, so a click near the horizon degrades to a sane
   coordinate instead of aborting a shape mid-draw.

### Fix 2 — the shape has to be visible once drawn

Draping is not automatic. Ground shapes classify against terrain by default, and terrain is hidden in
photoreal, so a correctly-drawn box still rendered nowhere. `DrawController.setClassificationTarget`
mirrors the evidence layer's switch and `CesiumStage.setBuildingMode` now drives both together.

**Gotcha worth keeping:** the first attempt used a `CallbackProperty` for `classificationType` so a mode
switch would re-drape without rebuilding. It silently did not work. Cesium decides at entity-creation
time whether a shape becomes a classification primitive and only takes that path for a CONSTANT
classificationType — behind a callback it falls back to a plain primitive at ellipsoid height, drawn and
invisible under the tiles. Hold it as a constant and push it onto existing entities. Same reason
`evidence-vector-layer.ts` keeps a constant and rebuilds.

### Verified end to end, in photoreal

Houston / Gulf Coast Refineries, Photoreal on, 13 km: drew a rectangle → `226.88 km² · 60.71 km` in
AREAS OF INTEREST, teal box visibly draped on the Google tiles, "Ask this region" popover, question sent,
answer returned (`18.4% built-up change · 46.2 ha · 18 structures`) with change masks and structure boxes
rendering over the photoreal surface. Switched back to Flat — box and evidence still render, no
regression. tsc clean, eslint clean, build green (5 routes).

### Resolved a standing unknown

**Google Photorealistic content tiles DO stream.** Previous sessions could only confirm the root tileset
fetched. Downtown Houston rendered with full 3D building geometry. The mode works.

### Reported and deliberately NOT fixed — before/after comparison

Product owner: the comparison "dosent always work for all region and dosent work with google 3d nature",
and explicitly said to note it rather than build it now. Written up in the header of
`split-comparator.ts`, where anyone touching the feature will read it. Two separate causes:

1. **Blank outside the investigation footprint.** `scene-imagery-layer.ts` passes `descriptor.bounds`
   straight into the provider, so scene imagery exists only inside the AOI rectangle and the handle
   sweeps over nothing beyond it. In Phase 1 the archive side also stops at zoom 14 (the stand-in
   Sentinel-2 mosaic ends there), so a deep zoom degrades one half before the other. Real per-scene
   footprints change the shape of this, not the fact of it — the honest fix is to SAY there is no
   coverage here, not to render nothing.
2. **Structurally impossible over photoreal.** `splitDirection` is a property of `ImageryLayer`, draped
   on the globe; photoreal hides the globe and a 3D tileset has no split channel. Doing it would mean
   clipping the tileset with a clipping plane driven by the same position — a different mechanism, and
   it would only ever compare geometry Google captured, never the operator's own imagery. Photoreal is
   a context view; analysis lives on the globe.

---

## Session — 2026-08-29 (i) · 2D morph crashed the renderer — fixed

`DeveloperError: radians is required` from `CesiumMath.toDegrees(camera.heading)` inside `readCameraState`,
raised from `onPreUpdate`, killing the render loop with "Rendering has stopped".

### Cause

**Cesium's `Camera.heading` and `Camera.pitch` getters return `undefined` while `scene.mode` is
`MORPHING`** — the whole duration of a 2D / 2.5D / 3D transition. `toDegrees` throws on undefined. The
camera-state sampler I added for the view readout runs EVERY FRAME, including every frame of that morph,
so switching projection reliably killed the scene.

All five raw reads now go through one guarded `readOrientationDegrees()` returning null when the values
are unreadable:
- `readCameraState` → returns null; subscribers keep their last value and the readout holds still.
- `getBookmark` → returns null; there is no meaningful pose to save mid-morph.
- `orient` / `orbitByDegrees` → bail; the morph is itself a camera move in progress.

### The structural half

**Anything that throws inside a `preUpdate` listener stops Cesium's render loop permanently and it does not
recover.** The per-frame camera publish is now wrapped in its own try/catch that reports once and then goes
quiet. A coordinate readout is a convenience and must never be able to take the Earth down with it — but it
logs, so a genuine fault still surfaces rather than hiding.

Any future work in `onPreUpdate` inherits this hazard: six layer `update()` calls run there too.

### Also resolved

The "camera stuck at 19,000 km on reload" flagged last session was **not a regression** — it was the 0×0
viewport. A hidden Browser pane reports zero dimensions, the virtualised catalogue then renders no rows and
Cesium's canvas is 0×0, so nothing descends. With `resize_window` applied before the reload the descent
lands correctly (Rotterdam, 9.0 km).

### Verified

All three projections round-tripped — 3D → 2D → 2.5D → 3D — with zero console errors, rendering alive and
the readout still publishing correct coordinates throughout.

---

## Session — 2026-08-29 (h) · Google key live, Flat is the new default

### Google Photorealistic 3D Tiles — key verified

`NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` is set and works. Verified directly:
`GET https://tile.googleapis.com/v1/3dtiles/root.json?key=…` returns a real 3D Tiles root. The app picks it
up — the Photoreal control is enabled where it was previously disabled — and selecting it fetches the
Google root tileset with no warnings.

**Content streaming is NOT yet confirmed.** Every attempt ended with the camera at globe altitude
(19,000 km), where a city-scale tileset is correctly supposed to load nothing but its root. The hidden
Browser pane renders at ~1 fps and the descent did not complete inside the observation windows.

### Flat is now the default building mode

`SCENE_RELIEF.defaultBuildingMode` is `"none"`. Massing was a poor default: every investigation opened with
geometry nobody asked for, fetching tiles nobody requested, over ground that in much of the world has no
footprints at all. Both alternatives stay one click away.

Terrain exaggeration follows the same reasoning — `defaultTerrainExaggeration: 1`, true scale on arrival.
The 2.4× value survives as `boostedTerrainExaggeration`, an opt-in preset for open landscape where a 30 m
DEM holds the only vertical information there is. **"Flat" now means flat**: no buildings AND no vertical
distortion, so nothing on screen disagrees with the measurements beside it before anyone asks it to.

### Watch this — unconfirmed, possibly a regression

On one reload of an investigation URL the camera stayed at globe home (20.6°N 78.9°E, 19,000 km) instead of
descending to the area of interest, even though the record loaded correctly (header and inputs present).
Could not reproduce cleanly — the pane is too slow to drive reliably and HMR churn was in flight during the
edits. **Check the direct-arrival path** (opening a shared investigation link cold) before trusting it.

---

## Session — 2026-08-29 (g) · Tier 3 of the audit

Timelapse export (audit item 15) **dropped on the product owner's call** — heaviest item on the list, and
the archive play-through already shows the same thing live.

### 11 · Reference layers — context that is NOT evidence

`lib/constants/reference-layers.ts` — a curated catalogue: terrain shading, boundaries & places, roads &
transport, all real free Esri services (each verified 200 with the right content type).

The separation is the point. An evidence layer names the model, version and confidence that produced it;
a reference layer names a source and a purpose, because **nothing asserted a coastline**. Different
structures and visibly different rows, so a boundary can never be mistaken for a finding.

`stackPosition` is load-bearing: hillshade is GROUND and goes UNDER the imagery; boundaries and roads are
ANNOTATION and go OVER it, or they are invisible. The stage push is now the stack from the ground up:
`reference.under → timeline base → scene rasters → reference.over → evidence vectors`.

Curated in constants rather than fetched — these are identical for every area on Earth and are product and
licensing decisions, not per-investigation data.

### 12 · Magnitude shading — the attribute was silently disappearing

Extrusion is the primary magnitude channel and **it does not exist in 2D or in draped mode**, so every
change region rendered identically however much changed — dropping the most important number on the
feature. `setMagnitudeShading` graduates the fill (alpha weight plus a brighten above 0.66 magnitude),
turned on exactly when `projection === "2D" || renderMode === "draped"`.

Cheap because the fill is already a `CallbackProperty` — no entity rebuild. The legend switches its wording
to match ("brighter = larger change" vs "taller and brighter"), because a legend describing a channel the
scene is not using is worse than no legend.

Floor of 0.4 on the weight: a small region must stay VISIBLE. Fading it out would hide real evidence for
being small, which is a different statement from showing it as minor.

### 13 · Camera bookmarks — finished a half-built service

`saveCameraBookmark` existed and nothing called it. Now wired: `useInvestigation.saveCameraView`, an
`investigation.saveCameraView` command, a bookmark button in the tool cluster, and the mock **actually
persists** it so a reload genuinely reopens the saved framing.

### 14 · Run history — past answers were unrecoverable

Prior runs were listed, but clicking RE-ASKED: it reran the models and might not reproduce the same
numbers. For a product whose claim is auditability, an answer you cannot return to has not been audited.

`selectedRunId` in the store; null follows the newest. Rows now carry when, how long, confidence and
whether evidence was insufficient, and clicking REOPENS. A banner marks the state and offers "Back to
latest". `startRun` clears the selection so a new run always takes the surface.

### Measurement gotcha that cost real time

`performance.getEntriesByType("resource")` caps at **250 entries** by default, so tile counts silently
under-report once a session has been running. Worse, a static camera with warm caches fetches NOTHING, so
a zero count proves nothing at all.

**Use Cesium's credit list instead** — it includes an entry per imagery layer actually being rendered.
That is what confirmed the reference layers are live ("Esri, HERE, Garmin, USGS, NGA" present).
`performance.clearResourceTimings()` + `setResourceTimingBufferSize(2000)` before a measurement if counts
are needed.

---

## Session — 2026-08-29 (f) · Building render mode switch (massing / photorealistic)

Three-way control in `CameraControls`: **Flat / Massing / Photoreal**, backed by `StageBuildingMode`.

### The trade, which is the whole point

- **Massing** (OSM, Ion asset 96188) — free, grey untextured boxes, sits ON TOP of the operator's imagery
  so the comparator and every raster stay visible. **Unchanged and still the default.** Nothing about the
  analysis path was touched.
- **Photorealistic** (Google) — metered per tile, textured, and it REPLACES the ground. Cesium's guidance
  is `scene.globe.show = false` beneath it, which suspends the scene rasters and the before/after split.
  Draped vector evidence survives only because `evidence-vector-layer` now switches to
  `ClassificationType.BOTH` in that mode.

Presentation mode, not an analysis mode, and the tooltip says so.

### Cost containment

Neither tileset is created until its mode is selected — verified: with Massing active there are **zero
requests to the photorealistic asset**. Switching away hides rather than destroys, so no re-fetch.

### Ion asset 2275207 does NOT work — measured, recorded, do not retry

The obvious route is `Cesium3DTileset.fromIonAssetId(2275207)`, reusing the existing Ion token with no
second key. The token DOES have access (endpoint returns 200 with `externalType: "3DTILES"`), but in
Cesium 1.144 the promise **neither resolves nor rejects and issues no request at all**. Instrumented and
confirmed: the factory is entered, `fromIonAssetId` is called, then nothing.

Switched to the documented `createGooglePhotorealistic3DTileset({ key })`, which needs
`NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` (Google Cloud project, Map Tiles API). The Ion asset id and this whole
finding are recorded in `cesium-runtime.ts` so nobody spends an afternoon rediscovering it.

Without a key the Photoreal button is **disabled with the reason in its tooltip** — never a dead button,
same honesty rule as the massing coverage indicator.

---

## Session — 2026-08-29 (e) · Terrain exaggeration was burying the buildings

The product owner tilted the camera over São Paulo and reported the scene looked like "a photo on a
terrain structure" with no 3D buildings. Correct observation, and it had two causes.

### The bug — exaggerating about SEA LEVEL

`scene.verticalExaggerationRelativeHeight` defaults to **0**, meaning exaggeration scales height about the
ellipsoid, not about the ground. With `verticalExaggeration = 2.4`:

- São Paulo sits at ~760 m → terrain rendered at ~1,824 m, **a kilometre above where it is**
- Everything positioned at TRUE height — 3D Tiles bounding volumes above all — ends up in a different
  vertical frame from the terrain it belongs to
- Result: **zero building content tiles fetched.** Measured, not inferred.

Elevation predicted it exactly: Po Valley (~50 m, 70 m of displacement) loaded tiles; São Paulo (~760 m)
loaded none; the Sahel report was the same symptom.

Fixed by pivoting exaggeration at the local terrain height (`scene.globe.getHeight` at the camera
position). **São Paulo went 0 → 16 content tiles.**

### The product decision — massing and exaggeration are mutually exclusive

They are alternative ways to convey height and they fight each other. In a city the vertical information
is in the BUILDINGS; a 30 m-posting elevation model holds none of it, so exaggerating the ground under
un-exaggerated massing only breaks the relationship between them. In open landscape there are no buildings
and exaggeration is exactly the right tool.

`use-scene-stage-binding` now pushes `hasBuildingMassing ? 1 : terrainExaggeration`. Whichever one is
carrying the height gets to be the one that does.

### Massing colour corrected

`#1B2733` at 0.94 was near-black over dark imagery — invisible, which is no better than not drawing it.
Now `#33414F` at 0.96. The tileset carries normals, so sunlight separates the faces and a mid-tone reads
as volume without out-contrasting the evidence.

### The honest ceiling, worth knowing

Even fully working, this stack is an orthophoto draped on a DEM plus **untextured grey massing boxes**.
Roads, cars and trees are painted onto the surface and always will be. The photoreal 3D city the owner is
picturing is **Google Photorealistic 3D Tiles** (Ion asset 2275207) — a different product with its own
licensing and cost. Not a code change; a decision.

---

## Session — 2026-08-29 (d) · Named analysis operations, and two corrections

Product-owner review of the running workspace raised four things. Three were right.

### Correction 1 — the comparator binding should never have been hidden

I folded Temporal / Cross-modal into the timeline's expand along with the playback speeds. Wrong call: a
playback rate is a preference, but temporal-against-cross-modal changes **what the comparator is showing**,
and a mode switch nobody can see is a mode nobody knows they are in. It is back in the always-visible row
with hints written in terms of what the operator will see. Speeds and the archive query stay behind the
expand — those genuinely are settings.

### Correction 2 — building massing was silently doing nothing

The toggle worked; the AOI was Sahel Transition Zone, Mali. **OpenStreetMap has essentially no building
footprints over farmland, desert or most rural areas**, so the button did nothing and looked broken.

`appearance.subscribeBuildingCoverage` now reports `unavailable | loading | present | none`, measured by
whether any tile carrying content was actually selected for the view (`tileVisible` count at
`allTilesLoaded`) — not by whether the tileset exists, since the tileset is global and its contents are
not. The control dims and says "OpenStreetMap has no building footprints over this area". A control that
does nothing without explanation teaches the operator the feature is broken instead of that the data is
absent.

### The real gap — you could not RUN a named analysis

The Toolbox listed 33 commands, all of them **interface** verbs (toggle layer, sweep, tilt). There was no
way to run change detection, NDVI or segmentation directly — only free text through `ask`. Free text is
the right primary interface and is not a sufficient one: an analyst who knows they want NDVI should not
have to phrase it, and a newcomer cannot ask for a capability they have no way of knowing exists.

**`lib/constants/analysis-operations.ts`** — eight operations (change detection, object detection,
land-cover segmentation, NDVI, NDWI, NDBI, SAR backscatter, area statistics), each declaring its
`requires[]` and its pipeline stage. Requirements are **declared, not enforced by hiding**: an operation
that cannot run shows the reason ("Needs a radar scene attached"), because that teaches something about
the analysis while a missing row teaches nothing.

**`operationId` now travels on `analysisRunRequestSchema`.** This is the contract point: the backend
dispatches the named operation directly instead of classifying intent from a sentence it may read wrong.
The mock already honours it — `selectMockAnalysisScript` takes `operationId` as authoritative and falls
back to keyword sniffing only for genuinely free text, which is exactly the guesswork the field removes.
One pipeline, two ways in: an operation and a typed question produce the same trace.

Also added `investigation.runOperation` so the agent reaches operations the same way the operator does.

### Not a gap — Key Insights already existed

`MetricStat` inside `ClaimCard` already renders claim metrics as animated stat cards; the product owner's
own screenshot showed "18.4% BUILT-UP CHANGE / 68.1 ha AFFECTED AREA / 18 new STRUCTURES DETECTED". A
second headline strip would be a second owner of the same numbers.

### Still open — base and reference layers (audit Tier 3, item 11)

DEM/terrain, land use, administrative boundaries, a basemap switcher and layer REORDERING. These belong on
this page, not another one. The current layer stack holds only analysis products; there is no notion of a
reference layer at all.

### Harness note that cost time

The mock analysis stream paces with `setTimeout` (90 / 130 / 16 ms). A hidden Browser pane clamps every
timer to ~1 s, so a 16-step run takes minutes instead of seconds and looks stalled. It is not — check that
the trace count is still CLIMBING and that evidence layers are arriving before concluding a run failed.

---

## Session — 2026-08-29 (c) · Crash fix, then Tier 2 of the audit

### The crash the product owner hit

`TypeError: Cannot set properties of undefined (setting 'minimumZoomDistance')` — `applyZoomLimits`
running against a destroyed viewer, called from `setMode`, called from `useSceneStageBinding`'s CLEANUP.

**Root cause is structural, not local:** the published handle OUTLIVES the viewer. A feature captures
`stage` in an effect closure; the layout tears the viewer down; the feature's cleanup then calls
`sceneLayers.clear()` and `appearance.setMode("globe")` on a dead scene. Cesium nulls its internals on
destroy, so an unguarded write lands on `undefined` and takes the whole route down.

Guarded `applyZoomLimits`, `setMode`, `setBasemapBrightness`, `sceneLayers.clear/setLayers/setSpotlight/
setAreaOfInterestOutline`, `globeLayers.clear`. **The invariant is now written into the CesiumStage file
header** — any new handle method touching `viewer`, `scene` or `basemapLayer` needs the same guard. That
is the durable part; the guards themselves are the easy bit.

Verified: three navigations in and out of the workspace, zero errors.

### formatPercentage was wrong at every call site

`formatPercentage(value)` did `value.toFixed(n) + "%"` with no multiplication, while **all six callers**
pass a 0–1 ratio (opacity, confidence, magnitude) — so full opacity rendered as "1%". `ConfidenceMeter`
already did `value * 100`, so 0–1 is the codebase convention and the formatter was the outlier. Fixed the
function, not the call sites. Pre-existing bug; my new layer-summary code inherited it and made it visible.

### Tier 2 built

- **Identify / FeatureInspector** — the largest working gap. Clicking a detection used to highlight it and
  say nothing. Now: geometry kind, centroid, area, confidence (null shown as "not asserted", never zero),
  a magnitude bar, model provenance, and the claims it supports. Runs the spotlight relationship
  BACKWARDS through the same graph, so the two directions cannot disagree. Anchored to a corner, not to
  the feature — a card that chases geometry covers the thing being inspected.
- **Layer product stats** — each evidence row now measures itself: feature count, total area, mean
  confidence. Mean is averaged only over features that ASSERT a confidence; treating "not asserted" as
  zero would report a model as less certain than it ever claimed.
- **Sun from acquisition date** — `appearance.setIlluminationTime` sets `viewer.clock.currentTime` to the
  comparison acquisition's capture time. Terrain lighting was already solar-driven, so the shadows on
  screen are now the shadows in the pixels. Not decoration: shadow direction and length are how height is
  read and how a new structure is told from a shadow that moved.
- **`investigation.inspectFeature` command** — the agent counterpart to spotlight.

**Key Insights (audit item 08) was NOT built — deliberately.** `MetricStat` already renders claim metrics
as animated stat cards inside `ClaimCard`. A second headline strip would be a second owner of the same
numbers, which is exactly the duplication this codebase avoids.

### Not verified — needs a human click

The FeatureInspector's TRIGGER could not be exercised headlessly. Cesium's `scene.pick` does not respond
to synthetic PointerEvents in the hidden Browser pane (picking forces a render pass, and the pane renders
at ~1 fps). The handler itself is the pre-existing one that already drove the spotlight — the change is
one added call beside it — but the click path is unproven. **Ask the operator to click a detection.**

### Harness recipe (now complete)

1. `resize_window` to an explicit size — a hidden pane reports a 0×0 viewport, which makes Cesium's canvas
   0×0 and the globe never reach first paint.
2. Reload, then shim rAF to also fire on a 16 ms timer.
3. `window.$RV(window.$RB)` to force React's streaming reveal.
4. Synthetic clicks on the Cesium canvas do NOT pick. DOM-level interaction works fine.

---

## Session — 2026-08-29 (b) · Tier 1 of the workspace audit

The product owner ran the workspace and reported three things: the timeline was rough and over-complicated,
the 3D map had no depth and the camera could not be moved, and the working tools felt thin. All three were
real. An audit was written first (published as an artifact), then Tier 1 of it was built.

### The camera bug — one line, wrong instrument

`viewer.camera.constrainedAxis = Cartesian3.UNIT_Z` was set once in `configureSceneAppearance` and never
released. It pins the camera's up-vector to world Z, which is CORRECT for the orbital globe (north stays up
while the planet turns) and actively wrong at five kilometres over a city, where it fights every attempt to
orbit or tilt around a four-kilometre target.

**It now lives in the mode switch**, released entering scene mode and restored entering globe mode. The two
instruments want opposite things here, which is exactly why it cannot be one-time setup.

Tilt was also not a control at all — Cesium's own tilt is a middle-drag, which does not exist on a
trackpad. `StageCameraApi` gained `orient` / `orbitByDegrees`, which pivot around the framed extent and
**preserve distance to it**, so a tilt is never also a zoom. `CameraControls.tsx` exposes them.

### The depth problem was not the terrain

World terrain was already loading with vertex normals and the Ion token works. The problem was scale: an
AOI is a 4.4 km box, urban relief across it is tens of metres, and at framing altitude that is under one
percent of the view. Geometrically correct, visually flat.

Fixed with the two things that actually carry vertical information in a city:
- **Cesium OSM Buildings** (Ion asset 96188) via `createBuildingMassing()`, styled to a desaturated slate —
  white massing out-contrasts every evidence colour and turns an analysis surface into an architectural
  render.
- **`scene.verticalExaggeration` at 2.4×** in scene mode. Height only; every horizontal position and
  measured area is untouched.
- Minimum zoom 180 m → **55 m**. The Esri basemap resolves to ~0.6 m/px, so there were four zoom levels of
  detail the camera could not reach.

**Gotcha found in testing:** the buildings endpoint was requested three times, because both the mode switch
and the store effect push `setBuildingsVisible` on entry and each call started its own tileset. Guarded with
`isLoadingBuildings`.

### Timeline: the drag was notched because the handle only had committed positions

Selection snaps to acquisitions (right — a date with no pass cannot be shown), but the handle was rendered
from the selection, so it jumped between acquisitions instead of following the finger.

**Now the handle is a DOM node the pointer owns and the selection is React state.** `paint()` is the only
place a handle position is set; the effect that syncs from selection is skipped for whichever handle is
mid-drag. Verified: 11 distinct handle positions across 11 pointer moves, settling onto the real
acquisition on release.

Two more smoothness fixes:
- `RASTER_CROSS_FADE_MS` now has `settled: 420` and `scrubbing: 160`; `isTimelineScrubbing` in the store
  drives the switch through the stage binding.
- Play-through **waits on `sceneLayers.isSettled()`** instead of a fixed clock, capped by
  `maximumSettleWaitMs`. Previously 2× (550 ms) was shorter than the tile fetch, so the fastest speed
  showed the least.

Simplification: **collapsed by default** — axis, two handles, one verdict, step/play. Lanes, speeds, the
archive query and the comparator binding live behind one expand. `TemporalPlaybar.tsx` was **deleted** and
its binding switch absorbed: "what is compared" and "when" are one question.

### Toolbox — the data was already there

`useRegisteredCommands()` already carried title, description, keywords, icon, shortcut and parameter schema
for every action. **33 operations existed and none were visible** unless you opened the palette and guessed
a search term. `ToolboxPanel.tsx` renders the registry — nothing is listed by hand, so it cannot drift.
Commands whose `paramsSchema.safeParse(undefined)` fails are shown but not runnable from a list, labelled
with where the argument comes from (15 runnable, 18 need a target).

Left panel is now tabbed (`LeftPanelTabs.tsx`), both trees stay mounted so collapse state and scroll survive
a tab switch.

### View readout

`SceneReadout` absorbed camera state: position, altitude, a north needle that counter-rotates with heading,
and a **measured** scale bar — two adjacent centre pixels picked against the ellipsoid, not derived from
altitude, so it stays correct under tilt and in every projection. Sampled at 10 Hz in the stage's own update
loop and written straight to the DOM; `StageCameraState` never enters React.

### Decisions worth not relitigating

- Buildings and exaggeration live in the **investigation store**, not read back off the stage. Mirroring
  external state into React on mount tripped `react-hooks/set-state-in-effect` and is a stale-UI bug waiting.
  Pitch is the exception — it changes continuously with a drag, so it is a subscription.
- The mockup's left rail shows change detection / object detection / segmentation as separate MODES. They
  are analysis products arriving as layer descriptors from one pipeline; making them navigation would fork
  the workspace into four near-identical screens. They belong in the Toolbox as operations. The product
  owner agreed.

### Verified

`tsc` clean, lint clean, build green, 5 routes. Driven through the live DOM: tilt OBLIQUE→LOW moved the
camera (9.0 km → 5.2 km at constant range), orbit stepped the heading 22.5°, 16 building tiles loaded from
one endpoint request, scale bar reads 500 m, Toolbox lists 33 operations, compact scrubber down to five
visible controls.

**Harness note:** the Browser pane reports a 0×0 viewport when it is not displayed, which makes Cesium's
canvas 0×0 and the globe never reach first paint. `resize_window` to an explicit size fixes it. Combined
with the rAF shim + `window.$RV(window.$RB)` from the previous session, that is the full recipe for driving
this app headlessly.

**Tier 2 next:** product result cards, identify/attribute inspector, Key Insights strip, sun position from
acquisition date, north arrow done (in the readout).

---

## Session — 2026-08-29 · The timeline scrubber, and the query it composes

Built the temporal scrubber that was deferred last session. The framing that mattered: **it is not a
playback widget, it is the input selector for the whole investigation.** Change detection needs a pair,
and until now that pair was chosen by clicking rows in a list that never showed time — the single decision
that determines the answer, made through the interface least able to inform it.

### The contract change (the part that matters to the backend)

`POST /api/v1/catalogue/search` is new: `{ areaOfInterest, from, to, modalities[], maximumCloudPercentage }`
in; `{ acquisitions[], coverageGaps[], recommendedPair, advisory }` out. This replaces handing the backend
two scene ids someone had picked.

Sending the **window** instead of the **selection** moves the judgement to the side that has the catalogue.
It can now say "there is nothing usable in that window", offer a cleaner pair eleven days away, or be asked
for a series rather than a pair — none of which is expressible once selection has happened upstream. The
area of interest travels with the query, so search, crop, band maths and tiling become one bounded job.

**`recommendedPair` is offered, never applied.** The catalogue sees the archive; the operator sees the
question. An interface that silently substituted the backend's pair would be answering something nobody
asked. It comes with a stated reason and a "Keep mine".

### The analyst judgement, in `lib/timeline-geometry.ts`

Pure, no React, no stage — because everything in it is falsifiable and worth being sure about. `assessPair`
returns a verdict plus **specific notes**, never a score ("0.62 comparability" is not actionable):

- seasonal offset — March against September over farmland is the crop cycle, not a finding. This is the
  one operators most often miss and the most valuable thing the component says.
- cross-modal pairing, resolution mismatch, combined cloud, and too-close separation.

`computeCoverageGaps` is **adaptive** (2.2× the median cadence), not a fixed day count — a gap means
something different for a five-day revisit than for an annual mosaic. Below three usable acquisitions it
returns none deliberately: two points define one interval which is its own median, so the shortage is the
finding and the catalogue's advisory says it in words.

### Decisions worth not relitigating

- **Selection falls back to the role slots** rather than duplicating them. On arrival nothing is chosen and
  the comparator binds exactly as before; the moment a handle moves, `use-timeline` takes over that side.
  That fallback is what made the change additive.
- **Scrubbed imagery is a BASE layer with no provenance block**, not an `EvidenceLayer`. It is the pixels an
  analysis runs on, not a product of one. Fabricating a trace step so it could pose as evidence would put a
  lie in the one structure this product asks people to trust. `useSceneStageBinding` takes `baseLayers` and
  a `comparatorOverride`; a side that cannot resolve (catalogued but untiled) falls back to its slot rather
  than binding to nothing.
- **Handles snap to acquisitions.** A handle resting between two passes implies imagery that does not exist.
- **Deferred removal in `scene-imagery-layer.ts`** — removed rasters are marked `retiringSince` and faded
  out over 420 ms rather than dropped on the frame the replacement is added. Without it every scrub step
  flashes the basemap. Retiring layers keep their `splitDirection`, or the outgoing date spreads across the
  whole scene mid-fade.

### Mock corrections (the mock was lying about itself)

- Role slots are now **derived from generated acquisitions**. They previously named the operator's selected
  scene ids, which were absent from the archive — so the timeline could not resolve either handle. A slot
  naming a scene the archive does not hold is exactly the incoherence the timeline exists to prevent.
- Cadence is genuinely uneven (`ACQUISITION_INTERVAL_DAYS`, two long stretches) — it was one-per-year, so
  the coverage-hole rendering could never fire. Its own comment already claimed otherwise.
- Cloud is **bimodal**, not uniform. Uniform left no clear scenes at either end, so every pair opened
  degraded.
- One shared `choosePair` now picks both the opening pair and the recommendation, and is season-aware.
  Before, the mock handed the operator a pair its own UI immediately criticised.

### Verified

25/25 on a temporary self-test route (since deleted), then driven through the live DOM: opening pair
`FAIR COMPARISON, 2,903 days apart`; stepping to a SAR date flips it to `DEGRADED` with the cross-modal and
10 m-vs-20 m notes; archive search returns 3 coverage holes distinguishing "every pass exceeded 40% cloud"
from "no acquisition over this area"; "Use it" restores the fair pair; play-through wraps and steps. Tiles
confirmed loading from Ion, EOX and Esri. `tsc` clean, lint clean, build green, 5 routes.

**Harness note, still true:** both browser tools put the tab in `visibilityState: "hidden"`. React never
hydrates because its boot is queued behind rAF. Workaround that works — inject an rAF shim that also fires
on a 16 ms timer, then call `window.$RV(window.$RB)` to force the streaming reveal. Screenshots remain
impossible unless the user displays the pane; DOM inspection is the substitute and is real evidence.

**Still unbuilt:** confidence hatching (spec §4.7), pages 3/4 as workspace modes, voice adapter, deck.gl,
camera-bookmark persistence (`saveCameraBookmark` exists, nothing calls it).

---

## Session — 2026-08-27 (b) · Analyst tooling, and finally getting eyes on it

The product owner ran the workspace and reported five things wrong. All five were real, and four of them
were **gaps rather than bugs** — features the design named and I had not built.

### The tooling problem, and what it actually was

Neither browser tool could show a live render. Both the in-app pane and the Chrome extension put the tab
in `visibilityState: "hidden"`, which starves requestAnimationFrame. Three consequences, and it took
disproving two wrong theories to find the real one:

- Cesium's render loop never runs, so the scene never paints and readiness never fires.
- **React's streaming reveal is queued behind rAF** (visible as the injected `$RT` script). The real page
  sits in a hidden `div#S:0` staging container while `app/loading.tsx` stays on screen.
- CDP screenshots return the last composited frame, so they are stale rather than wrong.

Two false alarms disproved along the way, both checked before reporting: the panels were NOT invisible
(`opacity: 1`, animation finished, 320×873, full live content — 5,000 catalogue scenes), and Mission
Command's panels appearing at an investigation URL were inside the hidden staging div, not a stale tree.

**The one genuine product bug this surfaced:** a workspace opened in a background tab never reached first
paint, so an operator switching to it later found it still saying "initialising". Fixed in `CesiumStage`
by driving `viewer.render()` from a timer while hidden — but **only until the first frame**, then
stopping. A hidden tab has nothing to show anyone, and rendering a full globe on a timer forever would
burn a battery for no one.

### What was built

**Drawing, rewritten.** It was rectangle-drag only. Now `region-draw.ts` is a real geometry engine:

| | |
|---|---|
| Shapes | rectangle, polygon, freehand, circle — four because they answer different questions |
| Measurement | distance, area, bearing, committing labels onto the scene |
| While drawing | rubber-band preview, live geodesic area/length/bearing, vertex count, cursor lat-lon |
| Keyboard | Enter completes, Backspace undoes a vertex, Escape cancels |
| Regions | multiple at once, one ACTIVE scoping the next question, listed with measured area |

Two details worth keeping. Camera input is disabled for the duration of a draw and restored through a
single `endSession()` that every exit path routes through — the previous version could leave the camera
dead after the operator gave up. And area is **geodesic, measured from the committed vertices**, because
that number is what the backend crops to and what the answer quotes.

**True 2D.** `StageProjection` = 3D / columbus / 2D, morphing rather than cutting. 2D is not a
convenience: in perspective every polygon edge is foreshortened by an amount that depends on where it
sits on screen, so tracing accurately is guesswork. This is the direct answer to "pull a 2D map so the
backend can receive good data".

**Detached pop-out windows** — the option the owner picked over cards or a filmstrip. `/scene/[sceneId]`
is a standalone route **outside** the geospatial group, so a window whose job is one picture does not
boot a WebGL globe. One window per scene, reused on re-click. Role assignment travels back by
postMessage, origin-checked and shape-validated — a window handle is not a reason to trust its messages.

**N-date acquisition stack.** `investigation.acquisitions[]` — the contract change that makes a timeline
possible at all. An investigation is a time series a pair is currently selected from, not a pair. Mock
generates nine acquisitions with real quicklook tiles derived from the scene's own tile source, including
unusable high-cloud ones, because a coverage gap is information.

**Also:** evidence legend (a scene of coloured geometry that never says what the colours mean is a
picture, not evidence), acquisition history list, region list, scene readout.

### Still missing — be honest about this

- **Timeline scrubbing is NOT built.** The owner chose analysis depth first and this was explicitly
  deferred. The contract (`acquisitions[]`) is in place so the component can be built without another
  schema change.
- **Confidence hatching** — designed in `03-2ndPage.md` §4.7, still unbuilt.
- **Not visually verified.** Build green, types clean, lint clean, five routes serve, and the full
  click-through flow was verified through the DOM earlier. Nothing animated has been *watched*.

**Next session: get the tab fronted first.** Everything else is guesswork until then.

### Backend additions this session

- `GET /api/v1/imagery/:sceneId` → acquisition, quicklook, bands, AOI context. Feeds the pop-out window.
- `POST /api/v1/investigations/:id/scenes` → `{sceneId, role}`, returns the **updated investigation**, not
  an acknowledgement. Re-fetching after a role change leaves a window where the layer stack and the
  comparator disagree about which scene is T1.
- `investigation.acquisitions[]` on the detail response, oldest first, each with `quicklookUrl` and
  `isAvailable`.

---

## Session — 2026-08-27 · Page 2, the Investigation Workspace

Built the Investigation Workspace end to end, plus the refactor it depended on. The design that preceded
it is `fcontext/feature-spec/03-2ndPage.md`; the product owner approved it with "go ahead", delegating the
five open decisions. Those were resolved as: shared stage **yes**, answer surface **yes**, pages 3 and 4 as
modes of this workspace **yes** (architected for, not yet built), present mode **yes**.

### The load-bearing change: one Cesium viewer, owned by a route group

`app/(geospatial)/layout.tsx` now mounts `<GeoStage />` beneath `{children}` for both `/` and
`/investigation/*`. Route groups do not appear in the URL, so no path changed.

This was the whole reason the refactor was necessary. Next.js unmounts a page's tree on navigation, so a
viewer owned by Mission Command dies mid-flight and the globe→AOI descent degrades to freeze → boot a
second WebGL context → cross-fade. That is the *simulated* continuity the previous session rejected when
it declined the MapLibre split; reintroducing it here by accident would have been absurd.

**The cesium import boundary moved, it did not weaken:**

> ~~`features/missionCommand/components/globe/`~~ → `components/sharedUI/functionalComponent/geoStage/`

`architecture-context.md` is updated. The globe's marker and arc layers relocated there unchanged.

**Mission Command's blast radius from the refactor was small but not zero**, and the honest version is
more useful than the flattering one:

| File | Change |
|---|---|
| `MissionCommandScreen.tsx` | No longer renders `AppShell` or the globe; the layout owns both. Gained the Investigate handler. |
| `DataContextPanel.tsx` | Gained the Investigate action and two props. |
| `CesiumGlobe.tsx`, `GlobeViewport.tsx` | Deleted, replaced by `CesiumStage.tsx` / `GeoStage.tsx`. |
| `GlobeControls.tsx`, `use-mission-command-commands.ts`, the stores, the panels | **Untouched.** They still talk to `GlobeViewerHandle`, which is now produced by an adapter hook. |

That adapter — `use-globe-stage-binding.ts` — is what kept the untouched column long. It is the only
place Mission Command reaches the stage.

### What the stage is now

Two modes, because it is two instruments. `globe` is orbital: markers, arcs, idle rotation, orbital zoom
limits. `scene` is close-range: operator imagery, evidence geometry, the comparator, tight limits, and a
recessed basemap. Switching is a method call — nothing about the transition touches WebGL.

Grouped API, so each surface's dependency is legible at the call site: `camera`, `globeLayers`,
`sceneLayers`, `comparator`, `regionDraw`, `appearance`.

New modules under `geoStage/`: `scene-imagery-layer.ts` (raster add/fade/split — layers are added and
cross-faded, never swapped, because a swap shows the black globe for one frame),
`evidence-vector-layer.ts` (clickable, extrudable, spotlightable geometry), `aoi-outline-layer.ts`,
`split-comparator.ts`, `region-draw.ts`.

### Three decisions worth keeping

**1. Layers are data, not components.** A layer arrives as a descriptor; one factory maps `kind` → Cesium
primitive. Adding a flood mask, a backscatter difference or a confidence field means the backend emits one
more descriptor and **zero frontend files change**. Without this the codebase grows linearly with the
science, and pages 3 and 4 could not be configurations of page 2.

**2. `renderMode` is not a boolean.** Cesium's `ClassificationType.TERRAIN` drapes a polygon onto terrain
and *cannot* be extruded; extrusion needs an absolute-height polygon, which is not classified. The
volumetric toggle rebuilds geometry. This was flagged as "verify at build time" in the design doc and is
now confirmed in code.

**3. Streaming state splits in two.** Trace steps, answer tokens and run status are the client-side fold
of an in-flight operation and live in `investigation-store`. Layers, evidence and claims are server state
and go into the **query cache**, mutated incrementally by the stream. `layer-ready` is a separate event
from `trace-step` on purpose: the change mask must reach the scene the moment it exists, not when the run
finishes.

Two shapes never enter React state — the **camera pose** and the **comparator split position**. Both
change every frame; the stage owns them and DOM handles subscribe.

### The command bus paid for itself again

Every workspace affordance dispatches through `investigation.*`. Three consequences, all intended:

- The autonomous investigation is **not a special code path** — it is a sequence of the same commands, so
  the machine presses the buttons a human would and the two modes cannot drift.
- Voice needs **no new UI**: the vocabulary IS the command list. Sweep, show me the change, zoom to the
  biggest change, why, generate a report — one command each.
- `listCommandDescriptors()` already serialises the workspace to JSON Schema for the agent layer.

### Verified this session

`tsc --noEmit` clean · `eslint` clean (one pre-existing benign React-Compiler warning on the virtualiser)
· `next build` succeeds, four routes emitted.

**Mock↔schema contract, 13/13** via a temporary self-test route (since deleted). It checked more than
"does it parse": every claim resolves its cited evidence, every evidence item resolves its features, every
inspectable trace step resolves to a real layer, a full 42-frame run validates against the stream union,
and the quoted hectare figure agrees with the polygons actually drawn to within 0.01 ha.

**Full flow, live, via client-side navigation:** select scenes → Investigate → route change to
`/investigation/inv_…` → workspace renders (identity strip with copyable trace id, three scene slots,
tool cluster, split handle, answer composer) → ask a question → stream delivers 16/16 trace steps, four
evidence layers (two visible, two artefact-only), three claims at 91% confidence with `model@version`
stamps, and the "Investigate further" call to action. Zero console errors.

### Two real bugs found and fixed by testing

1. **`useCountUp` froze at zero in a background tab.** rAF does not fire when hidden, so an operator who
   tabbed away mid-answer would return to `0.0 ha` displayed with full confidence — a wrong number in a
   product whose entire claim is that its numbers are trustworthy. Now backed by a timer, which fires when
   hidden, so the value always reaches its target whether or not it got to animate there.
2. **Reloading an investigation URL 404'd.** The design commits to the URL *being* the investigation, and
   the in-memory mock store made that false in Phase 1. Mock investigations now persist to
   `sessionStorage` (mock-only code, deleted with the folder in Phase 2).

### Two false alarms, checked before reporting

- `·` rendering as mojibake in test output was **my Windows console** (cp1252), not the app. The raw bytes
  are `c2 b7`, correct UTF-8. Same class of false alarm as the previous session — verified with `xxd`
  this time rather than assuming either way.
- Mission Command's panels appearing in the DOM at `/investigation/…` were inside `div#S:0`, Next.js's
  **hidden streaming staging container** (`display:none`). The live tree contained only the workspace.

### Still outstanding — read this before trusting any visual claim

**Nothing animated has been seen rendering.** The Browser pane has been collapsed for every session, and
this session finally identified the exact mechanism: React's streaming reveal is queued behind
`requestAnimationFrame` (visible as the injected `$RT` script), which never fires in a hidden tab. A
manual rAF→setTimeout shim in the console confirmed the stall is entirely the harness — content revealed
immediately once frames were simulated.

So these remain **unverified visually**: the Cesium canvas itself, the globe→AOI descent, the comparator
sweep, the evidence bloom, volumetric extrusion, the target-lock overlay, and the spotlight dimming.
They compile, they lint, they are wired, and their data paths are tested. They have not been watched.

**Do this first next session:** open the Browser pane, load `/`, select scenes, press Investigate, and
watch the descent.

### Message for the backend developer

The tile contract from the previous session stands. New requirements from this surface:

1. **`layer-ready` must be its own SSE event**, separate from `trace-step`. The viewer draws a layer the
   moment it exists. This is the single most important line in the analysis contract.
2. **Every trace step carries its artefact URI** where the stage produced one. The provenance
   requirements already oblige retaining those intermediates, so this costs a URI you already hold and
   buys the operator the ability to click any stage and see what the machine saw.
3. **Every evidence polygon carries** `areaHectares`, `magnitude`, `confidence`, `modelId`,
   `modelVersion`, `traceStepId`. Magnitude drives extrusion; the rest drive the layer row.
4. **Masks need both representations** — raster tiles for display *and* vector geometry for evidence.
   Raster alone gives a picture; geometry gives a clickable, auditable answer.
5. **Confidence stays `number | null`.** Null means AERIS declines to assert, and renders as a refusal
   card offering alternatives — never as zero.
6. **`POST /api/v1/investigations` must return fast.** The camera is already flying when it resolves; a
   slow create turns a continuous descent into a stall. Heavy work belongs in the run that follows.

Endpoints added: `/investigations` (create + list), `/investigations/:id` (get + patch),
`/investigations/:id/runs` (SSE), `/investigations/:id/evidence`, `/investigations/:id/plan`,
`/investigations/:id/report` (SSE + `.pdf`/`.json`/`.geojson`), `/regions/suggestions`.

### Phase 1 stand-in imagery — replace, do not copy

T0 and T1 point at two genuinely different public sources of the same ground (an EOX Sentinel-2 cloudless
mosaic and Esri World Imagery) so the comparator reveals a real difference. Two renderings of the same
picture would have proved nothing. SAR is Esri imagery with `sar-grayscale` grading — an honest stand-in,
not radar. All three are replaced by backend TileJSON in Phase 2 and nothing else changes.

### Deferred, deliberately

- **Pages 3 and 4** ship as workspace modes (`comparatorBinding`), not new components. The binding table
  is already in `lib/constants/investigation.ts`.
- **Voice** — the microphone renders and is explicitly disabled with a tooltip. The adapter is ASR →
  intent → `dispatchCommand`; the command set is the vocabulary and needs no UI work.
- **deck.gl** — still uninstalled. The trigger is unchanged: GPU aggregation, 100k+ vectors, or animated
  attribute transitions. Vector evidence currently renders as Cesium entities, which is right for the
  tens-to-hundreds of polygons a change run produces and wrong past roughly a thousand.
- **Camera bookmark persistence** — `saveCameraBookmark` exists and is wired to a PATCH; nothing calls it
  yet. It should fire on an explicit save, never on camera movement.

---

## Session — 2026-08-26 (c) · First visual review, and what it changed

The product owner ran the page and sent a screenshot — the first time anyone had seen this rendered.
Four problems, all real, all fixed. Recording them because three were design errors, not bugs.

**1. Marker confetti.** ~2,000 markers drawn at full size at every altitude buried whole continents under
overlapping blobs. Two causes: no level of detail, and a stress-test marker count shipped as the resting
default.

Fixed with GPU-evaluated LOD in `mission-marker-layer.ts` — each marker carries a
`DistanceDisplayCondition` whose range is status-first (`alert` 60,000 km → `archived` 2,500 km) and
magnitude-modified, plus `scaleByDistance` and `translucencyByDistance`. From orbit you now see alerts and
active investigations; routine monitoring reveals itself as the camera descends. Base pixel size dropped
from 7–16 px to 4.5–9 px before distance scaling, and `NEXT_PUBLIC_MOCK_MARKER_COUNT` went 2,000 → 300
(the knob survives for stress-testing; density is governed by the LOD rules, not the count).

**The lesson worth keeping:** a globe that renders every observation at every altitude communicates
nothing. Density has to be a function of camera distance and importance, or it is noise.

**2. Dead arcs.** They were static `PolylineGlow` — Cesium's stock material has no notion of position
along the line over time, so there was never going to be motion. Replaced with a custom Cesium material
whose shader runs over `materialInput.st.s` (the 0→1 coordinate along each polyline), producing a
travelling comet. Per-frame cost is one float uniform per arc; the pulse itself is GPU-side. Each arc
carries its own phase so they do not fire in unison. Apex ratio also dropped 0.16 → 0.08, which puts a
hemisphere-crossing pass near true low-Earth-orbit altitude instead of throwing decorative rings around
the planet.

**3. A washed-out Earth.** The imagery grading was far too aggressive — brightness 0.72, saturation 0.55 —
which drained the planet to a grey relief map. That was solving the wrong problem: it dimmed the whole
Earth to make markers readable. Marker prominence is the LOD system's job. Now brightness 1.02,
saturation 1.18, plus `scene.atmosphere` hue/saturation/brightness shifts and
`DynamicAtmosphereLightingType.SUNLIGHT` so the atmosphere responds to the sun rather than glowing
uniformly.

**4. The marker legend was hidden behind the data panel, and the panel's sections overlapped.**

The legend was anchored `bottom-4 left-4` against the *viewport* — permanently underneath the Data &
Context panel. `GlobeControls` now renders into the overlay's centre column (the free space between the
panels) instead, with legend and controls sharing one bottom row so they cannot collide with each other
either. It also derives its own readiness from `globeViewer !== null` rather than taking a prop, which
removed the plumbing through `GlobeViewport`.

The section overlap was a flex arithmetic bug: the mission list had a fixed `basis-[38%] shrink-0`
alongside a `flex-1` catalogue, which can exceed the panel height. Both lists are now collapsible and
claim flex space **only while expanded** (`min-h-0 flex-1` expanded, `shrink-0` collapsed). That fixed
the overlap and delivered the requested collapse controls in the same change — collapsing one list hands
its height to the other. Collapse state lives in `mission-command-store`; `SectionHeader` gained an
optional `onToggle`/`isExpanded` pair that turns it into a toggle.

**Note when changing `.env`:** `NEXT_PUBLIC_*` values are inlined at compile time. If marker density looks
unchanged after pulling this, restart the dev server.

---

## Session — 2026-08-26 (b) · Geospatial engine decision: CesiumJS (one engine until it hurts)

### The decision and why

**CesiumJS owns the Earth and the analysis surface. deck.gl is added later, as an overlay, only where
Cesium genuinely falls short. The backend owns all computation.**

The previous session shipped a stylised react-three-fiber globe. It was rejected, correctly: for an
Earth-observation product the home globe is not decoration, it is the index into the imagery. A dot-matrix
sphere cannot be zoomed into, is not georeferenced, and cannot show real land.

Rationale recorded by the product owner:
- The core idea is making the operator **feel** how a place has changed, not merely reporting that it did.
  That is a rendering problem, and it is where deck.gl earns its place.
- Cesium supports 2.5D / true 3D, so terrain-aware and extruded presentations stay open.
- Visual distinctiveness is a competitive requirement (SIH), not a nice-to-have. "Another Google Maps" is
  an explicit non-goal.

**The division of labour is a hard rule:** all mathematics, reprojection, band math, tiling and model
inference happen in the **backend**. The frontend renders and creates the experience. If the frontend is
ever computing NDVI or reprojecting a raster, something has gone wrong.

### What this changed — and, more usefully, what it did not

The `GlobeViewerHandle` adapter written in the previous session largely paid for itself. An entire
renderer was replaced and the blast radius stayed tiny — but be precise about what "tiny" means, because
the honest version is more useful than the flattering one.

**Structurally untouched** — never imported a renderer, so nothing changed:
`mission-command-store`, the assistant and data panels, the whole shell, `GlobeLoadingState`, and the
`GlobeViewport` mount/WebGL-probe logic.

**Changed, and worth understanding why:** two verbs on the handle had to change units, because Cesium
works in real-world measurements and the react-three-fiber globe worked in abstract radii.

| Before (R3F) | After (Cesium) | Why |
|---|---|---|
| `flyTo({ distance })` — globe radii | `flyTo({ altitudeMeters })` | An altitude is something an analyst can reason about; a radius multiplier is not |
| `zoomBy(delta)` — additive | `zoomByFactor(factor)` — multiplicative | A fixed metre step that feels right at street level is imperceptible from orbit |

That rippled into exactly three call sites — `GlobeControls`, `MissionCommandScreen`, and the
`globe.flyTo` command schema. Three small edits for a total renderer swap is the adapter working, not
the adapter failing; but the interface was *not* literally unchanged, and the next person should not
expect a future swap to be entirely free either.

**Keep this discipline.** No file outside `components/globe/` may import `cesium`. When the deck.gl
overlay lands, no file outside that folder may import `@deck.gl/*` either.

**Removed:** `three`, `@react-three/fiber`, `@react-three/drei`, `d3-geo`, `topojson-client`,
`world-atlas` and their types; the land-mask sampling pipeline (`globe-geometry.ts`, `use-land-dots.ts`,
`globe-assets.service.ts`, `public/geo/land-110m.json`); the five R3F scene layers. Cesium provides real
land, so sampling coastlines into a point cloud is obsolete.

**Added:** `cesium@1.144.0`. Its static runtime assets (`Assets`, `ThirdParty`, `Widgets`, `Workers`,
~7.8 MB) are copied to `public/cesium` by a **postinstall script** and served statically — they are not
bundled. `window.CESIUM_BASE_URL` must be set before a `Viewer` is constructed.

**Removed on request:** the entire `features/notifications` module, its store, mock data, query keys and
the `/api/v1/notifications` endpoint. It was built from `design_report.md` §3, which lists a notification
bell in the header, but the PDF tiers monitoring/alerts as later scope. Monitoring is not being built, so
the bell is gone. `AppShell`'s `headerActionsSlot` prop is intentionally kept — it is the shell's
documented extension point and later surfaces will use it.

### Locked: one engine. MapLibre + deck.gl was evaluated for page 2 and declined.

The question raised was whether to split engines — Cesium for the 3D globe (page 1), MapLibre + deck.gl
for the Investigation Workspace (page 2). It works technically: separate routes, separate WebGL contexts,
no conflict. It was declined anyway, for two reasons.

**1. Cesium already covers the Investigation Workspace's critical path natively.** Verified against the
Cesium 1.144 type definitions:

| Page 2 needs | Cesium native |
|---|---|
| Display the operator's scene (COG/XYZ tiles) | `UrlTemplateImageryProvider` |
| Overlay a change-mask raster | second imagery layer with alpha |
| Evidence polygons, clickable, draped on terrain | `GeoJsonDataSource` + `ClassificationType.TERRAIN` |
| Extrude change polygons by magnitude (2.5D) | `extrudedHeight` |
| **Before/after swipe slider** | **`splitDirection` + `scene.splitPosition` — built in** |
| Timeline scrubbing over a temporal stack | `viewer.clock` + time-dynamic imagery |
| Detection boxes | entities |

The swipe slider is the headline. For change detection it is *the* interaction — drag a handle, watch T0
become T1 under the cursor — and it is the most direct expression of "feel how it changed" available.
Cesium gives it as two properties; MapLibre has no equivalent and would need hand-rolled clip masks.

**2. Splitting engines makes the cinematic transition harder, not easier.** With one engine, globe → AOI
is a single continuous camera animation — seamless because it *is* one camera. With two it becomes
freeze → cross-fade → boot the second engine at a matched view → fade in. That is *simulated* continuity,
requiring an altitude→zoom conversion (Cesium metres onto MapLibre's log2 0–22 scale), matched
bearing/pitch, and two basemaps that look alike at the cut. Achievable, but real engineering spent on
precisely the moment that matters most.

Plus the ordinary tax: two camera models, two picking systems, two tile configs, two styling systems,
two upgrade paths — every geospatial feature built or abstracted twice.

**The strongest argument for the split, recorded so it is not lost:** `@deck.gl/mapbox`'s `MapboxOverlay`
works with MapLibre and gives *interleaved* rendering — deck.gl layers slot into the map's own layer
stack, correctly z-ordered. That is genuinely better than anything available on Cesium. If page 2 ever
turns out to be deck.gl-heavy rather than raster-heavy, revisit this.

### Where Cesium genuinely falls short — the three gaps to expect

None of these block anything, and none require replacing Cesium. Each is solved by adding deck.gl as a
camera-synced overlay *on* Cesium, when and only when it actually bites:

1. **GPU aggregation** — heatmap, hexbin, screengrid. Cesium has no native equivalent.
2. **Very large vector sets** — 100k+ features. Primitives help; nothing approaches deck.gl's scale.
3. **Rich animated attribute transitions** — deck.gl's `transitions` prop and `TripsLayer`. Cesium can
   animate, but manually.

**Caveat on all of the above:** this is API-level verification — the symbols exist and are documented for
these uses. The Investigation Workspace has not been built with them, and nothing in this project has
been visually verified yet. Well-grounded, not demonstrated.

### The honest risk: deck.gl + Cesium is not a first-class integration

This must be recorded, because it is the one place this stack has real friction.

deck.gl ships official overlays for Mapbox/MapLibre, Google Maps and ArcGIS. **There is no official
`@deck.gl/cesium`.** The workable pattern is a transparent deck.gl canvas layered above Cesium's canvas,
with Cesium's camera converted to a deck.gl `viewState` every frame.

Consequence to design around: **no depth interleaving with terrain.** deck.gl layers draw on top of the
scene rather than being occluded by mountains. For nadir satellite overlays this is usually what you
want anyway — an analyst wants the change mask visible, not hidden behind a ridge — but it means deck.gl
is the wrong tool for anything that must sit *within* the 3D scene.

**Therefore: do not force deck.gl everywhere.** Split by what each engine is actually good at.

| Use Cesium natively for | Use deck.gl for |
|---|---|
| Scene imagery tiles (`UrlTemplateImageryProvider`) | Animated temporal transitions — the "feel the change" moment |
| Change masks draped on terrain (`classificationType: TERRAIN`) | GPU aggregation: heatmap, hexbin, screen grid |
| Terrain, 3D Tiles, sky, atmosphere, lighting | Very large vector sets where Cesium entities would stall |
| Camera, fly-to, picking | Arc / trips / flow layers |

Cesium's terrain-draped polygons are genuinely excellent and are probably the right renderer for change
masks — do not reach past them for deck.gl out of habit.

### Basemap and terrain — read this before wondering why the Earth looks flat

Cesium's high-resolution imagery and world terrain come from **Cesium Ion**, which needs a free token.

- **`NEXT_PUBLIC_CESIUM_ION_TOKEN` set** → Ion world imagery + `createWorldTerrainAsync()`. Real satellite
  Earth with real elevation. This is the intended experience and the source of the wow factor.
- **Token absent** → CARTO dark raster basemap via `UrlTemplateImageryProvider` + `EllipsoidTerrainProvider`.
  Real coastlines and real geography, but flat, and styled to match the AERIS palette.

The fallback exists so the app never boots to a black sphere. **Get a free Ion token from
ion.cesium.com** — the free tier is generous and it is what turns this from a map into the product.

Later, terrain can be self-hosted: the backend would serve **quantized-mesh** tiles with a `layer.json`,
not raw DEM rasters.

### Message for the backend dev — what Cesium changes about the tile contract

The COG + TiTiler plan stands. Cesium adds specific, non-negotiable requirements:

1. **Tiling scheme.** Serve XYZ in **EPSG:3857 (WebMercatorQuad)** — TiTiler's default — or EPSG:4326 with
   `tilingScheme` declared. Do not invent a custom scheme.
2. **CORS is mandatory.** Cesium fetches tiles cross-origin from a canvas; without
   `Access-Control-Allow-Origin` the globe silently renders nothing. This is the most common first-day
   failure.
3. **Alpha channel required.** Serve PNG or WebP **with transparency** so nodata is transparent. An opaque
   black rectangle around every scene destroys the composite.
4. **Send `bounds`, `minzoom`, `maxzoom`.** TiTiler's TileJSON already carries these. The frontend maps
   them to Cesium's `rectangle` and `maximumLevel` so it never requests tiles outside coverage — without
   them Cesium hammers the tiler with 404s across the whole planet.
5. **Masks need two representations.** Raster tiles for display *and* vectorised **GeoJSON polygons** for
   evidence. The polygons are what make a claim clickable and what Cesium drapes onto terrain. Raster
   alone gives a picture; polygons give an auditable answer.
6. **Every evidence polygon needs numeric properties** — `areaHectares`, `magnitude`, `confidence`,
   `modelId`, `traceId`. Magnitude drives **2.5D extrusion**: extruding change polygons by how much
   changed is the single most direct way to make an operator *feel* the change rather than read it.
7. **Elevation/terrain**, if self-hosted later: quantized-mesh + `layer.json`.
8. Band selection and stretch stay **server-side**, requested through TileJSON query parameters
   (`?bands=4,3,2&rescale=0,3000`). The browser must never do band math.

Endpoints unchanged from the previous session's table, minus `/api/v1/notifications`, which is deleted.

### What is built right now

Mission Command Center page 1: shell (rail, header, command palette), Data & Context panel (upload,
virtualised catalogue, virtualised missions, model fleet), AERIS Assistant panel (streamed answers, live
execution trace, confidence), and the Cesium globe.

Globe internals, all inside `components/globe/`:

| File | Responsibility |
|---|---|
| `cesium-runtime.ts` | `CESIUM_BASE_URL`, Ion token, imagery/terrain providers for both paths |
| `CesiumGlobe.tsx` | Viewer lifecycle, scene look, input, idle rotation, publishes `GlobeViewerHandle` |
| `mission-marker-layer.ts` | One `PointPrimitiveCollection`; alert-only pulse; pick → marker |
| `satellite-arc-layer.ts` | Glowing arcs sampled from a true `EllipsoidGeodesic` |
| `GlobeViewport` / `GlobeControls` / `GlobeLoadingState` | Unchanged from the R3F build |

Scene configuration worth knowing: real sun lighting (day/night terminator), ground and sky atmosphere,
`depthTestAgainstTerrain = true` so far-side markers are correctly occluded, markers floated 4 km above
the surface so terrain never swallows them, imagery graded down (brightness/saturation) so AERIS overlays
stay the brightest thing on screen, and `resolutionScale` capped.

### Verified this session

`tsc --noEmit` clean · `pnpm lint` clean (one benign React-Compiler warning on the virtualiser) ·
`pnpm build` succeeds · page server-renders the full shell · all Cesium runtime assets serve from
`/cesium/*` (workers, WASM, widgets CSS, textures, terrain heights all HTTP 200).

Note for whoever probes those assets next: Cesium 1.144 bundles its workers as hashed chunks. The old
`Workers/cesiumWorkerBootstrapper.js` and `ThirdParty/Workers/z-worker-pako.js` filenames no longer
exist — a 404 on those is stale documentation, not a broken copy.

### Still outstanding

- **Visual verification has never happened.** The Browser pane has been collapsed for every session so far
  (`document.visibilityState === "hidden"`, so the client script never runs past the Suspense fallback and
  screenshots cannot composite) and the Chrome extension is not connected. Nobody has seen any of this
  rendered. Do this before building anything on top of it.
- **Set `NEXT_PUBLIC_CESIUM_ION_TOKEN`.** Without it the globe is real geography but flat and dark-styled.
  With it, it is satellite Earth with real elevation. This is the single highest-value five-minute change
  available right now.
- deck.gl is **not yet installed**. Deliberately deferred to the Investigation Workspace, where the
  analytical layers actually live — installing an unused renderer now would be dead weight.
- Arc travel animation: arcs currently glow but do not have a travelling pulse. Cesium's stock
  `PolylineGlow` material is static; animating it needs a custom material or per-frame updates.
- Cinematic globe → scene handoff, once there is a scene viewer to hand off to.

### Deferred, deliberately (not forgotten)

- Audio feedback for critical actions — needs assets and a settings surface.
- Real satellite TLE trajectories — arcs are currently synthetic great-circle tracks.
- Voice input — the microphone is rendered and explicitly disabled with a tooltip rather than hidden.

---

## Session — 2026-08-26 (a) · Mission Command Center (Page 1), Phase 1

### What was built

**Design system.** `app/globals.css` is the single source of truth for colour, radius, shadow and motion.
The prior state had the AERIS palette in `@theme` but left shadcn's semantic tokens (`--primary`,
`--card`, `--border`, `--sidebar-*`) at stock neutral grey, so every shadcn component rendered grey.
Those are now composed from the palette, and the stock light `:root` block was removed as a first-paint
flash risk. Single dark theme. Typography: Geist Sans + JetBrains Mono.

**Application shell** (`components/sharedUI/functionalComponent/appShell/`) — `AppShell`, `AppHeader`,
`NavigationRail`, `PanelContainer` (glass, collapsible, drag-resizable), `CommandPalette`. Built once,
inherited by all seven surfaces. The rail reads `lib/constants/navigation.ts`; unbuilt surfaces render
dimmed rather than linking to a 404. **Flip `isAvailable` there when a page ships.**

**Mission Command Center** (`features/missionCommand/`) — three zones over a full-bleed globe.

### Verified

`tsc --noEmit` clean · `pnpm lint` clean · `pnpm build` succeeds · page server-renders · zero console
errors · mock transport active.

Scalability measured against the real data layer at 5,000 scenes / 2,000 markers: generate catalogue
131 ms once (cached), first page 0.21 ms, page at cursor 4900 **0.02 ms** (constant time — cursor
pagination does not degrade with depth), search across 5,000 → 1,473 matches in 3.9 ms, marker projection
1.67 ms.

### Rules established that still hold

1. **The mock seam is one line.** `/mock` is the only place mock data exists. Services, hooks, stores and
   components contain zero mock awareness. Phase 2: delete `/mock`, then delete the marked block in
   `lib/providers/app-providers.tsx`. TypeScript fails on exactly that line, so mock data cannot survive
   the migration. Never add `if (useMock)` branches anywhere else.
2. **The command bus is the agent seam.** Every interactive affordance dispatches through
   `lib/command-bus` with a Zod parameter schema and a plain-language description.
   `listCommandDescriptors()` already emits JSON-Schema tool definitions, so the agent/voice layer needs
   no UI rewiring. Adding a button means registering a command, not adding a bare `onClick`.
3. **Imperative handles live in the feature store, not in refs** — so commands can reach them from
   outside React. Read with `getState()` at call time; always guard for null.
4. **Do not virtualise the assistant transcript.** Plain scroll container with `content-visibility` on
   completed turns, on purpose — heights change while streaming and a virtualiser re-measuring jitters.
5. `components/ui/**` and `hooks/use-mobile.ts` are excluded from lint as generated foundation code the
   workflow rules forbid modifying.

### Backend contract (unchanged except where the Cesium session amends it)

| Endpoint | Notes |
|---|---|
| `GET /api/v1/imagery` | **Cursor** pagination (`cursor`, `limit`, `search`) → `{items, nextCursor, totalCount}`. Offset pagination breaks under concurrent ingest. |
| `POST /api/v1/imagery/upload-ticket` | `{sceneId, uploadUrl, expiresAt, requiredHeaders}`. Files go **direct to storage**, never through the app server. |
| `POST /api/v1/imagery/:id/confirm` | Called after the storage PUT succeeds. |
| `GET /api/v1/missions` | Cursor paginated. **Order server-side** (alerts first, then recency); the client deliberately does not re-sort. |
| `GET /api/v1/globe/markers` | Whole collection, not paginated — uploaded to the GPU as one buffer. Keep the payload minimal. |
| `GET /api/v1/globe/satellite-tracks` | Ambient; failure must not break the globe. |
| `GET /api/v1/models/status` | Near-static, cached 5 min. Health enum: `online` / `warming` / `degraded` / `offline`. |
| `GET /api/v1/assistant/suggestions` | Backend-driven — which questions are worth asking depends on the operator's catalogue. |
| `POST /api/v1/assistant/stream` | **SSE**. Discriminated union on `type`: `message-start`, `trace-step`, `token`, `message-complete`, `stream-error`. Emit each trace step **twice** — `running`, then `completed` with `durationMs`. That transition is the execution-trace UI and the product's credibility signal. Tokens in word-sized chunks. |

Two contract requirements that matter more than they look:
- **Confidence is `number | null`.** Null means "AERIS declines to assert one" and renders as an explicit
  "Confidence not asserted", not as zero.
- **`cloudCoverPercentage` is null for SAR**, not `0`. Null renders "Cloud n/a"; zero would claim a
  cloud-free SAR scene, which is a different statement.
