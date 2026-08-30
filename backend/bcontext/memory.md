# Backend Memory

Session log for the AERIS backend. Newest first. Written for the next agent or developer picking this up
cold: what was decided, why, what is still broken, and what not to relitigate.

---

## Session — 2026-08-30 (0.2) · Persistence. Eight tables, and five bugs — two of which only the live database could find.

**Phase 0.2 is done and the gate is demonstrated.** Against a live PostGIS 3.5.2 / Postgres 17.5:
`alembic upgrade head` from base builds 8 tables, 7 GiST indexes and 24 check constraints; `alembic downgrade
base` removes every one of them; `alembic check` reports **no changes**, which is the proof that the schema
and the models agree; 25/25 tests pass, the 4 integration tests included.

Measured for the record — a 1x1 degree box reads `ST_Area` = 1.0 in degrees at both the equator and 60 N,
while on the spheroid it is 12,308.8 km2 and 6,122.9 km2. That factor of two is the whole reason for
`architecture-context.md` §8 rule 3. PostGIS sits 0.44% below the spherical closed form at the equator and
0.57% above it at 60 N; the test tolerance is 1%.

### What was built

| File | What it settles |
|---|---|
| `docker-compose.yml` | `postgis/postgis:17-3.5`, bound to **127.0.0.1:5433** |
| `app/constants/geo.py` | Storage SRID, and the **two** sanctioned ways to measure an area |
| `app/constants/investigations.py` | `WorkspaceMode` — was missing, needed by `investigations.mode` |
| `app/constants/statuses.py` | `TraceStepState` and `SceneProcessingState` added |
| `app/db/identifiers.py` | Prefixed ULIDs — `scn_`, `inv_`, `run_`, `stp_`, `ev_`, `clm_`, `msn_` |
| `app/db/models/` | `base.py` + 7 modules → 8 tables |
| `app/lib/database.py` | The one async engine, `get_session()`, `check_health()` |
| `alembic.ini`, `migrations/env.py`, `0001_initial_schema` | Schema migrations |
| `tests/conftest.py`, `tests/unit/test_identifiers.py`, `tests/integration/` | 21 unit + 4 integration |

### Two bugs the live database found, after the offline checks were already green

**Alembic silently rolled back every migration.** `migrations/env.py` gained a `_load_extension_owned_tables`
query that runs a `SELECT` on the connection *before* `context.configure`. SQLAlchemy 2.0 begins a
transaction on first execute; left open, Alembic's own transaction handling nests inside it and never commits
the outer one. `alembic downgrade base` printed "Running downgrade", **exited 0, and changed nothing** — the
version table still read `0001_initial_schema` and all eight tables were still there. Fixed with
`connection.rollback()` immediately after the read.

Two lessons worth more than the fix. **`alembic upgrade` reporting success is not evidence that anything
was written** — check the tables. And **`uv run alembic ... | tail -2` discards alembic's exit code**,
because the pipeline reports `tail`'s status; that is how the failure survived a `&&` chain and looked like
a passing round trip.

**The round-trip test asserted formatting, not geometry.** It compared `ST_AsText` output against the input
string, and PostGIS normalises `77.0` to `77`. The geometry was never wrong. Now compares `ST_Equals`, SRID,
vertex count and the four bounds.

### Three bugs found before they could ship

**`file_size_bytes` was `INTEGER`.** That caps at 2.147 GB, which a multi-band scene passes — so ingest
would have failed on precisely the large acquisitions this system is for. Now `BIGINT`.

**Constraint names were doubled in the migration** — `ck_claims_ck_claims_confidence_is_a_fraction_or_null`.
The naming convention in `base.py` is `ck_%(table_name)s_%(constraint_name)s`, so a migration passing the
*full* name gets it prefixed again. The models pass the bare name; the migration now does too. Left
unfixed, the next `--autogenerate` would have proposed dropping and recreating every check constraint.

**A config test was passing for the wrong reason.** `test_invalid_enumerated_value_is_rejected` asserts
`pytest.raises(ValidationError)`; once `DATABASE_URL` became required, it caught *that* instead and would
have kept passing even if the `Literal` on `environment` were deleted. Now it asserts the error names
`environment`, and `tests/conftest.py::mandatory_environment` supplies required fields so a test can break
exactly one thing. **This will recur** — every future required setting re-arms it. Add the field to
`MANDATORY_ENVIRONMENT` in the same change.

