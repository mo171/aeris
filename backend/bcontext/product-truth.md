# The requirements that are NOT in the PDF. Read before designing anything.

**what** : Records the product owner's direct instructions — the constraints, the build order and the
engineering standard that the research documents do not state and cannot be inferred from them. Including
§1.5 (the backend renders images and sends them), §4.1 (everything is async) and §4.2 (maths lives in its own
module), all added after the first draft.
**where**: Governs every backend design decision. Where this document and the PDF appear to conflict on
*how to build*, this document wins; the PDF remains authoritative on *what the domain is*.
**how**  : Each section is a decision with its reason attached. A decision without a reason is unusable
later, because nobody can tell whether the situation that produced it still holds.

> The idea is written clearly in `context/SatqueryAI.pdf` and `context/FirstIdea.txt`.
> **What follows is the part that is not.** It came from the product owner on 2026-08-30.

---

## 1. The system is agentic and voice-driven end to end. This is the architecture, not a feature.

There is **no microphone button in a sidebar.** The intended experience is Tony Stark and JARVIS: the
operator speaks, the system speaks back, and the visuals change as it talks. Text input remains available;
it is the fallback, not the design centre.

**Why this is architectural rather than cosmetic:** a chatbot with speech-to-text bolted on can only answer
questions. The system described here must also *act* — fly the camera, raise a layer, split the comparator,
enter present mode — because half of "show me" is a change to the screen, not a sentence.

### 1.1 There are two tool surfaces and one agent

| Surface | Lives in | Examples | Effect |
|---|---|---|---|
| **Analysis tools** | Backend | run change detection, compute NDVI, search the catalogue, measure hectares | Produce evidence |
| **Interface tools** | Frontend command bus | `globe.flyTo`, `investigation.focusEvidence`, `setSplitPosition`, `togglePresentMode` | Change what is on screen |

The frontend's `lib/command-bus/` is **already a tool registry**. `CommandDefinition` carries a
`description` written, in its own words, "for the agent as much as for the operator", plus a Zod
`paramsSchema`. Roughly sixty command ids exist in `lib/constants/commands.ts`. They are a public contract:
renaming one is a breaking change.

*"Compare these two and show me the biggest change"* is a single utterance that requires both surfaces. The
backend therefore emits **`ui-command` stream events**, and the frontend validates their parameters against
its own registry schema before dispatch. **The model's arguments are never trusted.** See `api-contract.md`.

This is the line that separates an agentic system from a conversational one.

### 1.2 The spoken line is generated from the validated claim, never from the answer text

Reading the written answer aloud produces a screen reader. The written answer is precise, cites figures and
is meant to be re-read; a spoken line must be short and must never voice a number that no specialist model
produced.

So speech is a **separate generation from the structured claim object**, delivered as its own `speech`
stream event. The evidence-first rule is unchanged — it is simply applied to a second surface.

### 1.3 Interruption stops the *speaking*. It never kills the work.

**Corrected by the product owner on 2026-08-31, against every earlier draft of this document and of
`api-contract.md` §5.** The rule those drafts state — speech detected during an utterance cancels synthesis
*and* the run behind it, emitting `run-error` — is **wrong and must not be built.**

JARVIS is not a system you wait for in silence. A ten-minute run is normal here: co-registration, specialist
inference, vectorisation. An operator who says *"wait, which sensor is that?"* halfway through is asking a
question, not withdrawing the request. Cancelling on barge-in makes every long analysis unaskable, because
the operator learns that speaking costs them ten minutes.

So there are **three** distinct signals, and only the first is barge-in:

| Signal | What stops | What survives |
|---|---|---|
| **Barge-in** — the operator speaks over an utterance | Synthesis of *that utterance* | The run. It keeps going, keeps streaming, keeps emitting `ui-command` |
| **Standby** — "quiet down", "stop talking" | All speech until released | The run, silently. Narration resumes on release, or at completion |
| **Abandon** — "stop", "cancel that", explicit and only explicit | The run, at the next node boundary | The checkpoint, so it stays resumable |

Node-boundary cancellation is still built in Phase 1.0, for the third row, and for the original reason: it is
nearly free at a boundary and impossible to retrofit. What changes is **who is allowed to pull it.** Barge-in
is not.

### 1.3.1 A run in progress is something the agent can talk about while it runs

