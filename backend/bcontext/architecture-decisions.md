# Architecture Decisions

**what** : Why each load-bearing technology and convention was chosen, what was rejected, and what changing
it would cost. One ADR per decision, newest last.
**where**: Read before changing or re-litigating a technology choice. When another bcontext document appears
to contradict an accepted ADR, the ADR wins and the other document is stale.
**how**  : Each ADR states its context, the decision, the rationale, the alternatives that were rejected and
the consequences. A decision without its rejected alternatives is unusable later, because nobody can tell
whether the situation that produced it still holds.

| # | Decision | Status |
|---|---|---|
| ADR-001 | Inngest, not Celery, for durable background execution | Accepted |
| ADR-002 | LangGraph owns all orchestration; Inngest owns the retry loop; no custom protocols | Accepted, amends 001 |
| ADR-003 | Everything is `async def`; maths lives in a per-subsystem `math/` module | Accepted |
| ADR-004 | Figures are rendered server-side with Matplotlib/Agg and shipped as images, not composed in the browser | Accepted |

---

## ADR 001: Workflow Orchestration (Celery vs. Inngest)

**Date:** 2026-08-30
**Status:** Accepted

### Context
The `aeris` backend requires a robust background task and workflow orchestration system to handle complex, long-running AI pipelines (e.g., imagery ingestion, segmentation, VQA, cross-modal analysis). These pipelines are modeled as Directed Acyclic Graphs (DAGs) and require reliable state management, retries, and error recovery. The two primary candidates considered were **Celery** (with Redis) and **Inngest**.

### Decision
We have decided to use **Inngest** for workflow orchestration instead of Celery.

### Rationale

1. **Native Support for Complex Pipelines (DAGs):** 
   The architecture relies heavily on multi-step pipelines (`pipeline/graphs/`, `agents/state.py`). Celery requires complex custom state-tracking (often via Redis) to manage multi-step workflows with dependencies. Inngest is built fundamentally around "steps" and handles state management, pausing, resuming, and retrying individual steps natively out of the box.

2. **Error Recovery & Developer Experience:**
   AI inference pipelines are prone to unpredictable failures (e.g., model timeouts, OOM errors). Inngest provides a modern dashboard that allows developers to inspect the exact state of a failed workflow, fix the issue, and replay the pipeline from the exact point of failure. This significantly accelerates development and debugging compared to Celery's monitoring tools (like Flower).

3. **Infrastructure Overhead:**
   Celery requires provisioning, scaling, and managing separate worker pools and message brokers (Redis/RabbitMQ). Inngest operates as an event-driven orchestrator, triggering HTTP endpoints on the existing API server, reducing the operational burden of managing complex infrastructure early in the project lifecycle.

### Caveats and Constraints
* **Data Payloads:** Because Inngest orchestrates via HTTP, large payloads (like raw satellite imagery or model weights) **must not** be sent through Inngest events. 
* **Mitigation:** The ingestion service must save raw files to persistent storage (e.g., S3 or local disk) and pass only the `file_url` or `reference_id` within the Inngest event payload. The executing steps will read the file directly from storage.

### Alternatives Considered
* **Celery + Redis:** Rejected due to the complexity of managing state across multi-step DAGs and the high infrastructure overhead.
* **Temporal:** A viable self-hosted alternative to Inngest. It offers similar workflow capabilities but requires managing the Temporal server infrastructure. Inngest was favored for its immediate ease of use, but Temporal remains a fallback if self-hosting orchestration becomes a strict requirement.

---

## ADR 002: LangGraph owns the graph; Inngest owns durable execution

**Date:** 2026-08-30
**Status:** Accepted
**Amends:** ADR-001 (scope clarification, not a reversal)

### Context

ADR-001 chose Inngest over Celery for "workflow orchestration". That phrase turned out to cover two
genuinely separate concerns, and conflating them produced a design that reinvented tools we already intend
to use:

1. **What the workflow is** — the nodes, the state carried between them, the conditional routing, where a
   run got to, and how it streams progress out.
2. **How a run is durably executed** — triggering, background execution, retry with backoff, replay after a
   failure, and an operator-facing dashboard.

An earlier draft of the Phase 1 plan proposed three custom protocols — `StepRunner`, `EventSink` and
`LLMProvider` — to cover concern (1) while Inngest was deferred to Phase 2. Every one of them duplicates
functionality that LangGraph and LangChain already provide.

The existing `folder-archtecture.md` had already anticipated this: `services/pipeline/state.py`,
`pipeline/nodes/`, `pipeline/graphs/` and `agents/state.py` are a LangGraph layout, and ADR-001's own
rationale cites those paths.

### Decision