### Decisions worth not relitigating

- **`wire_enum()` uses `values_callable`.** SQLAlchemy persists an enum member's `.name` by default, so
  `EvidenceKind.CHANGE_MASK` would be stored as `CHANGE_MASK` while the frontend expects `change-mask`.
  Pinned by `test_wire_enum_stores_values_not_member_names`.
- **`native_enum=False`** — VARCHAR + CHECK, not a Postgres ENUM type. A PG enum cannot drop a value, so
  every frontend vocabulary change would become a type migration.
- **Prefixed ULIDs, not UUID4 and not a sequence.** Time-ordered, so the PK index appends instead of
  fragmenting, and cursor pagination gets a stable total order without a second sort column. The prefix
  makes "a run id passed where a scene id was expected" visible on sight.
- **Areas are measured two ways, and `constants/geo.py` says which is which.** Vector geometry in the
  database uses `::geography` (spheroidal, correct anywhere, no projection choice). Raster pixel counting in
  Phase 1.4+ uses a *local* LAEA centred on the scene, because a spheroidal integral is unavailable for a
  pixel grid and a global equal-area grid shears scene-scale data enough to bias which pixels a mask
  contains.
- **The role lives on `investigation_scenes`, not on `scenes`.** A partial unique index enforces one scene
  per singular role, excluding `aux`.
- **The investigations ↔ missions foreign keys are a real cycle**, broken with `use_alter`; the migration
  adds both constraints after both tables exist.
- **Geometry columns in the migration declare `spatial_index=False`**, though the models declare `True`.
  It is a DDL-generation hint: left on, GeoAlchemy2 creates the GiST index through its own event *and* the
  migration creates it explicitly. `migrations/env.py` excludes `idx_*` from autogenerate for the same
  reason — GeoAlchemy2's prefix is `idx_`, ours is `ix_`.
- **The first migration is hand-written.** `CREATE EXTENSION postgis` must precede any geometry column and
  autogenerate cannot know that.
- **`downgrade()` does not drop the extension.** It may predate this schema, and another schema in the same
  database may hold geometry columns.

### Port 5432 was already taken

An existing Postgres is listening on this machine — the integration tests failed with
`password authentication failed for user "aeris"` against a database that is not ours. The container is now
on host port **5433**. Worth knowing before assuming a connection failure means the container is down.

### A throwaway I did not keep

I wrote a SQL differ to compare the migration's rendered DDL against DDL compiled from `Base.metadata`. It
found the doubled constraint names and was then abandoned: **`alembic check` does this properly** and needs
only a live database. Do not rebuild the differ.

### Two things the live database changed in the setup

**The image installs extensions we do not use.** `postgis/postgis` enables `postgis_topology`,
`postgis_tiger_geocoder` and `fuzzystrmatch`, and puts `topology` and `tiger` on the `search_path` — so
reflection saw about a hundred tables no model describes and `alembic check` reported six of them as
"removed". `docker/postgis-init/20_trim_extensions.sql` drops all three on a fresh volume, and
`migrations/env.py` additionally filters **extension-owned tables by querying `pg_depend`** rather than
keeping a name list, because Supabase may install them where we cannot drop them.

**The 15 enum CHECK constraints always read as "removed".** SQLAlchemy declares them through the column's
`Enum` type rather than as table-level `CheckConstraint` objects, so autogenerate reflects them and finds no
counterpart in the metadata. `env.py` now computes their names from the metadata and excludes them. Without
this, `alembic check` reports the same 15 differences on an identical schema — and a check that always fails
is a check nobody reads.

**Tests share one event loop** (`asyncio_default_test_loop_scope = "session"`). The engine is a process-wide
singleton whose pooled asyncpg connections belong to the loop that opened them; with a loop per test the
second test to touch the database died with "Event loop is closed". One session loop also matches
production, where the CLI calls `asyncio.run()` once.

### Next session

0.3 — Redis. Follow the same pattern: provision in compose, client in `app/lib/redis.py`, health probe,
a row in `aeris doctor`, a test.

---

## Session — 2026-08-30 (latest) · Phase 0.1 done. The first real code in `app/`.

The documents stopped being the work. `app/` now contains code that runs, and the Phase 0.1 gate is
demonstrated rather than asserted.

### What was built