Because the run outlives the interruption, the agent has to hold a conversation *concurrently with it*. Three
consequences, all architectural:

- **The agent narrates.** *"Co-registering the pair now — about two minutes."* Progress is not a spinner; it
  is spoken, generated from the trace steps already on the stream.
- **The agent answers provisionally, and says that it is.** Asked something mid-run that the analysis has not
  reached, it answers from model knowledge, **labelled**, then supersedes that answer with the grounded one
  when the run completes. This does not weaken the evidence rule — it makes it explicit. A provisional answer
  carries **no `claimIds`** and is marked provisional on every surface: written, spoken, shown. An
  *unlabelled* provisional answer is the worst output this system can produce, because it is a fluent
  unsourced number, which is precisely what the PDF says a VLM must never be permitted to emit.
- **A finished run interrupts the conversation, politely.** The result arrives asynchronously, possibly three
  turns later, against a conversation that has moved on: *"coming back to the built-up question — eighteen
  percent."*

**Consequence for Phase 1.0, which is why this is recorded before it is built:** the run must not be awaited
inline by the conversation. The agent loop and the pipeline run are **separate tasks over one shared
session**, communicating by stream. A spine that awaits `graph.astream()` to exhaustion inside the turn
cannot be made to do any of the above later without being rewritten.

### 1.4 Voice stack (decided)

`faster-whisper` for recognition, Piper/Kokoro for synthesis, both running in the backend, both offline.
Chosen over browser speech (Chrome-only, ships audio to Google, no control over interruption) and over
hosted realtime APIs (per-minute cost, needs internet, and puts part of the agent loop in someone else's
runtime). An offline loop also survives a demo venue with bad networking, which is a real SIH risk.

### 1.5 AERIS answers on three surfaces: written, spoken, and **shown**

Stated by the product owner and **missing from every earlier draft of these documents, including the PDF.**
It is a capability, not a presentation detail.

**The backend renders images and sends them to the frontend.** Not only tiles for the globe, and not only
GeoJSON for evidence — actual finished pictures. The reference is `notebooks/01_remote_sensing/`: read the
bands, compute the thing, apply a colour ramp with a deliberate stretch, and you have an NDVI map where
stressed vegetation is visibly red, a water mask, a SAR backscatter image in decibels where calm water is
black and the city is white. That render is the analysis made *legible*, and until now nothing in the plan
produced one.

The set of images worth sending, all of which the pipeline already has the data for:

| Figure | Made from | Answers |
|---|---|---|
| Colourised index map with a colourbar | S12 index array + ramp + stretch | "where is the vegetation stressed" |
| A mask, alone or over the true-colour scene | S7 / S12 / S13 masks | "what exactly did you count" |
| Detections and grounding with boxes and labels drawn | S13 / S14 boxes | "show me the ones you found" |
| T1 / T2 side by side, plus the change mask | temporal pair | "what changed" — the strongest single image this system can produce |
| SAR in dB, before and after speckle filtering | S8 | "why do you trust the radar here" |
| Histogram or a threshold plot | any `math/` output | "why did you cut it there" |

**Why this is not the tile pipeline, and cannot be folded into it.** A tile is a fragment draped on the globe
in EPSG:3857, composited by the browser, carrying no legend and no annotation. A figure is one self-contained
image: it carries its own colourbar, it can draw boxes and labels, it can put two dates next to each other,
and it does not need a WebGL context to exist. Neither substitutes for the other. Both ship.

**The frontend already has the place to put them, and the mechanism is already built.** It has detached
pop-out windows — `/scene/[sceneId]`, deliberately outside the geospatial route group so that *a window whose
job is one picture does not boot a WebGL globe* — and an `app/(reference)/` group for surfaces that answer a
question about the analysis rather than about a place. A figure panel belongs in exactly that shape: pop it
out, drag it to the second monitor, keep the globe on the first. **The backend side is what does not exist
yet.**

**Why the product owner calls this crucial.** The render path is ours end to end. Anything worth showing can
be composed server-side and shown *without waiting for a frontend component to be designed for it* — a new
diagnostic, an unplanned comparison, a plot that explains a refusal. It converts "the frontend would need a
new panel" into "the backend renders another figure". That is the leverage, and it is why the renderer is a
first-class subsystem rather than a helper.

