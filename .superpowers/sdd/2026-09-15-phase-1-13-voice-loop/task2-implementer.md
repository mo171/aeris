# Task 2 — Frontend command-event bridge

## Implementation

- Added Vitest and a focused `pnpm test` command.
- Added `dispatchUiCommandEvent`, which delegates execution and parameter validation only to the command bus and returns its discriminated `CommandDispatchResult`.
- Added result observation so stream owners can log non-completed command proposals without throwing into stream processing.
- Wired `ui-command` handling into both assistant and analysis streams with fire-and-observe dispatches; later frames remain independent of an unsuccessful proposal.

## RED evidence

1. `pnpm test -- ui-command-bridge.test.ts` failed with `Cannot find module './ui-command-bridge'`, proving the requested bridge did not yet exist.
2. After adding the observer test while withholding its implementation, the same command failed with `expected [] to deeply equal ['not-found']`, proving that stream observability was not accidental coverage.

## GREEN evidence

- `pnpm test -- ui-command-bridge.test.ts` — 1 file, 6 tests passed. Coverage exercises completed, not-found, invalid-params, disabled, and failed results, runs a valid command after every non-completed result, and checks observer delivery.
- `pnpm exec eslint lib/streaming/ui-command-bridge.ts lib/streaming/ui-command-bridge.test.ts features/investigation/hooks/use-analysis-run.ts features/missionCommand/hooks/use-assistant-session.ts` — passed with no findings.
- `git diff --check` — passed with no whitespace errors.
- `pnpm exec tsc --noEmit` remains blocked by pre-existing errors outside this task: `components/sharedUI/workflowCanvas/WorkflowCanvas.tsx` uses unsupported `"dots"`, and `features/investigation/components/tracePanel/VersionCanvas.tsx` references missing version fields (`authorName`, `authorId`, `description`). No bridge, hook, or test diagnostics were reported.

## Commit

Implementation commit: `4c96e4456b6606c528a9901d5a9e27b18fb86555` (`feat: dispatch streamed interface commands`).

## Self-review

- Command ids and parameters have no alternate execution path; the existing registry remains the sole lookup, Zod parsing, enabled-state, and handler boundary.
- Non-completed command results are retained for diagnostics and never change stream state or block subsequent event processing.
- Test registrations are unregistered after every case, preventing global command-registry state from leaking between stream-behavior assertions.