| File | What it settles |
|---|---|
| `pyproject.toml` + `uv.lock` | The dependency set, and `requires-python = ">=3.14,<3.15"` |
| `app/config.py` | `pydantic-settings`; `settings = Settings()` at import, so misconfiguration fails before anything mounts |
| `.env` / `.env.example` | Every configurable field, documented, with no secret values committed |
| `app/constants/` × 12 | stages · model_ids · intents · scenes · statuses · evidence · layers · reports · figure_kinds · errors · logs · pagination |
| `app/lib/logger.py` | `async def configure_logging()` and nothing else |
| `app/lib/exceptions.py` | `AerisError` + 7 subclasses, each with a stable `code` and a status |
| `app/lib/responses.py` | `CamelCaseModel`, `CursorPage[TItem]`, `CursorPageRequest`, `ApiErrorPayload` |
| `tests/unit/` | 12 tests. Green. |

### The gate, shown

- `uv lock --check` → in sync. `uv sync --frozen --dry-run` → "would make no changes", so the lock alone
  reproduces the environment without re-resolving.
- `ENVIRONMENT=prod uv run python -c "import app.config"` → `ValidationError` **at import**, naming
  `environment` and listing the four legal values. A missing variable behaves the same way and is covered by
  `test_missing_required_variable_raises_and_names_the_field`, which passes `_env_file=None` — without that,
  the test would pass by reading the very `.env` whose absence it is meant to be testing.

### The Python 3.14 risk is closed. Do not reopen it.

`uv pip install --dry-run --only-binary :all:` against the 3.14.5 venv resolved **every** heavy dependency as
a cp314 wheel: torch 2.13.0, torchvision 0.28.0, transformers 5.16.1, timm 1.0.29, ctranslate2 4.8.1,
faster-whisper 1.2.1, onnxruntime 1.29.0, tokenizers 0.23.1, plus langgraph/langchain and typer/rich/structlog.
The previous session left this open as the largest unknown in Phase 0. There is no reason to downgrade to 3.12,
and no reason to rebuild the working scientific venv.

### `requirements.txt` was lying, which is why it is gone

The 131-line freeze listed `earthpy` (imported nowhere) and **omitted** `pystac-client`,
`planetary-computer`, `rioxarray` and `xarray` — which `notebooks/01_remote_sensing/` imports on every run and
which were installed in the venv. A naive `uv sync` from that file would have pruned the libraries the owner's
notebooks depend on. All four are now declared (the first two as runtime, since `aeris dataset fetch` needs
exactly what notebook 01 does by hand; xarray/rioxarray as dev, because the application reads windows through
rasterio rather than whole datasets). `git rm`'d, recoverable from history.

`uv sync` also removed `fastapi`, `uvicorn`, `starlette` and `inngest`. **That is correct, not a regression.**
Inngest returns in 0.3 and FastAPI in 2.1, each added by the sub-phase that first needs it. `app/workers/` was
also removed from disk — empty, and ADR-002 deleted it from the plan.

### Decisions worth not relitigating

- **`StrEnum`, not `Literal` or bare constants**, for every wire vocabulary. Pydantic validates against it for
  free, it serialises as the exact string the frontend expects, and Phase 0.7's contract tests can iterate it.
- **No `Formatter` subclass.** The previous session expected one, and expected to carve a sync exception into
  `code-standards.md` §7 for it. Not needed: `JsonFormatter(fmt=..., rename_fields={"levelname": "level",
  "name": "logger"}, timestamp=True)` produces the wanted shape, and anything passed as `extra=` is merged in
  automatically. Verified by running it. **Do not build what the library already does.**
- **§7 did get a second exception**, but for a different and narrower reason: `to_error_payload()` is sync
  because errors are rendered from sync contexts, and framework callbacks are sync because the framework calls
  them. The test written into §7: *no I/O now, and no plausible I/O later.* `configure_logging()` fails that
  test — it awaits nothing today and is still `async def`, because a log handler that writes to a socket is a
  plausible next version of it.
- **Console logging drops `extra=` fields.** rich prints the message only. Accepted, and written into
  `lib/logger.py`: `json` is the diagnostic format, and in Phase 1 the human surface is the CLI's rich trace of
  S1–S20, not the log stream. Anyone debugging a run switches to `json` and filters on `run_id`.