**The agent explains the image, and the VLM reads the same image.** The figure is dual-purpose: it is what the
operator sees *and* what the vision-language model is given at S14. One consequence follows immediately —
**the render must be deterministic and its parameters recorded**, because a figure the VLM reasoned over is
part of the evidence chain, not a screenshot.

**What keeps it honest.** A figure is evidence, and the evidence rules apply unchanged:

- **Every figure carries its render spec** — bands, stretch bounds, colour ramp, resampling method, CRS — plus
  the `traceStepId` of the stage that produced its data. Re-rendering from the spec produces the same image.
- **Every figure carries its legend as data**, never only as pixels. The frontend's own note earns quoting
  here: *a scene of coloured geometry that never says what the colours mean is a picture, not evidence.*
- **No number is drawn onto a figure that no claim carries.** Captions are built from claim objects, exactly
  as speech is (§1.2). A figure is a third rendering of the same validated result, never a fourth source of
  facts.

`api-contract.md` §6 defines the `figure-ready` event and the endpoints; `architecture-context.md` §7 places
the `rendering/` subsystem; `roadmap.md` 1.2.1 builds it; **ADR-004** records why this is rendered on the
backend rather than composed in the browser, and what was rejected.

### 1.6 AERIS is a session-scoped harness with two memories

**Stated by the product owner on 2026-08-31.** Also a gap: nothing in these documents described memory of any
kind beyond the LangGraph checkpointer, and **the checkpointer is not memory** — it is the resume point of one
run.

The operator opens a session deliberately, by keypress. The frontend already has the shape for it: every
`CommandDefinition` carries a `shortcut`, and the command palette is the surface. From that moment AERIS is
*present* — it holds the thread, it knows what "it", "there" and "the second one" refer to, and it is the
thing driving the interface rather than a panel sitting inside it.

| Memory | Scope | Holds | Written |
|---|---|---|---|
| **Thread** | One session | Turns, referents, the active investigation, what is running | Continuously, automatically |
| **Long-term** | Across sessions, indefinitely | Durable facts the operator chose to keep: this AOI is the Ghaziabad site, this operator works in hectares, this pair is the baseline | **Deliberately** — the operator says "remember that", or the agent proposes and the operator agrees |

**Long-term memory being opt-in is the design, not a limitation.** A system that silently retains everything
an analyst said is one nobody can audit, and this workload is disaster response and defence. Every long-term
entry records who wrote it, when, and the session it came from — the provenance rule the evidence chain
already runs on, applied to the things the agent believes.

**What it is not.** Not a vector store of chat logs retrieved by similarity, which is how this is usually
built and why it usually produces confident nonsense. **Recalled memory is context, never evidence.** It can
shape what AERIS does; it can never become a claim. A claim comes from a specialist model, every time.

LangGraph owns the mechanics of both — the checkpointer for the thread, `BaseStore` for the long-term
namespace — for the reason ADR-002 gives for everything else: we do not rebuild what the library provides.

---

## 2. Build in two phases. Phase 1 is a complete application with no HTTP.

### Phase 1 — the entire engine, as a CLI

Services, the agentic system, the LangGraph pipeline with checkpointed resume and replay, the models, the
evidence layer, the report generator and the **full voice loop** — all of it, driven from the terminal, tested
over and over. No routes. No controllers. No WebSockets.

### Phase 2 — serving

Routes, controllers, SSE, WebSockets, Inngest, auth. **Phase 2 adds files and deletes none.**

### Why this is the right split, and what makes it work

Building the engine behind a CLI removes HTTP, sockets, serialisation and browser state from the debugging
surface while the hard parts — co-registration residuals, model routing, evidence binding — are still being
got right.

An earlier version of this section named **two custom seams**, `EventSink` and `StepRunner`, as the price of
making Phase 1 not become a rewrite. **Both are cancelled.** ADR-002 records the reason: LangGraph already
provides everything they were going to provide, and writing them would have spent engineering days on
plumbing that a library ships. The product owner's instruction is explicit —

> **All orchestration is LangGraph. The retry loop is Inngest. I am not writing protocols for either.**

So the split works because of what the libraries already give us, not because of anything we build:

