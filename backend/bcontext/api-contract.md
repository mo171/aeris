# The wire. What the frontend already expects, and the two events we are adding.

**what** : The complete backend contract — endpoints, payload rules, stream event unions, shared
vocabularies and the tile requirements — plus the additions this design introduces for voice, agentic
interface control and **rendered figures**.
**where**: Binding on every Phase 2 route, and on the Phase 1 LangGraph stream, which emits these exact
event objects to the terminal. Any change here is a coordinated change with the frontend.
**how**  : Most of this is transcribed from code the frontend has already shipped, so it is contract rather
than proposal. Sections marked **NEW** are additions agreed on 2026-08-30 and not yet implemented on the
frontend.

---

## 0. Where the truth lives

| Question | Authoritative file |
|---|---|
| Which endpoints exist | `frontend/lib/constants/rest.api.ts` |
| Exact payload shape | `frontend/features/*/schemas/*.schema.ts` (Zod) |
| Transport envelope, pagination, errors | `frontend/lib/types/api.types.ts` |
| Stage codes S1–S20 | `frontend/lib/constants/pipeline-stages.ts` |
| Model ids | `frontend/lib/constants/models.ts` |
| Interface command ids | `frontend/lib/constants/commands.ts` |
| Hard requirements, stated in prose | `frontend/fcontext/memory.md` — the three sections titled **"Message for the backend developer"** |

Those Zod schemas are exported to JSON Schema into `bcontext/contracts/` (Phase 0.7) and every backend
fixture is validated against them in CI. **Drift is a failing test, not a Phase 2 surprise.**

## 1. Rules that are not negotiable

1. **camelCase on the wire.** Python fields are `snake_case`; Pydantic models set
   `alias_generator=to_camel, populate_by_name=True`. Never rename a concept across the boundary —
   `ground_sample_distance_meters` ↔ `groundSampleDistanceMeters`, and nothing shorter on either side.
2. **`confidence` is `float | None`.** `None` means AERIS declines to assert one and renders as an explicit
   refusal card. **Never coerce it to `0.0`** — zero is the claim "no confidence", which is a different
   statement from "no claim".
3. **`cloudCoverPercentage` is `None` for SAR**, never `0`. Zero would assert a cloud-free radar scene.
4. **The wire carries codes, the frontend carries copy.** Send `S13` and `changeformer`; never send
   "Specialist analysis" or "ChangeFormer". An unknown code fails at the frontend's schema boundary, which
   is intended — it is louder than a blank row.
5. **Cursor pagination**, never offset. The catalogue is unbounded and ingest is concurrent, so offsets
   skip and duplicate rows. Shape: `{items, nextCursor, totalCount}`; `nextCursor: null` ends the sequence.
6. **`POST /investigations` must return fast.** The camera is already flying when it resolves. Heavy work
   belongs in the run that follows.
7. **Insufficient evidence is a successful response**, not an error. It carries a reason and actionable
   remedies (PDF p.38).
8. **Every evidence polygon carries** `areaHectares`, `magnitude`, `confidence`, `modelId`, `modelVersion`,
   `traceStepId`.
9. **Masks ship in both representations** — raster tiles for display, GeoJSON polygons for evidence.
10. **Every trace step carries its artefact URI** where its stage produced one. Provenance already requires
    retaining those intermediates, so this costs a URI already held.