- **Names that changed from the sketch in `folder-archtecture.md`**, which is now updated to match the code:
  `modalities.py` → **`scenes.py`** (it holds modality *and* both role enums, and "modalities" would be a
  misnomer for `SceneRole`), and `limits.py` → **`pagination.py`** (named for what it bounds; `limits.py` is the
  kind of name that becomes a junk drawer).

### What was deliberately *not* written, and why

The instinct in a skeleton phase is to fill every file the architecture names. Each of these was left out
because nothing reads it yet, and a constant nothing reads is a claim no test verifies:

- **`constants/ui_commands.py`** — the ~60 command ids. `api-contract.md` §4 does require the backend to mirror
  them, but a mirror written months before the first `ui-command` event is a mirror that has already drifted.
  Write it when the event is first emitted, transcribing `commands.ts` in that same change.
- **`constants/color_ramps.py`** — Phase 1.2.1, with the renderer that draws them. A ramp list written now would
  describe ramps nothing can draw.
- **The per-model capability mapping** — fleet truth, established in 1.6/1.7 when the models are wired. A
  guessed mapping would route a request to a model that cannot serve it.
- **`constants/tasks.py`** — Phase 0.3, with Inngest.
- **`runs_directory` and any storage settings** — 0.4, with the buckets. `config.py` holds only fields that are
  read today.

### Next session

0.2 — Supabase + PostGIS. `app/lib/database.py`, Alembic, and the first migration. The gate is a polygon
round-trip whose area is correct **in an equal-area projection**, which is the one part of that sub-phase worth
being careful about: an area computed in EPSG:4326 degrees is wrong in a way that looks plausible.

---

## Session — 2026-08-30 (figures) · The backend sends images. Agent conduct and the notebook rule written down.

Two things happened: a capability that was missing from every document was added, and the standard the agent
working here is held to was made explicit instead of implied.

### The missing capability: the backend renders figures and sends them

The product owner's instruction, in effect:

> The backend should also be sending images to the frontend — images with bounding boxes, 2D images like the
> ones in notebook 01: take the data, map it, show it to the user, and the AI can explain that image too.
> There is a reference space in the frontend UI where those images can go — it pops out as a new window, it can
> go to the second screen. This is crucial: **we control the render, so we can show literally anything.**

**Nothing in these documents described this.** Not the PDF, not `product-truth.md`, not `api-contract.md`. There
was exactly one visual path — COG → TiTiler → XYZ tiles → Cesium — and that path is for *place*: a fragment
draped on the globe, no legend, no annotation, composited by the browser.

The distinction that is now written into four documents:

> **A tile is a fragment for the globe. A figure is one self-contained picture that carries its own legend.**

A figure can draw a colourbar, put boxes and labels on the image, place T1 and T2 side by side with the change
mask between them, and be looked at with no WebGL context at all. `notebooks/01_remote_sensing/` has been
producing exactly these all along — `imshow` with a named ramp and explicit `vmin`/`vmax`, a labelled
colourbar, masks as binary images, SAR as `10·log10` into a dB window. Nothing carried them to the frontend.

**The second reason it matters, which is not about presentation.** At S14 the VLM is handed a rendered image to
reason over. If that render is not deterministic and its parameters are not recorded, nobody can say later what
the model was looking at. So a figure is part of the evidence chain, and the stretch is not a cosmetic choice:
widen it and a drought disappears, narrow it and healthy crop looks stressed.

Written into:

| Document | What was added |
|---|---|
| `product-truth.md` | **New §1.5** — the three surfaces (written, spoken, **shown**), the six figure kinds, why this is not the tile pipeline, and why the product owner calls it crucial |
| `api-contract.md` | **New §6** — the `figure-ready` event with its `legend`, `renderSpec` and `traceStepId`, eight rules, and two endpoints. Old §6–§8 renumbered to §7–§9 |
| `architecture-context.md` | `rendering/` in the §7 subsystem table, **scientific boundary 13**, **invariant 19**, Matplotlib/Agg + Pillow in the §9 stack |
| `folder-archtecture.md` | `services/rendering/` with its `math/`, `schemas/events/figure.py`, `figure_controller.py`, `cli/renderers/figure_writer.py`, `routes/figures.py`, two `constants/` vocabularies, four placement rows |
| `roadmap.md` | **New sub-phase 1.2.1**, the `figures` bucket in 0.4, figures in the 1.5 gate, figures replacing "tiles" in 1.7, the endpoints in 2.3 |
| `architecture-decisions.md` | **ADR-004**, with the alternatives that were rejected |

