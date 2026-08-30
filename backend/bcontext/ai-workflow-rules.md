# Development Workflow

## Approach

Build this project incrementally using a spec-driven workflow. Context files define what to build, how to build it, and what the current state of progress is. Always implement against these specs — do not infer or invent behavior from scratch.

## Scoping Rules

- Work on one feature unit or subsystem at a time.
- Prefer small, verifiable increments over large speculative changes.
- Do not combine unrelated system boundaries in a single implementation step.


If a change cannot be verified end to end quickly, the scope is too broad — split it.

## Handling Missing Requirements

- Do not invent product behavior that is not defined in the context files.
- If a requirement is ambiguous, resolve it in the relevant context file before implementing.


## Protected Foundation Components

Do not modify generated third-party foundation components unless explicitly instructed.

This includes:

- `components/ui/*` (shadcn/ui components)
- third-party library internals

These should remain default and reusable.

Project-specific styling, layout changes, and feature logic must be implemented in app-level components instead of modifying foundation components.

Only modify these files when a task explicitly requires it.

## Keeping Docs In Sync

Update the relevant context file whenever implementation changes:

- System architecture or boundaries
- Storage model decisions
- Code conventions or standards
- Feature scope



## Before Moving To The Next Unit

1. The current unit works end to end within its defined scope.
2. No invariant defined in `architecture-context.md` §13 was violated. In particular, check the four that are
   easiest to break without noticing:
   - **Nothing hand-written orchestrates, checkpoints, streams or retries.** LangGraph owns the graph and its
     state; Inngest owns retry and replay; LangChain owns LLM access (ADR-002).
   - **Every function added is `async def`**, except functions inside a `math/` module, which are sync and are
     called through `asyncio.to_thread` (ADR-003).
   - **No numerical method was written inside a service, node, controller or route.** It belongs in that
     subsystem's `math/` (ADR-003).
   - **No hardcoded fixed set outside `app/constants/`, and no `os.environ` outside `config.py`.**
3. Also refer to `folder-archtecture.md` for the folder structure and each folder's purpose — including its
   "Placement questions, answered" table when a new file has no obvious home.
4. `memory.md` has an entry for the session.
