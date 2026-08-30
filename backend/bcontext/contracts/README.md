# The frontend's contract, vendored. Generated — do not edit.

**what** : `schemas.json` — every Zod schema in `frontend/` converted to JSON Schema (draft 2020-12).
92 schemas from 14 modules, keyed by source module then by exported schema name.
**where**: Read by `tests/contracts/`, and by Phase 2 when a route serialises a payload one of these
schemas will receive. Written by `frontend/scripts/export-contracts.mts`.
**how**  : `api-contract.md` §0 makes the frontend's Zod authoritative. This directory exists so the backend
can be *held* to that rather than asked to match a copy of it by hand.

---

## Regenerating

```bash
cd frontend
pnpm run contracts:export     # rewrites backend/bcontext/contracts/schemas.json
pnpm run contracts:check      # exits 1 if the committed file is stale. For CI.
```

**Run the export in the same change as the Zod edit.** `contracts:check` exists so that forgetting is
caught rather than discovered later as a backend that validates against a contract nobody is using.

## Three things about this file that are deliberate

**It is committed, not generated at test time.** A test that regenerates its own fixtures proves nothing
about the thing it is fixed against — it would pass by construction. Committing it also means the backend
suite needs no Node, so `uv run pytest` works on a machine that has never installed the frontend.

**The output carries no timestamp and its keys are sorted.** Regenerating an unchanged contract produces a
byte-identical file, so a diff here means *the contract changed* rather than *someone ran the script*. That
is also what makes `contracts:check` meaningful.

**Schemas are inlined, not `$ref`-linked.** `geoBoundingBoxSchema` appears in full inside every schema that
composes it, which is why the file is ~276 KB for 92 schemas. The alternative — one document of `$defs` with
cross-references — is smaller and would put a reference resolver between every Python test and the thing it
is validating. Each entry here is self-contained and can be handed straight to a validator.

**`io: "input"`.** The frontend calls `schema.parse(response.data)`, so a backend payload is the schema's
*input*. Any schema carrying a `.transform()`, a `.default()` or a coercion has a different output type, and
exporting the output side would demand values the backend cannot send — a `Date` object where the wire has a
string. Nothing currently transforms; the flag is set so that the day one does, this stays correct silently
instead of breaking loudly.

## What checks it

| Test | What it prevents |
|---|---|
| `test_shared_vocabularies.py` | The backend inventing a vocabulary the frontend owns — the `changeformer` / `mdl_changeformer` class of bug (`api-contract.md` §7). Every backend `StrEnum` must be paired with a frontend schema or declared backend-only **with a reason**, so a new enum forces a decision. |
| `test_wire_payloads.py` | A payload that does not match: `model_dump()` without `by_alias=True`, `exclude_none=True` dropping a nullable-but-required key, a timestamp without its `Z`. |

The classification lives in `app/constants/contracts.py`, which also records — as a list, checked
mechanically — every frontend vocabulary the backend has **not** met yet, with the phase that will.