**Why 1.2.1 and not a later number.** 1.4 produces the first index array, 1.5 the first mask, 1.6 the first
boxes, 1.7 hands an image to the VLM. Building the render primitive before all four means each emits its figure
as it lands rather than being retrofitted. The number is deliberately `1.2.1` so nothing from 1.3 onwards had
to be renumbered. Its gate uses only what 1.2 already produces — an RGB composite, an index map with a
colourbar, a mask overlay — and **re-rendering from the recorded `renderSpec` must be byte-identical.**

**What Phase 1 does with figures given there is no browser:** `cli/renderers/figure_writer.py` writes them to
`runs/<run_id>/figures/` and prints the path, exactly as `journal_writer.py` makes the wire testable before a
route exists.

**Coordinated frontend change.** The frontend has the *mechanisms* — detached pop-out windows (`/scene/[sceneId]`,
deliberately outside the geospatial route group so a window whose job is one picture does not boot a globe) and
the `app/(reference)/` route group. It does **not** have the figure surface, and `ROUTES` has no entry for it.
Same status as `ui-command` and `speech`.

### The conduct rules, in `README.md` → "How you are expected to work here"

Product owner's instruction: whoever works on this backend works as **a senior software engineer, an ML
engineer and an agentic-systems developer** — not a code generator pointed at a spec. Three enforceable parts:

1. **Do not build what already exists.** ADR-002 is the precedent: three protocols were designed before anyone
   checked that LangGraph and LangChain already shipped them.
2. **No AI slop.** No abstraction without a second real caller; no `try/except` that swallows; no comment
   restating the line below it; no placeholder that pretends to work; **no plausible-looking numerics** — this
   domain punishes those harder than crashes, because a wrong hectare figure gets quoted in a report and an
   exception does not.
3. **Disagree with a reason**, and fix the document in the same change.

### The notebook rule — this one changes behaviour, not just tone

> Some notebooks are for me, most are for you. Carry out notebook research as if the conclusion you draw is
> actually going to be used. Don't burn tokens writing notebook code because I said "notebook" — do it because
> it is important for the research or will help you write something better.

The operative test, now in `README.md` and as standing rule 1 of `roadmap.md`: **if nothing downstream would
change based on the output, do not write it.** If you already know the answer, say so in `memory.md` and skip
to writing the code. If you do run one, use the conclusion — a threshold, a constant, a comment naming the
failure mode. Nothing ships out of a notebook; conclusions do.

**Applied immediately, as the first test of the rule:** sub-phase 1.2.1's research line says *none needed, and
no notebook* — notebook 01 already establishes the render idiom, so the conclusion is drawn and the honest next
step is library code. Under the old standing rule, that sub-phase would have opened with a notebook nobody
needed.

### Confirmed, not to be relitigated

ADR-003's exception — `math/` modules are the **only** sync surface in `app/`, reached with
`asyncio.to_thread` — was put to the product owner and confirmed correct. ADR-003 stands as written.

### Next session

**Phase 0.1**, in progress at the end of this session. One open risk to resolve inside it: the `.venv` is
**Python 3.14.5**. rasterio, geopandas, numpy and matplotlib all work on it, but **PyTorch and ctranslate2
(faster-whisper) may have no cp314 wheels** — which 1.6, 1.7 and 1.13 all depend on. Check cheaply with a
dry-run install before pinning `requires-python`; do not destroy a working scientific venv on a guess.

---

## Session — 2026-08-30 (later) · The three custom protocols are cancelled. Async and maths rules added.

No implementation code this session either. The output is a documentation correction, and it is worth reading
before anything else in this folder, because it reverses part of the entry below it.

### What was wrong

`architecture-decisions.md` had already recorded **ADR-002** — LangGraph owns orchestration, Inngest owns
durable execution — but the decision had only been propagated into `architecture-context.md` §3–§4. Seven
other places still described `StepRunner`, `EventSink` and `LLMProvider` as things to build:
`architecture-context.md` §9 and §11, `roadmap.md` 1.0 / 1.9 / 1.10 / 2.3 / 2.5 and its folder-additions
block, `product-truth.md` §2 and §6, `code-standards.md` §8, and `api-contract.md`'s header. A developer or
agent starting from `roadmap.md` 1.0 — which is exactly where they would start — would have spent Phase 1.0
writing three protocols that ADR-002 had already deleted.

