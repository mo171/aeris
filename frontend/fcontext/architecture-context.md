# AERIS Frontend Architecture Context

---

# Stack

| Layer | Technology | Role |
|---|---|---|
| Framework | Next.js 16 + TypeScript | Full-stack frontend architecture with App Router, server/client boundaries, dashboard rendering, and realtime UI systems |
| UI System | Tailwind CSS + shadcn/ui | Design system, reusable components, dashboards, tables, cards, dialogs, forms |
| State Management | Zustand | Global client-side state management for dashboard filters, UI state, realtime state, and temporary workflow state |
| Server State & Caching | TanStack Query | API caching, mutations, background refetching, optimistic UI, infinite queries |
| Forms & Validation | React Hook Form + Zod | Scalable form handling and schema-based validation |
| Charts & Analytics | Recharts | Analysis statistics, confidence graphs, area metrics, change quantification |
| 3D Earth | CesiumJS | The globe, terrain, imagery tiles, camera and fly-to. Owns everything georeferenced and everything that lives inside the 3D scene |
| Analytical rendering | deck.gl — **not installed yet** | Deferred on purpose. Added as a camera-synced overlay above Cesium only when a specific gap bites: GPU aggregation, 100k+ vector features, or rich animated attribute transitions. Cesium covers everything else natively |

**Division of labour — a hard rule.** All mathematics, reprojection, band math, tiling and model
inference happen in the **backend**. The frontend renders and creates the experience. If frontend code
is computing NDVI or reprojecting a raster, something has gone wrong. AERIS is not another Google Maps;
the frontend's job is to make change *felt*, not to be a GIS engine.


YOU CAN ALWAYS SUGGEST MORE IMPROVISATION ON ARCHITECTURE LIKE ADD ON BUT IT SHOULD NOT CONTRADICT OR DRIFT FROM OUR EXSITING ARCHITECTURE AND PATTERNS 

---

# System Boundaries

- `app`
  - Route structure, layouts, page rendering, loading states, route-level boundaries
  - this is only for proper routing the page inside it page.tsx should be very light weight

- `components`
  - this will have only 2 folder ui where shadcn all components are present
  - sharedUI where all other component specifc to the app is built 
  this is to make sure no 2 pages should write the same u.i code in two diff files for that same thing I am very strict with this 
  inside the sharedUI folder there will be 2 more folders 
  - functionalComponents and dumbComponents 
  by the name u might have figured out what that means so u have to make components like that for sharing due to which u have to work in future scope manner think can this u.i be used anywhere else in the future uf yes then it goes in sharedUI then if not dumb then in functionalComponents this should be your taught process

- `features`
  - Feature/domain-level frontend systems
  - Contains feature-specific components, hooks, services, store, and logic
  - example:
      making investigation workspace 
       so investigation/ 
       it will contain service,hook,component,store(shared state used to eradicate prop drilling),schemas,types
       hook and component is most important folder because every single thing of the u.i should be broken down into smaller manageable component and should be very efficient the handling of the data and other things we will constantly be using hooks like the pro frontend dev uses 
       service is when we call a specific endpoint so all of that will be done there sending of the data and store is the state management so we dont use prop drilling 
       - `schemas`
      - Zod validation schemas
      - Form validation and client-side data validation

    - `types`
      - Shared TypeScript types and interfaces


- `hooks` root level is the main which uses auth and chnage only in rare cases
  - Reusable frontend logic
  - WebSocket subscriptions, debounce hooks, infinite scroll, responsive hooks


- `store`
  - Zustand global state management
  - Sidebar state, auth state, notification state, websocket state
  - in this folder global state management will be done unlike what we were doing in feature folder 

- `lib`
  - Shared infrastructure and initialized systems
  - Axios client, websocket client, query client, auth helpers, environment config
  - the lib has constant and providers so make use of it as well 
  - constant folder inside
  which all the global constant like sidebar or anything else should be there 
  .env.ts file should be there for loading env variables and other configurations at onces and providing 
  services config 
  
  lib/
  axios/axios-client.ts       # the single axios instance + apiPost/apiPostForm + ApiError
  constant/rest.api.ts        # THE endpoint registry — every URL in the app
  constant/query-keys.ts      # every TanStack Query key
  providers/                  # theme-provider, query-provider, app-providers
  types/api.types.ts          # PaginatedResponse<T>, DropdownItem, shared API shapes
  env.ts                      # typed NEXT_PUBLIC_* access
  utils.ts                    # cn() and pure helpers

  and many more

main reason for this 
Dashboard

↓

hook

↓

service

↓

axios client

more generalised
components
    ↓

features/components
    ↓