**LangGraph gives Phase 1 durability on day one.** It runs in-process and needs no HTTP, so typed state,
resume-from-checkpoint, replay, plan approval via `interrupt()` and cancellation are all available in Phase
1.0 — not deferred to Phase 2.5 as the `StepRunner` plan required. The pipeline never writes to a socket; it
writes our event models into the LangGraph stream (`stream_mode="custom"`). Phase 1 consumes that stream with
a terminal renderer and a JSONL writer; Phase 2 consumes the same stream over SSE. **The Phase 1 JSONL
replays through the frontend's own Zod parsers, so Phase 2 wire compatibility is provable months before a
route exists** — the payoff the seams were meant to buy, obtained for free.

**Inngest owns the retry loop, and only the retry loop.** Trigger, background execution, backoff, replay and
the operator dashboard. One Inngest function wraps one graph invocation; on retry the graph resumes from its
checkpoint instead of re-running completed stages. Nothing in `app/` implements backoff itself. This does not
overturn ADR-001 — it narrows it to the concern Inngest is actually good at, and Inngest genuinely cannot be
used in Phase 1 because it orchestrates by making HTTP calls into the application. Phase 1 simply re-invokes
the graph from the CLI and lets the checkpointer supply the resume point.

**The one containment rule that survives.** LangChain and LangGraph chat-model construction happens in
`app/lib/llm/`, so `agents/` and `pipeline/nodes/` import a project module rather than a vendor package. It is
about forty lines and it is what makes §6 true. It is an import-location rule, **not** a wrapper.

`cli/` and `routes/` are **sibling adapters over one core.** Neither may contain logic the other needs.

---

## 3. How a sub-phase is executed

Every `1.x` runs the same three beats, in order:

1. **Research.** Re-read the relevant PDF pages. Use `notebooks/` to think — load the data, plot it, get the
   maths wrong in a notebook where it is cheap. **Write a notebook only when its conclusion will change the
   code you write next**, and then actually use that conclusion: a threshold, a constant, a comment naming a
   failure mode, a paragraph in a doc. A notebook written because a plan said "notebook" is wasted work. If
   you already know the answer, say so and skip to step 2. A notebook is a thinking surface; nothing ships
   from one, but conclusions do.
2. **Write the code.** Only after the notebook shows the approach is right.
3. **Test.** Automated tests, then the product owner exercises it. A sub-phase is not done because the code
   exists; it is done when its **gate** passes.

Phase 0 establishes a **setup pattern** that is then repeated for every dependency:
`provision → client in lib/ → health probe → a row in aeris doctor → a test`.

---

## 4. The engineering standard

Stated by the product owner, and it is the acceptance criterion for every file:

> Must not be AI slop. Must be well thought out, accurate, minimal, easy to maintain, and well researched.

Operationally:

- **Researched** — a design decision that comes from the PDF cites its page. A numerical method that has a
  known failure mode says so in a comment where the method is used.
- **Accurate** — the domain punishes plausible-looking code. Hectares computed in degrees, a co-registration
  residual left unchecked, a cloud mask applied after the index instead of before: each produces a confident
  wrong number, which is worse than an error, because the whole product is a promise that its numbers can be
  trusted.
- **Minimal** — no abstraction without a second caller. No configurability nobody asked for. **No protocol
  for something a library already does** — that is the whole content of ADR-002, and it is why `StepRunner`,
  `EventSink` and `LLMProvider` were cancelled before a line of any of them was written.
- **Maintainable** — small single-purpose modules, no shortform names, every file self-describing at the top
  (`code-standards.md`).

### 4.1 Every function is `async def`. `math/` is the only exception.

Stated by the product owner after the first draft of these documents was written, and it is retroactive:
**there is no sync path through `app/`.** Routes, CLI commands, controllers, services, pipeline nodes, domain
functions, agents, tools, `lib/` clients, repositories, voice handlers — all coroutines.

The reason to make it absolute rather than case-by-case: a single sync function in the middle of an async call
chain pushes a decision onto every caller above it — block the loop, or wrap the call — and that decision gets
made differently in different files. The result is a codebase where a signature no longer tells you whether
calling something is safe. Uniformity deletes the question. It is also the shape of the stack we chose:
LangGraph nodes are awaited by `graph.astream()`, FastAPI endpoints are coroutines, SQLAlchemy runs on
`asyncpg`, and barge-in (§1.3) *is* `asyncio` task cancellation.

And it is not free later. Converting a sync codebase to async rewrites every call site; starting async costs
nothing.