## 2. Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/imagery` | Cursor paginated (`cursor`, `limit`, `search`) |
| GET | `/api/v1/imagery/{sceneId}` | Acquisition, quicklook, bands, AOI context. Feeds the scene pop-out. |
| POST | `/api/v1/imagery/upload-ticket` | → `{sceneId, uploadUrl, expiresAt, requiredHeaders}`. **Direct to storage**, never through the app server. |
| POST | `/api/v1/imagery/{sceneId}/confirm` | Called after the storage PUT succeeds. Triggers ingest. |
| POST | `/api/v1/catalogue/search` | `{areaOfInterest, from, to, modalities[], maximumCloudPercentage}` → `{query, acquisitions[], coverageGaps[], recommendedPair, advisory}`. POST because the body carries geometry. |
| GET | `/api/v1/missions` | Cursor paginated. **Ordered server-side** — alerts first, then recency. The client deliberately does not re-sort. |
| GET | `/api/v1/missions/{missionId}` | |
| POST | `/api/v1/missions` | Promotes a completed investigation into a re-runnable mission. |
| GET | `/api/v1/globe/markers` | Whole collection, unpaginated — uploaded to the GPU as one buffer. Keep the payload minimal. |
| GET | `/api/v1/globe/satellite-tracks` | Ambient. **Failure must not break the globe.** |
| GET | `/api/v1/models/status` | Near-static, cached 5 min. Health: `online` / `warming` / `degraded` / `offline`. |
| POST | `/api/v1/investigations` | Fast. → `{investigationId, areaOfInterestName, areaOfInterest, cameraTarget}` |
| GET/PATCH | `/api/v1/investigations/{id}` | |
| POST | `/api/v1/investigations/{id}/scenes` | `{sceneId, role}` → **the updated investigation**, not an acknowledgement. Re-fetching leaves a window where the layer stack and the comparator disagree about which scene is T1. |
| POST | `/api/v1/investigations/{id}/runs` | **SSE.** The analysis stream. |
| GET | `/api/v1/investigations/{id}/evidence` | The evidence graph: claims, evidence, layers. |
| GET | `/api/v1/investigations/{id}/figures` | **NEW** (§6). Every rendered figure for the investigation, metadata only. |
| GET | `/api/v1/figures/{figureId}` | **NEW** (§6). The image bytes, from storage. CORS enabled, immutably cacheable. |
| GET | `/api/v1/investigations/{id}/plan` | The autonomous plan, returned **before** execution so the operator can edit it. |
| GET | `/api/v1/investigations/{id}/report` | **SSE**, plus `.pdf` / `.json` / `.geojson` exports. |
| GET | `/api/v1/investigations/{id}/cross-modal` | Two per-sensor runs and their agreement. A separate endpoint, not a mode of `/runs` — the shape is genuinely different, and folding it in would force every temporal consumer to handle a dual-provenance claim it will never receive. |
| GET | `/api/v1/regions/suggestions` | |
| GET | `/api/v1/assistant/suggestions` | Backend-driven — which questions are worth asking depends on the operator's catalogue. |
| GET | `/api/v1/assistant/history` | |
| POST | `/api/v1/assistant/stream` | **SSE.** The Mission Command assistant stream. |

## 3. Stream events

Three unions, all discriminated on `type`. **In Phase 1 these are exactly the objects the CLI prints and
journals**, which is what makes Phase 2 a transport swap rather than a rewrite.

### 3.1 Assistant stream — `POST /assistant/stream`

`message-start` · `trace-step` · `token` · `message-complete` · `stream-error`

**Emit every trace step twice** — once `running`, then again `completed` with `durationMs`. That transition
*is* the execution-trace UI, and it is the product's credibility signal. Tokens in word-sized chunks.

### 3.2 Analysis stream — `POST /investigations/{id}/runs`

`run-start` · `trace-step` · `layer-ready` · `claim` · `answer-token` · `run-complete` · `run-error`
plus **NEW** `figure-ready` (§6) · `ui-command` (§4) · `speech` (§5)

**`layer-ready` is its own event and must stay that way.** The viewer draws a layer the moment it exists,
rather than waiting for the run to finish. The frontend's own note calls this "the single most important
line in the analysis contract". It carries the layer *and* the evidence records it draws, so nothing ever
renders unattributed.

**`figure-ready` follows the same principle for images** — a rendered figure is shown the moment it exists,
never batched to the end of the run.

`run-complete` carries `confidence` (nullable), `insufficientEvidence` (nullable) and `totalDurationMs`.