features/hooks
    ↓

features/services
    ↓

lib/api


---

# Frontend Data Philosophy

## Global UI State

Use Zustand for:
- sidebar state
- modal state
- selected filters (AOI, date range, sensor type)
- websocket connection state
- temporary realtime UI state (active investigation, map viewport)

DO NOT store server cache in Zustand.

---

## Server State

Use TanStack Query for:
- API responses
- investigation results
- mission data
- model registry
- analysis outputs
- evidence graphs
- pagination
- infinite queries

Features:
- caching
- optimistic updates
- background refetching
- stale management

---

## Realtime State

Realtime updates should use:
- WebSockets
- append-only state updates
- incremental cache mutation

Examples:
- analysis progress updates
- change detection completion
- monitoring alert notifications
- live execution trace streaming

---

# Frontend Rendering Strategy

## Server Components

Used for:
- static dashboard rendering
- SEO-sensitive pages
- initial data loading
- low-interactivity pages

Examples:
- landing page
- model observatory (static registry view)
- mission history pages

---

## Client Components

Used only when browser interactivity is required.

Examples:
- investigation workspace (interactive map + chat)
- 3D Earth viewer
- live execution trace streaming
- change detection slider / comparison views
- evidence explorer with claim-to-region linking
- mission command center

Rule:
Avoid unnecessary client-side rendering.

---

# Frontend Performance Strategy

## Image Handling

- Next.js Image component
- CDN-backed image delivery
- lazy loading
- responsive image sizing
- blur placeholders
- optimized WebP/AVIF delivery

---

## Feed Optimization

- cursor pagination
- virtualized rendering
- infinite scroll
- optimistic interactions

---

## Caching Strategy

No periodically unchanged data should be refetched repeatedly.

Use:
- TanStack Query caching
- Zustand persistence
- memoization
- staleTime configuration
- Redis-backed APIs

Examples:
- model registry metadata
- sensor/satellite configurations
- spectral index definitions
- user permissions

---

# Frontend Realtime Systems

Realtime systems include:
- live analysis progress streaming
- execution trace updates
- monitoring alert notifications
- realtime confidence and evidence updates
- mission status changes

Architecture:
WebSocket
→ hooks/use-websocket
→ Zustand store update
→ UI rerender

---

# File & Media Handling

User uploads:
- satellite imagery (GeoTIFF, TIFF, PNG, JPEG)
- SAR imagery
- multi-temporal image pairs

Architecture:
Frontend
→ Signed Upload URL
→ Cloud Storage
→ CDN delivery

Rules:
- files never pass through backend server
- optimize all uploaded images
- generate responsive variants
- lazy load media

---

# Frontend Security Rules

- Never trust frontend RBAC alone
- Backend validates every permission
- Sanitize user-generated content
- Use schema validation everywhere
- Use protected routes
- Store auth securely
- Avoid exposing secrets client-side

---

# Important Frontend Invariants

1. Components should remain presentation-focused whenever possible.
2. Business/domain logic belongs inside feature modules.
3. Long-running or realtime workflows should not block UI rendering.
4. Server state and UI state must remain separated.
5. Expensive lists must use virtualization or pagination.
6. No periodically static data should be unnecessarily refetched.
7. WebSocket updates should mutate cache incrementally instead of refetching everything.
8. Client components should exist only where interactivity is required.
9. API communication must stay centralized inside services/hooks.
10. Reusable UI systems should be abstracted early to prevent duplication.

---

without frontend architecture collapse.
---

# Patterns Established In The Mission Command Build (2026-08-26)

These are additions to the architecture above, not departures from it. They exist because the same
problem will recur on all seven surfaces, and solving it once per surface would guarantee drift.

## The UI Command Bus (`lib/command-bus`)

Every interactive affordance in the application dispatches through a registered command rather than a
bare handler.

```
Button / keyboard shortcut / command palette / (later) agent + voice intent
        ↓
dispatchCommand(id, params)   ← Zod-validated at the boundary
        ↓
the feature's registered handler
```

A command declares `{ id, title, description, group, keywords, shortcut, paramsSchema, handler }`.
Features register theirs from a `use-<feature>-commands.ts` hook and unregister on unmount.

Why this is architectural rather than a convenience:

- The entire UI must eventually be drivable by the agentic system. `listCommandDescriptors()` already
  serialises the registry to JSON Schema, so the agent layer consumes the interface as tools with **no
  UI rewiring and no separate agent adapter**.
- Validation happens once, centrally. An agent or a misheard voice intent cannot drive the UI into an
  invalid state; it fails as data with a typed result.