**The exception is honest rather than convenient.** A numerical kernel is CPU-bound — marking it `async def`
would advertise that it yields when it never does, blocking the loop for its full duration behind a signature
that says otherwise. So `math/` modules are sync, they are the only sync functions in `app/`, and every call
into them is offloaded with `asyncio.to_thread` at the call site where the cost is visible.

### 4.2 Maths never lives in the file that uses it

Also stated by the product owner, and it is the reason `math/` exists as a folder: **when a service deals with
maths, the maths does not go inside the service file.** It goes in a sibling `math.py`, or a `math/` package,
inside that subsystem's own folder.

The instruction as given was about being able to *tell the two apart* — to open a service and see application
logic, and open `math/` and see arithmetic, without the two braided together. Three things follow from it that
make it more than tidiness:

- **The maths is the part that has to be provably right.** A formula isolated in `math/` is a pure function
  over arrays, and its test is three lines checked against QGIS or a hand calculation. The same formula
  entangled with band lookup, mask application, config reads and a database write cannot be tested that way
  without standing the whole system up — and untested arithmetic is how this product breaks its one promise.
- **It is where the scientific boundaries live or die** (`architecture-context.md` §8). Equal-area
  reprojection before hectares, nodata propagating as a mask, reflectance rather than digital numbers. In one
  named place per subsystem those can be read and reviewed. Scattered through service logic they can only be
  hoped for.
- **"Which formula" changes constantly; "the formula" never does.** Choosing NDVI over NDWI for a query is
  routing. `(nir - red) / (nir + red)` is physics. Mixed together, every routing change edits code that
  should never be touched again.

`architecture-context.md` §12 states the boundary; `folder-archtecture.md` places the files.

---

## 5. Compute, and why the model manager is written the way it is

The development GPU is **8 GB today, with a move to a 24 GB machine expected.** The system must run correctly
on 8 GB and simply run *faster* on 24 GB — the same code, no branch, no rewrite.

So the `ModelManager` is built for the small card first:

- Detects available VRAM at startup and selects a **profile** (`vram-8` / `vram-16` / `vram-24`), overridable
  from `.env`. The profile sets weight precision, inference tile size, batch size and how many models may be
  resident at once.
- **Lazy loads and LRU-evicts** under a lock. On 8 GB roughly one large model is resident at a time; on 24 GB
  several are, and the eviction path simply stops firing.
- Exposes its real state as the fleet health the frontend already renders: `warming` is a model loading,
  `queueDepth` is the depth of the lock queue, `degraded` is a model running below its profile.

That last point is worth keeping: **the Model Observatory shows real telemetry, not decoration**, because the
health enum the frontend defined happens to be exactly the manager's state machine.

---

## 6. The language model is a swappable component

**OpenAI is the current provider.** The requirement attached to that choice is explicit: swapping it must be a
change in `config.py` and nothing else.

That requirement is met by **LangChain's `init_chat_model`**, which takes the provider and model as strings and
returns a chat model exposing the same `with_structured_output` / `bind_tools` / streaming surface whichever
provider is named. Completion, structured output, tool calling and embeddings all come from the library
directly.

So the agent depends on `app/lib/llm/`, which is about forty lines calling `init_chat_model` with values from
`config.py`, and never on a vendor SDK. **An earlier draft specified an `LLMProvider` protocol with hand-written
adapters here. That is cancelled** (ADR-002): it would have re-implemented provider selection, structured
output and tool binding by hand, and Phase 1.9's gate — "write a second adapter to prove the seam holds" —
becomes a one-line `.env` change instead of a week's work. `lib/llm/` exists only so that the model name and
provider are read from config in one place, not to abstract the library.

This is still insurance against the risk register: the agent layer is the component most likely to be
replaced, and the one whose replacement would otherwise touch the most code.

---

## 7. Deadline

**SIH 2026 grand finale, December 2026.** Roughly three months from 2026-08-30.

Consequences: the MVP and SIH tiers from PDF p.44 are the scope; ADV and FUT are deferred *explicitly and in
writing* rather than quietly dropped. Voice is the exception — the PDF rates it low demo value per
engineering day, and the product owner has overruled that. It is the product's identity here.

Demo hardening (PDF Phase 10) is real work with a real cost and is scheduled, not assumed.
