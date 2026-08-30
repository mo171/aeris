# bcontext — read this first, then read in the order below.

**what** : The entry point for every human and every AI agent working on the AERIS backend. It says which
document is authoritative for which question, and in what order to read them.
**where**: Read at the start of every backend session, before opening any source file. Every other bcontext
document assumes you arrived through here.
**how**  : Each document below owns exactly one kind of question. When two documents appear to disagree, the
one listed as authoritative for that question wins, and the other is stale and must be corrected.

---

## Read order

| # | Document | Authoritative for | Read when |
|---|---|---|---|
| 1 | `product-truth.md` | **What we are building and why, including the parts not written in the PDF.** Voice-first agentic control, the two-phase build, the engineering standard. | Every session. Start here. |
| 2 | `roadmap.md` | **What to build next.** Phases, sub-phases, gates, current status. | Every session. |
| 3 | `architecture-context.md` | Layering, dependency direction, scientific boundaries, tech stack, and **the numbered invariants** every change is checked against. | Before writing any service, pipeline or worker. |
| 4 | `folder-archtecture.md` | Where a file goes. | Before creating any file. |
| 5 | `code-standards.md` | How a file is written — headers, naming, config and constants discipline. | Before writing any file. |
| 6 | `api-contract.md` | **The wire.** Endpoints, payload shapes, stream events, and the rules the frontend depends on. | Before touching anything the frontend consumes. |
| 7 | `architecture-decisions.md` | Why a technology was chosen, and what was rejected. | Before changing or re-litigating a technology choice. |
| 8 | `ai-workflow-rules.md` | How to scope a unit of work and when it is done. | Every session. |
| 9 | `memory.md` | What the previous session did, decided, and left broken. | Every session, and **update it at the end of every session.** |

## The one-paragraph version

AERIS answers questions about satellite imagery with evidence, not with fluent text. Specialist
remote-sensing models produce structured, checkable results; the language model explains those results and
is never permitted to invent one. Every claim carries a georeferenced region, the model and version that
produced it, a confidence, and a full execution trace. The system is driven by voice and by an agent that
controls both the analysis and the interface. It answers on **three surfaces at once** — written, spoken,
and **shown**: the backend renders the imagery it reasoned over into captioned, legended images and the agent
explains them out loud (`product-truth.md` §1.5).

## Four rules you will otherwise get wrong on your first file

Stated here because they are absolute, and because they cost nothing on day one and a rewrite later.

1. **LangGraph owns all orchestration.** Graph topology, typed state, conditional routing, resume from a
   checkpoint, plan approval via `interrupt()`, and streaming through `stream_mode="custom"`. **We write no
   orchestration code of our own** — no `StepRunner`, no `EventSink`, no `LLMProvider`. ADR-002 deleted all
   three; if a document still describes them as things to build, it is stale and
   `architecture-context.md` §4 wins.
2. **Inngest owns the retry loop, and nothing else owns any part of it.** Trigger, backoff, replay,
   dashboard. No node, service or client implements its own retry — including ingest, which is the one most
   tempted to (ADR-002).
3. **Every function is `async def`.** The only exception is a `math/` module, which is sync and is called
   through `asyncio.to_thread` (ADR-003, `code-standards.md` §7).
4. **Maths never lives in the file that uses it.** A subsystem that computes a number carries a sibling
   `math/` package: the service chooses *which* method, `math/` contains *the* method (ADR-003,
   `code-standards.md` §8).

## How you are expected to work here

You are not a code generator pointed at a spec. Work as a **senior engineer who is at once a software
engineer, an ML engineer and an agentic-systems developer** — someone who has shipped a system like this
before and has earned opinions about it. Bring judgment, not just compliance. Every item below is an
acceptance criterion, not encouragement.

**Do not build what already exists.** Before writing a class, check whether something in the stack already
does it. ADR-002 exists because three protocols were designed before anyone checked that LangGraph and
LangChain already shipped them — days of work that had to be deleted from a plan. That check is your job on
every file, not a one-off. A custom abstraction over a library is a cost you pay forever and a capability
you lose immediately.

**No AI slop.** The product owner's phrasing, and it is the standard (`product-truth.md` §4). In practice:

- No abstraction without a second real caller. No configurability nobody asked for.
- No defensive scaffolding around things that cannot fail. No `try/except` that swallows and logs.
- No comment restating the line below it. Comments explain *why*, or a failure mode, or nothing.
- No placeholder that pretends to work. If something is not built, it raises or it is not there.
- No plausible-looking numerics. This domain punishes them harder than it punishes crashes — a wrong
  hectare figure is quoted in a report, an exception is not.

**Notebooks are research instruments. Some are teaching material for the product owner; most are for you.**
The rule is the same either way: **write a notebook only when the conclusion you will draw from it is going
to change the code you write next.** Then actually use that conclusion — put it in a doc, a constant, a
threshold, a comment naming the failure mode you found.

Do not write notebook cells because the roadmap says "notebook". If you already know the answer, say so and
skip it. If a notebook would tell you something real — what this sensor's nodata actually looks like, whether
this threshold holds on this scene, why a filter destroys the feature you care about — then it is worth every
token. The test is simple: **if nothing downstream would change based on the output, do not write it.**
Nothing ships out of a notebook; conclusions do.

**Disagree with a reason.** If a document here is wrong, say so and correct it in the same change. A stale
document that everyone works around is worse than no document. Three of these files were corrected on
2026-08-30 for exactly that reason.

## Two documents that are NOT in this folder and are still authoritative

- `../../context/idea.md` — the product overview and a page index into the PDF.
- `../../context/SatqueryAI.pdf` (text at `pdf_extracted.txt`) — the research, the 20-stage pipeline, the
  module table M1–M22, the feature tiers, the risk register and the reference list. **Cite page numbers
  when a design decision comes from it.**

## The frontend is a source of truth for the backend

The frontend is built and running against mocks. It has already specified this backend's wire format. Three
files in `../../frontend/` are contract, not suggestion:

- `lib/constants/rest.api.ts` — the endpoint registry.
- `features/*/schemas/*.schema.ts` — the exact payload shapes, as Zod.
- `fcontext/memory.md` — contains three sections titled **"Message for the backend developer"** with hard
  requirements. Read them.

`api-contract.md` in this folder is the backend-side transcription of those, plus what we are adding.