### 3.3 Report stream — `GET /investigations/{id}/report`

`report-start` · `report-section` · `report-complete` · `report-error`

---

## 4. NEW · `ui-command` — the agent drives the interface

**Agreed 2026-08-30. Not yet implemented on the frontend.**

Emitted on both the assistant and analysis streams.

```jsonc
{
  "type": "ui-command",
  "runId": "run_01J...",          // or messageId on the assistant stream
  "commandId": "investigation.focusEvidence",   // from lib/constants/commands.ts
  "params": { "evidenceId": "ev_01J..." },
  "reason": "Raising the largest change region."  // one line, spoken or shown; never null
}
```

**Why it exists.** *"Compare these two and show me the biggest change"* is one utterance that needs both an
analysis and a change to the screen. Without this event the agent can only answer, never act, and the system
is a chatbot with a map next to it.

**Why it is safe.** The frontend's command bus already carries a Zod `paramsSchema` per command. On receipt
the client:

1. looks `commandId` up in the registry — **unknown id is dropped and logged, never dispatched**;
2. parses `params` against that command's schema — **a parse failure is dropped and logged**;
3. checks `isEnabled()`;
4. dispatches.

**The model's arguments are never trusted.** The registry is the allowlist, and it is the frontend's, not
the backend's. The backend mirrors the id list into `app/constants/ui_commands.py` so it can only *propose*
commands that exist; the frontend still validates independently, because a mirrored list drifts.

**Constraints.** Commands are proposals about presentation, never about data. Nothing that navigates away,
deletes, or spends money is dispatchable this way. Rate-limited per run — an agent that flies the camera
eleven times in one answer is a bug, not a feature.

## 5. NEW · `speech` — what AERIS says out loud

**Agreed 2026-08-30. Not yet implemented on the frontend.**

```jsonc
{
  "type": "speech",
  "runId": "run_01J...",
  "utteranceId": "utt_01J...",
  "text": "Built-up area increased about eighteen percent. Fourteen hectares, mostly north-east.",
  "audioUrl": "/api/v1/speech/utt_01J....opus",   // null while synthesis streams over the socket
  "claimIds": ["clm_01J..."],                      // what this utterance is grounded in; never empty
  "interruptible": true
}
```

**The spoken line is generated from the validated claim objects, not from the answer tokens.** Reading the
written answer aloud produces a screen reader: the written answer is precise, cites figures and is meant to
be re-read, while speech must be short and must never voice a number no specialist produced.