- The command palette and every keyboard shortcut are consumers of the registry, so adding a capability
  never means also editing the palette or a shortcut table.

Rules: command ids are a public contract and live only in `lib/constants/commands.ts`. Commands taking
parameters are hidden from the palette (a palette cannot collect arguments) but stay agent-invocable.
Never add an interactive control whose behaviour bypasses the bus.

## Imperative Handles Belong In The Feature Store

Long-lived imperative objects — the globe camera (`GlobeViewerHandle`), the assistant panel controls —
are published into the feature's Zustand store on mount and read with `getState()` at call time.

They are not threaded down as refs, for two reasons: commands must be reachable from **outside React**
(the agent will call `dispatchCommand` from non-component code, where a ref is unreachable), and it
removes multi-level ref prop chains. These are live connection objects, the same category as a WebSocket
client — not server cache, so this does not violate the server-state/UI-state separation. Stores holding
them are never persisted. Every consumer must guard for null.

## Renderer Adapters

**No file outside `components/sharedUI/functionalComponent/geoStage/` may import `cesium`.** The same
rule applies to `@deck.gl/*` when the analytical overlay lands.

This boundary *moved* on 2026-08-27 (it used to be `features/missionCommand/components/globe/`); it did
not weaken. The reason is in "The Shared Geo Stage" below. The rule itself is not stylistic: the entire
renderer was replaced once already — react-three-fiber to CesiumJS — and because of this boundary, the
blast radius was three call sites.

Each surface consumes the stage through its own narrow adapter rather than reaching in directly:

| Surface | Adapter | Where |
|---|---|---|
| Mission Command | `GlobeViewerHandle` (`flyTo`, `zoomByFactor`, `resetView`, `setAutoRotate`) | `features/missionCommand/hooks/use-globe-stage-binding.ts` |
| Investigation Workspace | the stage handle directly, bound once | `features/investigation/hooks/use-scene-stage-binding.ts` |

Everything above those two hooks speaks in claims, layers, markers and roles. The stage speaks in
primitives. The translation happens in exactly two files.

## The Shared Geo Stage (2026-08-27)

**One Cesium viewer, owned by a route group layout, shared by every geospatial surface.**

`app/(geospatial)/layout.tsx` mounts `<GeoStage />` beneath `{children}` and wraps both `/` and
`/investigation/*`. Route groups do not appear in the URL, so no path changed.

Why the layout and not a feature: Next.js unmounts a page's tree on navigation. A viewer owned by
Mission Command would be destroyed mid-flight, and the globe → AOI descent would degrade to freeze →
boot a second WebGL context (~2 s) → cross-fade. That is exactly the *simulated* continuity this project
rejected when it declined the MapLibre split, and it would be absurd to reintroduce by accident.

Consequences to design around:

- **Scope the group deliberately.** Only surfaces that render the Earth belong in it. The Model
  Observatory must never pay for a WebGL context it does not use.
- **The stage has two modes**, `globe` and `scene`, because it is two instruments: orbital (markers,
  arcs, idle rotation, orbital zoom limits) versus close-range (operator imagery, evidence geometry, the
  comparator, tight limits, recessed basemap). Switching is a method call, not a remount — nothing about
  the transition touches WebGL.
- **The handle lives in `store/geo-stage-store.ts`**, global rather than feature-scoped, because the
  viewer outlives every page in the group. `pendingDescent` on that store is how a camera flight survives
  a route change: Mission Command starts the flight and routes *without awaiting it*, and the workspace
  consumes the pending descent to learn it must not restart a flight it is already inside.

## Runs And Lenses: Two Verbs, One Catalogue (2026-08-30)

`lib/constants/analysis-operations.ts` entries carry `kind: "run" | "lens"`.

- A **run** asks the backend to produce evidence that does not exist yet. It appends to the evidence
  graph and puts a step on the trace spine.
- A **lens** changes how evidence already in the workspace is READ. No model executes, no trace step
  appears, nothing is added to the graph.

They share one catalogue because they answer the same operator question — *what can I do here?* — and
share the `requires` vocabulary that explains why a row cannot be used. They must not share a dispatch
path: **a lens that dispatched an analysis run would fabricate a trace step for work nobody did**, which
is the exact opposite of the auditability this product sells. The branch appears in two places on
purpose — `InvestigationScreen.handleRunOperation` for the UI, and the `investigation.runOperation`
command handler, which is the agent's entry point and has no component above it.

Cross-modal agreement is the first lens. It reads a completed pair of per-sensor analyses over an
investigation that already exists.

## A Surface Must Be A Place (2026-08-30)

`lib/constants/navigation.ts` applies one test before a row is added: **could an operator arrive here
with nothing open?**