The phrase "custom stream" was also ambiguous. It means **LangGraph's `stream_mode="custom"`**, a library
feature, and read as though it meant a streaming mechanism of ours. Now stated explicitly in
`architecture-context.md` §4.

### The product owner's instruction, verbatim in effect

> All orchestration is LangGraph. The retry loop is Inngest. I am not writing protocols for either — it is
> unnecessary time.

Propagated everywhere. `architecture-context.md` §4 is now the named tie-breaker for any stale reference that
resurfaces, and `README.md` carries the rule so it is seen before any document is opened.

### Two conventions added — ADR-003

**Everything is `async def`.** No sync path through `app/`. Routes, CLI commands, controllers, services, nodes,
domain functions, agents, tools, `lib/` clients, repositories, voice handlers. `asyncio.run()` is called once
per adapter, in `cli/main.py`.

**Maths never lives in the file that uses it.** A subsystem that computes a number carries a sibling `math/`
package. The service chooses *which* method; `math/` contains *the* method.

**The one interaction between them, and the reason both are stated as absolutes.** A CPU-bound numerical
kernel marked `async def` would block the event loop for its full duration behind a signature claiming it does
not — worse than an inconsistency. So `math/` modules are **sync**, they are the **only** sync functions in
`app/`, and every call into them is offloaded with `asyncio.to_thread` at the call site. That makes the
sync surface a *place* rather than a scattering of exceptions, which is what makes invariant 7 reviewable.

Where each rule is now written:

| Rule | Stated in | Checkable as |
|---|---|---|
| Async everywhere, `math/` excepted | `code-standards.md` §7, `product-truth.md` §4.1, ADR-003 | `architecture-context.md` §11, invariant 7 |
| Maths in its own module | `code-standards.md` §8, `product-truth.md` §4.2, ADR-003 | `architecture-context.md` §12, invariant 8 |

### `folder-archtecture.md` was rewritten

It was a bare tree with no header, no rules and no annotations, and it still carried a Celery-shaped
`workers/` folder including **`handlers/retry.py`** — a hand-written retry loop, which invariant 5 now
forbids. Rewritten with the required `what/where/how` header, per-line annotations, the four placement rules,
a "Placement questions, answered" table, and an explicit **"Folders that were deliberately removed"** table so
the deletions are not silently re-added by the next agent.

Removed and why:

| Removed | Because |
|---|---|
| `pipeline/pipeline.py`, `context.py`, `executor.py` | A hand-rolled executor and context object. LangGraph's compiled graph and typed state replace all three |
| `pipeline/runner.py` | Was `StepRunner`. Retry is Inngest's, resume is the checkpointer's |
| `lib/events.py` | Was `EventSink`. The event *models* survive, moved to `schemas/events/`; the transport is the LangGraph stream |
| `workers/` with `jobs/` + `handlers/{success,failure,retry}.py` | Celery-shaped, and `retry.py` is a hand-written retry loop. Replaced by `app/inngest/functions/` |
| `spectral/ndvi.py`, `ndwi.py`, `nbr.py` | Those are formulae, not modules. Now functions in `spectral/math/index_formulae.py`, with `indices.py` choosing between them |

Added: `cli/renderers/`, `schemas/events/`, `pipeline/{state,checkpointer,stream,cancellation}.py`,
`services/*/math/` on nine subsystems, `lib/llm/`, `app/inngest/functions/`, `app/db/` split into `models/` +
async `repositories/`, `services/reports/`, and `tests/unit/math/` mirroring the maths.

### Invariants renumbered

`architecture-context.md` grew two sections — §11 (async) and §12 (maths) — so **Invariants moved from §11 to
§13** and now number 18 rather than 15. `ai-workflow-rules.md` points at §13 and calls out the four
easiest-to-break invariants by name. The old `§11` cross-references in the session entry below are stale;
read §13.

### What did not change

The scientific boundaries (§8), the wire contract, the two shared vocabularies, the phase split, the voice
stack, the VRAM profiles, and every gate except 1.0's and 1.9's. `api-contract.md` needed one word changed.

### Next session

Still Phase 0.1, unchanged. Do not start Phase 1 work before `aeris doctor` is green. When 1.0 arrives, read
ADR-002 first — most of that sub-phase is now *configuring* LangGraph rather than building anything.

---

## Session — 2026-08-30 · The backend plan, and the two seams it rests on