**LangGraph owns concern (1). Inngest owns concern (2). LangChain owns LLM access.**

| Concern | Owner |
|---|---|
| Graph topology, typed state, conditional routing | LangGraph `StateGraph` |
| Run state persistence and resume-from-checkpoint | LangGraph checkpointer — SQLite in Phase 1, Postgres in Phase 2 |
| Human-in-the-loop plan approval | LangGraph `interrupt()` |
| Streaming trace steps, ready layers and claims | LangGraph custom stream, carrying our Pydantic event models |
| Cancellation and voice barge-in | Task cancellation plus the checkpoint, so a cancelled run is resumable |
| LLM calls, structured output, tool binding | LangChain — `init_chat_model`, `with_structured_output`, `bind_tools` |
| Durable background execution, retry, replay, dashboard | Inngest, Phase 2 |
| Phase 1 invocation | The CLI calls `graph.astream()` directly |

**One Inngest function wraps one graph invocation.** Inngest guarantees the run happens and is retryable;
LangGraph knows what the run is and where it got to. On an Inngest retry the graph resumes from its last
checkpoint rather than re-executing completed nodes.

**The retry loop is Inngest's, exclusively.** No node, service, domain function or `lib/` client implements
backoff, and no `try/except` re-runs a stage. Ingestion is the concrete case worth naming, because it is the
one most tempted to grow its own loop: a scene download or a COG conversion that fails is retried by
`app/inngest/functions/ingest_scene.py`, whose retry policy is Inngest configuration, not code we wrote. In
Phase 1, before Inngest is bound, a failed run is simply re-invoked from the CLI and the LangGraph
checkpointer supplies the resume point — the same graph, no retry code either way.

### Consequences

**Deleted from the plan**: the `StepRunner` protocol and `LocalStepRunner`, the `EventSink` protocol, and
the `LLMProvider` protocol. The event *models* survive — they are the wire contract with the frontend
(`api-contract.md` §3) and are what nodes write into the LangGraph stream.

**Phase 1 keeps its CLI-only property.** LangGraph runs in-process and needs no HTTP, so retry, replay,
resume, plan approval and cancellation are all available in Phase 1 through the checkpointer. This is
strictly better than the deferred-Inngest arrangement it replaces: durability arrives in Phase 1.0 rather
than Phase 2.5.

**Phase 2 becomes smaller.** The graphs do not change. An Inngest function is added that invokes the same
graph, and the SSE endpoint consumes the same stream the CLI consumes.

**One containment rule survives** from the deleted protocols: LangChain and LangGraph model construction
happens in `app/lib/llm/`, so `agents/` and `pipeline/nodes/` import a project module rather than a vendor
package directly. This is an import-location rule, worth about forty lines, and it is what makes the model
and provider configurable from `config.py`. It is **not** a wrapper — structured output, tool calling and
streaming are used directly from the library.

### Rationale

- **Do not rebuild what the library does.** Checkpointing, interrupts, streaming and provider selection are
  solved problems. Engineering time is better spent on co-registration, change detection and evidence
  binding, which is where this product's difficulty actually lives.
- **Deterministic routing is preserved.** PDF pp.24–25 argues for a deterministic router over an autonomous
  agent loop. `add_conditional_edges` with a plain dictionary lookup *is* that router, expressed as a graph.
  LangGraph does not impose an autonomous loop.
- **Typed state replaces ad-hoc context passing.** The 20-stage pipeline carries a large amount of state
  between stages; a typed `StateGraph` schema makes that explicit and inspectable.

### Alternatives considered

- **Custom protocols over the raw OpenAI SDK.** Rejected: more code, less capability, and it would have had
  to grow checkpointing and interrupts by hand.
- **LangGraph for durability too, no Inngest.** Viable in Phase 1 and is in fact what Phase 1 does. Rejected
  for Phase 2 because LangGraph checkpointing is not a job scheduler: it has no trigger model, no backoff
  policy across process restarts, and no operator dashboard. ADR-001's reasons for Inngest still hold for
  concern (2).

### Documents corrected by this ADR

The three protocols were referenced as things to build in `architecture-context.md` §9/§11, `roadmap.md`
1.0 / 1.9 / 1.10 / 2.3 / 2.5, `product-truth.md` §2/§6, `code-standards.md` §8 and `api-contract.md`'s
header. All were corrected on 2026-08-30. If a stale reference resurfaces, `architecture-context.md` §4 is
the tie-breaker.

---

## ADR 003: The backend is async everywhere, and maths lives in its own module

**Date:** 2026-08-30
**Status:** Accepted
**Source:** Product owner instruction, recorded in `product-truth.md` §4.1 and §4.2