Cross-modal failed it. It reads an existing investigation — same evidence graph, same scenes, same area
of interest — so it needed an id the rail could not supply. It shipped as `/cross-modal/:id` plus an
index route to bridge the gap, and the index route was a symptom rather than a fix.

The cost of getting this wrong is not cosmetic. A reading of an investigation, given its own route, loses
every tool on the surface it left: the Toolbox, the assistant, the draw tools, the timeline, the layer
stack, the inspector, the trace. The cross-modal page computed an advisory saying its two acquisitions
were four days apart, told the operator that mattered, and withheld the only control that changes it.

**Before promoting a reading to a route, ask what the operator loses by leaving the workspace.** If the
answer includes anything they would plausibly reach for while reading it, it is a lens, not a page.

A lens composes into the workspace through **slots**: `InputsPanel` takes `sensorsSection?: ReactNode`,
`AnswerPanel` takes `verdictSection?: ReactNode`. Both receive already-composed elements and learn
nothing about the feature supplying them, which keeps the dependency one-way — investigation composes
crossModal, never the reverse.

## Exactly One Writer Per Stage Channel (2026-08-30)

`useSceneStageBinding` is the only thing in the application that calls `stage.sceneLayers.setLayers`.

This was briefly violated: a second hook pushed the cross-modal layer stack while the workspace binding
pushed its own, and the visible result depended on which effect ran last. That is a race, not a design.

A feature that needs different layers on the stage supplies them as **data through a pure function**, and
the single binding composes them — `features/crossModal/lib/sensor-stage-layers.ts` exports
`composeSensorLayers`, which `useSceneStageBinding` consumes via its `sensorLayers` option. The same rule
covers the spotlight: `spotlightFeatureIds` overrides the claim-derived highlight rather than a second
hook fighting for `setSpotlight`.

The general form: **when a second consumer needs to influence a stage channel, extend the single writer's
inputs — never add a second writer.**

## View Modes Must Restore What They Displace (2026-08-30)

A mode that takes over shared view state records the previous value and puts it back when it closes.

Opening the cross-modal lens forces `comparatorBinding` to `"crossModal"` so the split reveals radar
against optical. The lens slice carries `displacedBinding` and restores it on close. Without it, closing
the lens strands a temporal investigation with a radar/optical split and no indication of why.

This generalises to every future lens and present-style mode: if turning it on writes shared state,
turning it off owes the operator the state they had.

## Layers Are Data, Not Components

Analysis overlays arrive as descriptors (`StageLayer` / `EvidenceLayer`), never as components. One
renderer factory maps `kind` → Cesium primitive.

Adding a new analysis product — a flood mask, a backscatter difference, a confidence field — means the
backend emits one more descriptor and **zero frontend files change**. Without this the codebase would
grow linearly with the science behind it, and pages 3 and 4 could not be configurations of page 2.

Two details that are load-bearing:

- **`renderMode: "draped" | "extruded"` is not a boolean on a primitive.** Cesium's terrain
  classification (`ClassificationType.TERRAIN`) draws a polygon onto the ground and *cannot* be
  extruded; extrusion needs an absolute-height polygon, which is not classified. The volumetric toggle
  therefore rebuilds geometry rather than flipping a flag.
- **Every feature carries `magnitude`, `confidence` and `areaHectares`.** Magnitude drives extrusion,
  confidence drives muted rendering of uncertain regions, area is what the answer quotes. Geometry
  without them can be drawn but cannot be argued with.

Apply the same shape to any other heavy third-party renderer added later (image viewer, chart engine):
consume it through a narrow imperative interface owned by the feature.

## Streaming State: Where Each Half Goes

An analysis run produces two categories that must not be mixed:

| Arrives on the stream | Home | Why |
|---|---|---|
| Trace steps, answer tokens, run status | Feature store (`investigation-store`) | The client-side fold of an in-flight operation. Not cached server data. Living in the store is what lets the answer panel and the execution spine — opposite ends of the screen — read one run without prop-drilling. |
| Layers, evidence, claims | **Query cache**, mutated incrementally | Server state. `queryClient.setQueryData` on each `layer-ready` / `claim` frame, never a refetch. This is the existing rule for realtime data, applied. |

`layer-ready` is a separate event from `trace-step` on purpose: the viewer must draw a change mask the
moment it exists, not once the run finishes. That difference is what separates a workspace that feels
alive from one that feels like a form submission.

Two shapes never enter React state: the **camera pose** and the **comparator split position**. Both
change every frame; a render per frame would spend exactly the budget these surfaces exist to showcase.
The stage owns them and DOM handles subscribe.