> **Partly superseded.** The `EventSink` and `StepRunner` seams described below were cancelled by ADR-002 and
> the `LLMProvider` protocol with it. Everything else in this entry stands. See the entry above.

No implementation code was written this session. The output is the plan and the contract, deliberately:
the frontend had already specified most of this backend, and writing services before reading that
specification would have produced work that had to be undone.

### What the frontend already decided for us

The frontend is built, running on mocks, and it has published this backend's wire format. Three places:

- `lib/constants/rest.api.ts` — every endpoint.
- `features/*/schemas/*.schema.ts` — the exact payload shapes, as Zod, including the discriminated stream
  unions.
- `fcontext/memory.md` — **three sections titled "Message for the backend developer"** carrying hard
  requirements in prose: EPSG:3857 tiles, CORS, alpha channel, `bounds`/`minzoom`/`maxzoom`, masks in both
  raster and vector form, `confidence` nullable and never zero, `cloudCoverPercentage` null for SAR, and
  `POST /investigations` returning fast because the camera is already flying.

Two vocabularies are shared and **must not be invented on this side**: the S1–S20 stage codes and the twelve
model ids. The wire carries the code, the frontend carries the copy. The frontend has already had, and
fixed, the bug where a claim said `changeformer` while the fleet said `mdl_changeformer` — do not
reintroduce it from here.

All of this is transcribed into `api-contract.md`.

### The product owner's instructions, which are not in the PDF

Recorded in full in `product-truth.md`. The two that change the architecture:

**The system is voice-driven and agentic end to end.** Not a microphone in a sidebar — JARVIS. The operator
speaks, the system speaks back, and the visuals move as it talks. This means the agent has *two* tool
surfaces, not one: analysis tools in the backend, and the frontend's existing command bus as interface
tools. The frontend's `CommandDefinition` already carries a description written "for the agent" and a Zod
`paramsSchema`, so the registry is a tool registry that nobody had connected an agent to yet.

**Phase 1 is the entire application as a CLI.** Services, agents, workers, models, voice — all of it, no
HTTP. Phase 2 adds routes, controllers and sockets and deletes nothing.

### Two contract additions, approved this session

- **`ui-command`** — the agent proposes a frontend command; the frontend validates the params against its
  own registry schema before dispatching. The model's arguments are never trusted; the registry is the
  allowlist and it belongs to the frontend. This is the line between an agentic system and a chatbot with a
  map beside it.
- **`speech`** — a short utterance generated **from the validated claim objects, not from the answer
  tokens**, carrying `claimIds` that must never be empty. Reading the written answer aloud would produce a
  screen reader; the written answer cites figures and is meant to be re-read, while speech must be short
  and must never voice a number no specialist produced.

Both are in `api-contract.md` §4–5. **Neither is implemented on the frontend yet** — that is a coordinated
change when Phase 2.7 lands.

### The two seams, and why they are not over-engineering

> **CANCELLED by ADR-002 later the same day.** Read this for the reasoning that *led* to the seams, not as
> instructions. LangGraph provides both: the checkpointer replaces `StepRunner` (and delivers resume in Phase
> 1.0 rather than 2.5), and `stream_mode="custom"` replaces `EventSink` while keeping the event models, which
> were the genuinely valuable part. Do not build either.

Phase 1 as a CLI only avoids becoming a rewrite if these exist from the first commit. Both are justified by
a named Phase 2 requirement, and no third protocol is justified.

**`EventSink`** — the pipeline emits typed events that *are* the frontend's stream events, and never
touches a socket. Phase 1 renders them to the terminal and journals them as JSONL; Phase 2 injects an SSE
broadcaster. The payoff is immediate rather than deferred: **the Phase 1 journal can be replayed through
the frontend's own Zod parsers, so Phase 2 wire compatibility is provable months before a route exists.**

**`StepRunner`** — steps are pure functions behind a protocol. `LocalStepRunner` in Phase 1 (memoise,
retry, replay from the failed step), `InngestStepRunner` in Phase 2.

The `StepRunner` seam exists because of a genuine conflict with ADR-001 that is worth stating plainly:
**Inngest orchestrates by making HTTP calls into the application**, so Phase 1 cannot literally use Inngest
without ceasing to be a CLI. The protocol keeps ADR-001 as the target, keeps Phase 1 honestly CLI-only,
delivers replay before the project depends on Inngest's dev server, and reduces the cost of ADR-001 being
wrong to a one-file swap. **ADR-001 is not overturned** — its binding is deferred to Phase 2.5.