### Context

Two conventions were missing from the first draft of these documents and are cheap now, expensive later.

**Sync/async.** The stack we chose is asynchronous throughout — LangGraph nodes are awaited by
`graph.astream()`, FastAPI endpoints are coroutines, SQLAlchemy runs on `asyncpg`, and voice barge-in is
`asyncio` task cancellation. But the scientific half of the system is NumPy, Rasterio, GDAL, Shapely and
PyTorch, all of which are synchronous and CPU-bound. Left undecided, each file would resolve the mismatch its
own way.

**Maths placement.** Every subsystem in this backend computes something: index formulae, co-registration
residuals, speckle filters, morphology, vectorisation, equal-area hectares, confidence aggregation. Written
inline, that arithmetic ends up braided together with band lookup, mask application, config reads and database
writes — and it is the one part of the system that has to be **provably** right, because the product's entire
promise is that its numbers can be trusted.

### Decision

**1. Every function in `app/` is `async def`, except functions inside a `math/` module or `math.py`.**
`asyncio.run()` is called once per adapter — `cli/main.py` in Phase 1, never in Phase 2.

**2. `math/` modules are sync, pure, and the only sync surface in `app/`.** They know arrays, numbers,
geometries and CRS codes. They do not know what a scene, a claim, a run or a model id is, and they do no I/O.
Every call into them from async code is offloaded with `asyncio.to_thread(...)`, written at the call site.

**3. A service that deals with maths does not contain the maths.** It goes in a sibling `math.py`, or a
`math/` package, inside that subsystem's own folder. The service chooses *which* method; `math/` contains
*the* method.

The two decisions reinforce each other: because `math/` is the only sync surface, "is this safe to await" has
a structural answer rather than a per-file one, and the rule is reviewable instead of aspirational.

### Rationale

- **Uniform async removes a question from every call site.** One sync function mid-chain forces every caller
  above it to choose between blocking the loop and wrapping the call; that choice gets made inconsistently,
  and then a signature no longer tells you whether calling something is safe.
- **`async def` on a CPU-bound kernel is a lie.** It never yields, so it blocks the loop for its full duration
  while advertising that it does not. Being honest about it — sync function, explicit `to_thread` at the call
  site — is strictly better than a uniformity that misleads.
- **Isolated maths is testable maths.** `code-standards.md` §11 requires deterministic numerics to be checked
  against hand calculations or QGIS. A pure function over arrays makes that a three-line test; the same
  formula inside a service needs the whole system standing up, so in practice it does not get tested.
- **It is where the scientific boundaries live** (`architecture-context.md` §8). Equal-area reprojection
  before hectares, nodata propagating as a mask, reflectance rather than digital numbers, resampling method
  following data type. One named place per subsystem means those can be read and reviewed.
- **Retrofitting async is a rewrite of every call site.** Starting async costs nothing.

### Alternatives considered

- **Sync application with a thread pool at the edges.** Rejected: LangGraph, FastAPI and the voice loop are
  async-native, so this inverts the stack and makes concurrent capture, synthesis and analysis awkward.
- **Mixed sync/async, decided per module.** Rejected — this is precisely the state the decision exists to
  prevent.
- **`async def` on the maths too, for uniformity.** Rejected: it would block the event loop while claiming
  not to, which is a worse failure than an inconsistency, and it would hide the `to_thread` boundary that
  makes the offload cost visible.
- **A single top-level `app/math/` package.** Rejected: it separates the arithmetic from the domain that
  gives it meaning, and grows into a grab-bag. Per-subsystem `math/` keeps a formula next to the service that
  chooses it.

### Consequences

- `pytest-asyncio` is a base dependency; `async def test_...` above `math/`, plain `def test_...` inside it.
- `tests/unit/math/` mirrors every `services/*/math/`.
- `services/spectral/ndvi.py`, `ndwi.py` and `nbr.py` are removed from the planned tree — those are formulae
  and become functions in `services/spectral/math/index_formulae.py`.
- Invariants 7 and 8 in `architecture-context.md` §13 are the checkable form of this ADR.

---

## ADR 004: Figures are rendered on the backend, not composed in the browser

**Date:** 2026-08-30
**Status:** Accepted
**Source:** Product owner instruction, recorded in `product-truth.md` §1.5

### Context

Until now these documents described exactly one visual path: COG → TiTiler → XYZ tiles → Cesium. That path is
correct for *place* — a fragment draped on the globe, composited by the browser, no legend, no annotation.