## Cesium And deck.gl: Who Renders What

**One engine until it hurts.** Cesium renders the globe *and* the analysis surface. MapLibre + deck.gl
was evaluated as a second engine for the Investigation Workspace and declined: Cesium covers page 2's
critical path natively — including the before/after swipe slider (`splitDirection` + `scene.splitPosition`),
which is the most direct "feel the change" interaction there is — and splitting engines would turn the
cinematic globe→AOI transition from one continuous camera move into an engineered cross-fade.

deck.gl is added later, as an overlay, only where Cesium genuinely falls short: GPU aggregation
(heatmap/hexbin/screengrid), very large vector sets (100k+ features), and rich animated attribute
transitions. Do not reach for it before one of those actually bites.

There is **no official deck.gl integration for Cesium** (official overlays exist only for Mapbox/MapLibre,
Google Maps and ArcGIS). The workable pattern is a transparent deck.gl canvas above Cesium's, with
Cesium's camera converted to a deck.gl `viewState` each frame.

The consequence to design around: **deck.gl layers are not depth-interleaved with terrain.** They draw
on top rather than being occluded by relief. For nadir satellite overlays that is usually desirable — an
analyst wants the change mask visible — but it means deck.gl is wrong for anything that must sit *within*
the 3D scene.

So split by strength rather than defaulting to one:

| Cesium natively | deck.gl |
|---|---|
| Scene imagery tiles (`UrlTemplateImageryProvider`) | Animated temporal transitions — the "feel the change" moment |
| Change masks draped on terrain (`classificationType: TERRAIN`) | GPU aggregation: heatmap, hexbin, screen grid |
| Terrain, 3D Tiles, sky, atmosphere, lighting | Very large vector sets that would stall Cesium entities |
| Camera, fly-to, picking | Arc / trips / flow layers |

Cesium's terrain-draped polygons are excellent and are likely the right renderer for change masks. Do not
reach past them for deck.gl out of habit.

## Basemap And Terrain Configuration

Cesium's high-resolution imagery and world terrain come from Cesium Ion and need a free token.

- `NEXT_PUBLIC_CESIUM_ION_TOKEN` set → Ion world imagery + `createWorldTerrainAsync()`. Real satellite
  Earth with real elevation. This is the intended experience.
- Token absent → CARTO dark raster basemap + `EllipsoidTerrainProvider`. Real geography, but flat.

The fallback exists so the application never boots to a black sphere, not as an equivalent option.

## The Phase 1 Mock Seam

Mocking happens at the **transport layer**, never in services, hooks, stores or components:

- `/mock` exports `installMockTransport(apiClient)`, which swaps the axios adapter and the SSE transport
  in `lib/streaming`.
- It is called from exactly one guarded block in `lib/providers/app-providers.tsx`, at module scope so
  it is installed before the first query fires.
- Phase 2 removal is: delete `/mock`, then delete that block. TypeScript fails on that single line, so
  mock data cannot survive the migration.

Mock responses reproduce the real wire format exactly — cursor envelopes, artificial latency, error
statuses, chunked SSE frames — so loading, empty and error states are exercised in Phase 1 rather than
shipped untested. Never add `if (useMock)` branches outside `/mock`.

## Rendering Cost Rules

- **Batch geospatial primitives.** Thousands of markers belong in one `PointPrimitiveCollection`, not
  thousands of Cesium `Entity` objects. Entities carry a full property/time-dynamic machinery that costs
  far more than the primitive it renders.
- **Do not mutate every primitive every frame.** Cesium marks the collection dirty and rebuilds its
  buffer on property writes, so a per-frame pulse across thousands of points is expensive. Animate a
  small, meaningful subset — alert markers only — so the motion also carries information.
- **Cap resolution scale.** `viewer.resolutionScale` on a high-density display is the most common cause
  of an otherwise fine scene running at 30 fps.
- **Request render mode where possible.** A globe that only redraws when something changes leaves the GPU
  alone while the operator reads the assistant panel. It must be disabled while the camera is animating
  or auto-rotating.
- **Bound tile requests.** Always give an imagery provider its `rectangle` and `maximumLevel` from the
  scene's TileJSON, or Cesium will request tiles across the whole planet and collect 404s.
- Batch high-frequency stream writes. Assistant tokens accumulate in a ref and flush on an interval;
  committing every token re-renders the transcript ~70×/second.
- Virtualise lists whose length is unbounded. Do **not** virtualise content whose height changes while
  streaming — use `content-visibility` instead; a virtualiser re-measuring mid-stream jitters.
- Every skeleton must match the real content's dimensions, or data arrival causes a visible jump.