### Decisions recorded so they are not relitigated

| Decision | Reason |
|---|---|
| Voice: `faster-whisper` + Piper/Kokoro, backend, offline | No per-minute cost, no vendor in the agent loop, and it survives a demo venue with bad networking |
| ~~LLM: OpenAI behind an `LLMProvider` protocol~~ → **OpenAI through LangChain `init_chat_model`** (ADR-002) | Product owner requires swapping to be a `config.py` change. `init_chat_model` takes the provider as a string, so the 1.9 gate is a `.env` change rather than a hand-written second adapter |
| Supabase for relational + auth, MinIO for rasters | TiTiler reads COGs over S3; multi-GB GeoTIFFs do not belong in Supabase Storage |
| `ModelManager` is VRAM-profiled (`vram-8` / `vram-16` / `vram-24`) | Dev GPU is 8 GB today, 24 GB expected. Same code on both — the small card gets LRU eviction, the big card simply stops evicting |
| TiTiler is a **Phase 1.2 gate**, not a Phase 2 task | CORS is named by the frontend as the most common first-day failure. Far cheaper to discover in September than in December |
| Areas computed in an equal-area CRS | Hectares are quoted in reports. Computing them from degrees is the classic confidently-wrong number |
| The co-registration residual **gates** change detection | Above tolerance the pipeline refuses rather than lowering a confidence. A residual larger than the feature under discussion invalidates the comparison, it does not degrade it |
| Late fusion, never early | Keeping each sensor's evidence separable is what makes the joint answer auditable (PDF p.19) |

### `architecture-context.md` was another project's document. Rewritten this session.

It opened with the heading "ScholarSync Frontend Architecture Context" and then described **ATLUS, the
backend for LUNARSAFE** — lunar terrain processing, DEM super-resolution, landing-zone ranking, Monte Carlo
trajectory propagation. A developer reading it cold would have built the wrong system. Flagged to the
product owner, who approved the rewrite.

Kept: the layering (`Route → Controller → Service → Helper → Model → DB`), the pipeline/worker split for
long-running scientific work, and the reusable half of the tech-stack table.

**Corrected while rewriting** — the old stack table listed **Celery** as the background-job layer, which
directly contradicts ADR-001. Now: Inngest as the Phase 2 target for retry and replay, with Phase 1
durability supplied by the LangGraph checkpointer, and a line saying explicitly that Celery is not used.
*(This sentence originally described `StepRunner` / `LocalStepRunner`; corrected here by ADR-002.)*

Two things were added that did not exist before and are now load-bearing:

- **§8 Scientific-computing boundaries** — twelve rules, each with the specific wrong answer that follows
  from breaking it: mask before index arithmetic, residual gates the comparison, equal-area CRS for
  hectares, nodata is not zero, reflectance not DN, resampling method follows data type, fixed SAR order
  with layover/shadow retained, late fusion only, no model-generated figures, nullable confidence,
  insufficient evidence as a success, artefact retention.
- **§11 Invariants** — fifteen numbered, checkable statements. `ai-workflow-rules.md` already closed a unit
  of work by asserting "no invariant defined in `architecture-context.md` was violated", but **the document
  had no invariants section**, so that check had nothing to check against. It does now. *(Now §13, and
  eighteen statements — see the entry above.)*

### Also noted

- `app/main.py` and `app/config.py` exist and are **empty**. The backend is genuinely greenfield.
- `requirements.txt` is a flat pip freeze including the whole Jupyter tree. Phase 0.1 replaces it with
  `pyproject.toml` + `uv.lock` and splits the notebook dependencies into a `dev` group.
- Useful things already present: `notebooks/01_remote_sensing/` with five started notebooks, and real
  Sentinel-1 VV/VH and Sentinel-2 B02/B03/B04/B08 GeoTIFFs in its `data/`. Phase 1.2 has test data on disk
  already.
- `bcontext/ai-workflow-rules.md` still carries the frontend's "protected foundation components" section
  about `components/ui/*` and shadcn. Harmless, but it is frontend text in a backend document.

### Next session

Phase 0.1. Do not start Phase 1 work before `aeris doctor` is green — the whole point of the Phase 0 pattern
is that nothing is built on an unverified dependency.