It cannot produce the thing the product owner actually asked for and the notebooks already produce: **one
self-contained image that carries its own colourbar**, that can have boxes and labels drawn on it, that can put
two dates side by side with a change mask between them, and that can be looked at without a WebGL context —
in a pop-out window, on a second monitor, or inside a report. `notebooks/01_remote_sensing/` has been rendering
these all along (`imshow` with a named ramp and explicit `vmin`/`vmax`, a labelled colourbar, masks as binary
images, SAR as `10·log10` into a dB window); nothing carried them to the frontend.

There is a second, harder requirement in the same shape. At S14 the VLM is given a rendered image to reason
over. If that render is not deterministic and its parameters are not recorded, the evidence chain has a hole in
it: nobody can say later *what the model was looking at*.

### Decision

**The backend renders figures itself and ships finished images.** `app/services/rendering/` owns the array →
image path, using **Matplotlib on the `Agg` backend** plus **Pillow** for composition. Each figure is written
to object storage and announced with a `figure-ready` event (`api-contract.md` §6) carrying a machine-readable
legend, the `traceStepId` of the stage it draws, the claims it supports, and a `renderSpec` complete enough to
reproduce the image byte-for-byte.

**Tiles and figures both ship, and neither substitutes for the other.** Tiles answer "where"; figures answer
"what does this look like, and what do the colours mean".

### Rationale

- **We control the render, so we control what can be shown.** Adding a new kind of visual becomes "the backend
  renders another figure" rather than "the frontend needs a new panel with new WebGL work". That is the whole
  reason the product owner calls this crucial.
- **The colourbar is not decoration, it is the claim.** A ramp with no stated domain is unreadable, and the
  frontend's own standard already says so: *a scene of coloured geometry that never says what the colours mean
  is a picture, not evidence.* Drawing the legend where the data is known is the only place it is cheap.
- **A stretch decides what the operator sees.** Widen it and a drought disappears; narrow it and healthy crop
  looks stressed. Server-side rendering is what makes that choice recordable (`architecture-context.md` §8
  rule 13).
- **The same image serves the operator and the VLM.** One deterministic render, one recorded spec, one thing to
  audit — instead of a browser composite the model never saw.
- **The frontend already has the surfaces.** Detached pop-out windows and the `app/(reference)/` route group
  exist and are the right home. This decision adds no frontend architecture, only a payload.

### Alternatives considered

- **TiTiler only; let Cesium composite everything.** Rejected: tiles cannot carry a colourbar, an annotation or
  a side-by-side, and a figure pinned to a globe cannot be looked at on its own. This is not a limitation of
  our configuration, it is what a tile is.
- **Send arrays and let the frontend colour them.** Rejected on three counts: it puts band and ramp maths in
  the browser, which `api-contract.md` §8 rule 5 forbids; it makes the render non-reproducible, since the
  operator's client version decides the pixels; and it means the VLM and the operator are looking at different
  images.
- **A headless browser screenshotting the frontend.** Rejected: a browser and a render farm added to the
  backend to obtain something Matplotlib does in twenty lines, with a new failure mode per frame.
- **Base64 image bytes inside the SSE event.** Rejected: it stalls the stream the trace UI depends on. The
  event carries metadata; `imageUrl` points at storage (`api-contract.md` §6 rule 7).
- **Rendering only at report time.** Rejected: the operator watches the analysis assemble itself, and a figure
  is worth most at the moment its stage completes — the same argument that made `layer-ready` its own event.

### Consequences

- New subsystem `app/services/rendering/` with a sibling `math/` (`color_ramps.py`, `stretch.py`,
  `rasterize.py`), obeying ADR-003: the service chooses the ramp and stretch, `math/` applies them.
- New event model `schemas/events/figure.py`; new constants `color_ramps.py` and `figure_kinds.py`, shared
  vocabulary with the frontend's legends.
- New roadmap sub-phase **1.2.1**, deliberately placed after the tile engine and before 1.4/1.5/1.6/1.7 so
  each of those emits figures as it lands. Later sub-phases add figure *kinds*, not rendering code.
- MinIO gains a `figures` bucket (0.4), with CORS. Not because the browser loads these as images — a
  plain `<img>` needs no CORS at all, measured in Phase 0.4 — but because anything that reads a figure's
  *pixels* does: `fetch()`, and `crossOrigin="anonymous"` → canvas → `getImageData`, which is the path
  Cesium takes. Checking that the picture appears is exactly how a broken CORS configuration ships.
- `Matplotlib` must never be imported with an interactive backend anywhere in `app/`. `Agg` is set once, at
  import of the rendering package.
- Invariant 19 and scientific boundary 13 in `architecture-context.md` are the checkable form of this ADR.
- **Coordinated frontend change**, like `ui-command` and `speech`: the figure surface is not built and `ROUTES`
  has no entry for it yet.
