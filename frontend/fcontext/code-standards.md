# Code Standards

## General

- Keep modules small and single-purpose.
- Fix root causes — do not layer workarounds.
- Do not mix unrelated concerns in one component or route.
- Respect the system boundaries defined in `architecture-context.md`.


## Next.js

- Default to React Server Components.
- Add `"use client"` only when the component needs browser interactivity, hooks, or real-time state.
- Keep route handlers focused on a single responsibility.
- Long-running work belongs in background tasks, not in request handlers.
- write proper typescript practice code avoid use of any and write modular tracebale code

## API Routes

- Validate and parse request input before any logic runs.
- Return consistent, predictable response shapes.
- Keep route handlers thin — push complexity into shared modules or background tasks.


## File Organization

- refer `folder-archtecture.md`