Hence `claimIds`. **An utterance with no claim behind it is not emitted** — the same evidence-first rule the
rest of the system runs on, applied to a second surface. Spoken numbers are rounded for the ear ("about
eighteen percent") while the written claim keeps its declared `precision`; the underlying value is identical.

`interruptible: false` marks a refusal or a safety statement that should finish before barge-in silences it.

**Barge-in cancels the utterance, not the run.** *(Corrected 2026-08-31; the earlier text here said it
cancels both, and that was wrong — `product-truth.md` §1.3.)* Speech detected during playback stops synthesis
of that one utterance. The run behind it continues, keeps emitting `trace-step`, `layer-ready`, `claim` and
`ui-command`, and completes normally. A ten-minute analysis has to survive being spoken over, or no operator
will risk asking a question during one.

Three signals, three effects:

| Signal | Effect |
|---|---|
| Barge-in (speech over an utterance) | That utterance's synthesis stops. Nothing else. |
| Standby ("quiet down") | Speech suppressed until released; the run continues silently and narration resumes at completion. |
| Abandon (explicit "stop this run") | The run stops at the next node boundary and emits `run-error` with a cancellation reason. **The only thing that uses the Phase 1.0 cancellation.** |

**Provisional utterances.** A question asked mid-run that the analysis has not answered yet is answered from
model knowledge, and that is the one case where `claimIds` is empty. It **must** then carry
`"provisional": true`, and the client must mark it unsourced. An unlabelled empty-`claimIds` utterance is a
contract violation, not a degraded case — it is a fluent number with nothing behind it. The grounded
utterance that later supersedes it carries `supersedesUtteranceId`.

---

## 6. NEW · `figure-ready` — the images the backend renders

**Agreed 2026-08-30. Not yet implemented on the frontend.** The requirement is `product-truth.md` §1.5; the
decision and its rejected alternatives are **ADR-004**.

The backend renders finished images from the data it reasoned over — a colourised index map with a colourbar,
a mask over the true-colour scene, detections with boxes drawn, T1 and T2 side by side with the change mask.
These are **not tiles.** A tile is a fragment draped on the globe in EPSG:3857 with no legend and no
annotation; a figure is one self-contained picture that carries its own legend and needs no WebGL context.
Both ship, and neither substitutes for the other.

Emitted on the analysis stream and on the assistant stream.

```jsonc
{
  "type": "figure-ready",
  "runId": "run_01J...",
  "figureId": "fig_01J...",
  "kind": "index-map",           // index-map | mask-overlay | detection-overlay | comparison | histogram | rgb-composite | sar-backscatter
  "title": "NDVI — 2026-03-14",
  "caption": "Vegetation index over the area of interest. Stressed vegetation below 0.2 in red.",
  "imageUrl": "/api/v1/figures/fig_01J....webp",
  "width": 1024,
  "height": 1024,
  "traceStepId": "ts_01J...",    // the stage whose output this renders. Never null.
  "claimIds": ["clm_01J..."],    // claims this figure supports; [] is allowed for a diagnostic figure
  "legend": {                     // legend AS DATA, never only as pixels
    "kind": "continuous",         // continuous | categorical | binary
    "label": "NDVI",
    "colorRamp": "RdYlGn",
    "domain": [-0.2, 0.8],
    "entries": null               // for categorical/binary: [{ "color": "#ffffff", "label": "Water" }]
  },
  "renderSpec": {                 // enough to reproduce this exact image
    "sceneIds": ["scn_01J..."],
    "bands": ["B08", "B04"],
    "stretch": { "min": -0.2, "max": 0.8 },
    "colorRamp": "RdYlGn",
    "resampling": "nearest",
    "crs": "EPSG:32643",
    "maskApplied": true
  },
  "isPrimary": false              // one figure per run may be marked primary: the one to show unprompted
}
```

### Rules

1. **`traceStepId` is never null.** A figure renders the output of a stage. An image with no stage behind it
   is decoration, and decoration is what this product exists not to produce.
2. **`renderSpec` is complete enough to reproduce the image.** Re-rendering from the spec is
   byte-identical for the same input. A figure the VLM reasoned over is part of the evidence chain, so
   "which stretch was that drawn with" must be answerable months later.
3. **`legend` is data, not pixels.** Colourbars may also be drawn into the image, but the machine-readable
   legend is mandatory. The frontend's own rule, quoted: *a scene of coloured geometry that never says what
   the colours mean is a picture, not evidence.*
4. **No figure carries a number that no claim carries.** Captions and drawn labels are generated from claim
   objects, exactly as `speech` is (§5). A figure is a third rendering of a validated result, never a fourth
   source of facts.
5. **Emit as soon as the figure exists**, like `layer-ready` — do not batch until `run-complete`. The
   operator watches the analysis assemble itself.
6. **Format is WebP, falling back to PNG**, always with an alpha channel so nodata is transparent. Lossy
   compression is forbidden for masks and permitted for RGB composites.
7. **The image bytes never travel on the stream.** `imageUrl` points at storage; the event carries metadata
   only. A base64 payload in an SSE frame stalls the stream that the trace UI depends on.
8. **One `isPrimary` figure per run, at most.** It is what the reference surface shows without being asked.
   More than one primary means the run did not decide what it was answering.

### Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/investigations/{id}/figures` | Every figure for an investigation, newest first. Metadata only. |
| GET | `/api/v1/figures/{figureId}` | The image bytes. Served from storage, **CORS enabled**, cacheable immutably — a `figureId` addresses one render, so it never changes. |

### Where the frontend puts these

The frontend already has both mechanisms and needs neither invented: **detached pop-out windows** (the
`/scene/[sceneId]` pattern, deliberately outside the geospatial route group so a window whose job is one
picture does not boot a WebGL globe) and the **`app/(reference)/` route group** for surfaces that answer a
question about the analysis rather than about a place. A figure panel is exactly that shape — pop it out, move
it to the second monitor, keep the globe on the first.

**This is a coordinated change, like §4 and §5.** The backend produces figures; the frontend surface is not
built yet, and `ROUTES` has no entry for it.

## 7. Shared vocabularies — the backend may not invent these

- **`S1`–`S20`** — `frontend/lib/constants/pipeline-stages.ts`. Also records which stages produce an
  inspectable artefact (S7 cloud mask, S9 registration residual, S12 index map, S13, S15).
- **12 model ids** — `frontend/lib/constants/models.ts`: `rs-vlm`, `grounding-dino-sam`, `changeformer`,
  `sar-change`, `segformer-landcover`, `dota-detector`, `index-engine`, `geospatial-engine`,
  `optical-sar-fusion`, `s2cloudless`, `co-registration`, `sar-preprocess`.
  **One vocabulary.** A claim saying `changeformer` while the fleet says `mdl_changeformer` makes "which
  model produced this claim, and why was it chosen" unanswerable by joining the two. That bug has already
  been fixed once on the frontend; do not reintroduce it from this side.
- **9 intents** — `SCENE_VQA`, `GROUND`, `INDEX_QUERY`, `DETECT`, `SEGMENT`, `CHANGE_DETECT`, `CHANGE_VQA`,
  `CROSS_MODAL`, `EVIDENCE_RECALL`.
- **~60 interface command ids** — `frontend/lib/constants/commands.ts`.

## 8. Tiles

From the frontend's Cesium session notes. Each of these has a specific failure mode attached.

> **Tiles are not figures.** This section is about fragments draped on the globe: no legend, no annotation,
> composited by the browser. Self-contained captioned images are §6 and go through a different path.

1. **XYZ in EPSG:3857 (WebMercatorQuad)** — TiTiler's default. Do not invent a scheme.
2. **CORS is mandatory.** Cesium fetches tiles cross-origin onto a canvas; without
   `Access-Control-Allow-Origin` the globe silently renders nothing. Named as the most common first-day
   failure — which is why it is a Phase 1.2 gate rather than a Phase 2 discovery.
3. **Alpha channel required.** PNG or WebP with transparency, so nodata is transparent. An opaque black
   rectangle around every scene destroys the composite.
4. **Send `bounds`, `minzoom`, `maxzoom`.** TiTiler's TileJSON already carries them; the frontend maps them
   to Cesium's `rectangle` and `maximumLevel`. Without them Cesium requests tiles across the whole planet
   and hammers the tiler with 404s.
5. **Band selection and stretch stay server-side**, via TileJSON query parameters
   (`?bands=4,3,2&rescale=0,3000`). **The browser must never do band math.**
6. **Vector evidence** is GeoJSON with numeric properties. `magnitude` drives 2.5D extrusion — extruding
   change polygons by how much changed is the most direct way to make an operator *feel* a change rather
   than read it.
7. Self-hosted terrain, if it ever happens: quantized-mesh + `layer.json`.

## 9. Contract testing

Phase 0.7 exports every Zod schema to JSON Schema into `bcontext/contracts/`. Then:

- Every response model has a fixture, validated against its schema in CI.
- Every Phase 1 run journal is validated end to end — **which proves Phase 2 wire compatibility during
  Phase 1**, before a single route exists.
- Contracts are **generated, never hand-edited.** A wanted change is made in the frontend's Zod and
  re-exported.
