# How every backend file is written. Non-negotiable, and checked at review.

**what** : The file header convention, naming rules, the async rule, the maths-placement rule, and the
configuration and constants discipline that every Python file in `backend/` must follow.
**where**: Applies to every file written by a human or an agent. A file that does not follow the header
convention is incomplete, not merely undocumented.
**how**  : Rules are stated with the reason they exist, because a rule whose purpose is forgotten gets
applied wrongly at the first edge case.

---

## 1. The file header

**Every file opens with a header. The first line says why the file exists — not where it lives.**

The reason is scanning cost. An agent — or a developer — deciding whether a file is relevant should be able
to read one line and move on, instead of loading the whole file into context to find out it was the wrong
one. The path is already known from the import; the *purpose* is what cannot be recovered without reading.

```python
# Turns a raw satellite acquisition into a validated, catalogued scene the rest of the system can trust.
#
# what  : Reads an uploaded raster, extracts sensor/CRS/band metadata, runs the quality checks that decide
#         whether the scene is usable, converts it to a Cloud-Optimised GeoTIFF and records it.
# where : The entry point of the S1-S6 stages. Called by the ingest CLI command and, in Phase 2, by the
#         imagery controller. Nothing downstream may read a raster that has not passed through here.
# how   : Rasterio opens the file once and every probe reads from that handle. Quality failures raise
#         IngestRejected rather than returning a flag, because a scene that fails S6 must never reach a
#         model - a silently degraded input produces a confidently wrong answer.
```

- **Line 1** — one sentence, what this file is for. Written so it is useful in isolation.
- **what** — what it actually does, and the parameters or inputs that matter.
- **where** — its place in the system. What calls it, what it unblocks, which boundary it sits on.
- **how** — the mechanism, and any decision a reader would otherwise question. This is where a non-obvious
  choice is defended.

Scale the header to the file. A 40-line constants module gets three short lines; a pipeline node gets the
full treatment. **Do not pad a trivial file to fill the template.**

## 2. Comments

Use comments where they carry information the code cannot: a unit, a known failure mode, a citation, a
reason for an unusual choice.

**Do not narrate.** `# loop over the bands` above a loop over the bands is noise, and noise trains the next
reader to skip comments, including the one that mattered.

Cite the PDF where a design comes from it: `# Late fusion, not early - PDF section 9, p.19.`

## 3. Naming

- **No shortforms.** `acquisition` not `acq`, `coordinate_reference_system` not `crs_str`, `investigation`
  not `inv`. The exceptions are established domain terms that are *never* written in full in the field —
  `ndvi`, `sar`, `vlm`, `crs`, `cog`, `aoi`, `dem`.
- Functions are verbs, values are nouns, booleans read as assertions (`is_available`, `has_cloud_mask`).
- Names match the wire. If the frontend calls it `groundSampleDistanceMeters`, the Python field is
  `ground_sample_distance_meters` and the serialiser handles the case change. **Never rename a concept
  across a boundary** — the cost is paid every time someone tries to trace a value end to end.

## 4. Configuration lives in config.py. Always.

Anything that changes between environments, or that is a one-time hardcoded decision, is read from `.env`
through `config.py` and from nowhere else. URLs, credentials, bucket names, model paths, VRAM profile,
tile sizes, thresholds, timeouts, feature flags, the LLM provider.

`config.py` is a `pydantic-settings` model. It validates at import, so a missing or malformed variable
fails loudly at startup instead of surfacing as a mystery failure inside a worker an hour later. The
frontend does exactly this in `lib/env.ts`; the backend matches it.

**`os.environ` is not read anywhere except `config.py`.**

## 5. Hardcoded lists live in constants/. Always.

Any fixed set — task types, modality names, status values, error codes, limits, stage codes, model ids —
gets a module in `app/constants/`. Never inline, never duplicated.

Two of these sets are **shared vocabulary with the frontend and cannot be invented here**:

- **Pipeline stage codes S1-S20** — `frontend/lib/constants/pipeline-stages.ts`
- **Model ids** (12 of them) — `frontend/lib/constants/models.ts`

The wire carries the code; the display copy lives in the frontend. The backend sends `S13` and
`changeformer`, never "Specialist analysis" or "ChangeFormer". Sending a code the frontend does not know
fails at its schema boundary, which is the intended behaviour — it is louder than rendering a blank row.

## 6. Module size and shape

- One purpose per module. When a file grows past roughly 300 lines, it is usually doing two things.
- Pure domain functions take and return plain data. No I/O, no globals, no logging of business meaning.
  They are the parts worth being certain about, so they must be testable without a database.
- Side effects live at the edges: `lib/` for infrastructure clients, `inngest/` for durable execution,
  pipeline nodes for stage orchestration.
- **Dependency direction is one-way**: `routes/cli → controllers → services → domain → lib → constants`, and
  `domain → math/ → constants`. A service never imports a controller. Domain code never imports `lib`.

## 7. Every function is `async def`. `math/` is the only exception.

Routes, CLI commands, controllers, services, pipeline nodes, domain functions, agents, tools, `lib/` clients,
model loaders, repositories, voice handlers — **all coroutines.** There is no sync path through `app/`.

```python
async def ingest_scene(source_path: Path) -> Scene: ...          # correct
def ingest_scene(source_path: Path) -> Scene: ...                # wrong, wherever it lives outside math/
```

The reason is not fashion. One sync function in the middle of an async call chain forces every caller above
it to choose between blocking the event loop and wrapping the call, and that choice gets made differently in
different files. You then have a codebase where a signature no longer tells you whether calling something is
safe. Uniformity removes the question. It is also the shape of everything we build on: LangGraph nodes are
awaited by `graph.astream()`, FastAPI endpoints are coroutines, SQLAlchemy runs on `asyncpg`, and barge-in is
`asyncio` task cancellation.

**`asyncio.run()` is called in exactly one place per adapter** — `cli/main.py` in Phase 1, and never in
Phase 2, where the framework owns the loop. A service that calls `asyncio.run()` is a bug.

**The exception, and why it is an exception rather than an inconsistency.** A numerical kernel is CPU-bound.
Marking it `async def` would be a lie: it never awaits, so it blocks the loop for its full duration while
advertising that it does not. Honest is better. Therefore:

- **Functions inside a `math/` module or `math.py` are sync `def`.** They are the only sync functions in `app/`.
- **Every call into `math/` is offloaded at the call site**, so the cost is visible where it is paid:

```python
# services/spectral/indices.py
from app.services.spectral.math import index_formulae

async def compute_normalised_difference_vegetation_index(scene: Scene) -> IndexResult:
    near_infrared, red = await self._read_bands(scene, ("B08", "B04"))
    # CPU-bound array arithmetic - offloaded so the event loop keeps serving the voice stream.
    values = await asyncio.to_thread(index_formulae.ndvi, near_infrared, red)
    ...
```

- Third-party **sync** libraries — Rasterio, GDAL, Shapely, pyproj, PyTorch's blocking calls — are treated the
  same way: reached from inside a `math/` module, or wrapped in `to_thread` at the boundary. Use a process
  pool instead when the work is heavy enough to fight the GIL, and say so in a comment.

**The second exception, deliberately narrow.** Two more kinds of function are sync, and both are sync because
making them coroutines would be actively worse rather than merely unnecessary:

- **A method that maps fields already in memory onto another shape**, on an object that is not always reached
  from a coroutine. `to_error_payload()` in `lib/exceptions.py` is the case in hand: it is called from exception
  handlers, from log formatting, and from `__str__`-adjacent code, and an `await` there would mean an error
  could not be rendered from a sync context — which is exactly the context errors show up in.
- **A callback the framework calls, never us.** A `logging.Formatter` subclass, a Pydantic validator, a
  `__init_subclass__`. The standard library calls these synchronously; declaring one `async def` produces a
  coroutine object where a value was expected.

Both are recognisable by the same test: **no I/O now, and no plausible I/O later.** Anything that could
eventually read a file, a socket or a database is a coroutine today, even if today it only returns a constant.
`configure_logging()` in `lib/logger.py` is the illustration on the other side — it awaits nothing, and it is
still `async def`, because a handler that ships logs over a socket is a plausible next version of it.

**Tests follow.** `pytest-asyncio`, `async def test_...` for everything above `math/`; plain `def test_...`
for the `math/` modules, which is part of why they are worth isolating. `asyncio_mode = "auto"` is set in
`pyproject.toml` so that no test carries a marker whose absence would silently skip it.

## 8. Maths goes in `math/`, never in the file that uses it

**A service, node, controller or domain file that needs a numerical method does not contain that method.** It
goes in a sibling `math.py`, or a `math/` package once there is more than one file of it, inside that
subsystem's own folder.

```
services/spectral/
├── indices.py            # async. WHICH index, band mapping per sensor, mask application, result object.
└── math/
    ├── index_formulae.py # sync, pure. ndvi(near_infrared, red) -> ndarray.
    └── thresholds.py     # sync, pure. Otsu, fixed cut-offs, histogram statistics.
```

**The dividing line:** `math/` knows arrays, numbers, geometries and CRS codes. It does **not** know what a
scene, a claim, a run, an investigation or a model id is, and it does no I/O. If a `math/` function needs a
`Scene`, the split was made in the wrong place — move the lookup up into the service and pass arrays down.

Why this is a rule and not a preference:

- **The maths is the part that has to be provably right.** §11 requires deterministic numerics to be tested
  against values computed by hand or by QGIS. A formula tangled up with band lookup, masking, config reads
  and a database write cannot be tested that way without standing the system up. Isolated, the test is three
  lines.
- **It is where the scientific boundaries are kept or broken** (`architecture-context.md` §8): equal-area
  reprojection before area, nodata propagating as a mask, reflectance rather than digital numbers, resampling
  method following data type. In one named place per subsystem those can be read and reviewed; scattered
  through service logic they can only be hoped for.
- **It is the sync/async boundary** (§7). One sync surface, in one predictable location.
- **"Which formula" changes often; "the formula" never does.** `(nir - red) / (nir + red)` is physics.
  Choosing NDVI over NDWI for a query is application logic. Mixing them means every routing change edits code
  that should never be touched again.

Cite the source where the method has one: `# Otsu 1979. Fails on bimodal-with-unequal-variance histograms.`

## 9. Errors

- Raise typed exceptions from `app/lib/exceptions.py`. Never return `None` to signal a failure that the
  caller must handle.
- Every error carries a stable `code` from `app/constants/errors.py`. The frontend's `ApiErrorPayload`
  expects `{message, code, status, details}`.
- **Refusal is a valid outcome, not an error.** When evidence is insufficient the pipeline returns an
  `InsufficientEvidence` result with remedies. That is a product feature (PDF p.38) and must not be
  collapsed into an exception.

## 10. Typing

- Full annotations on every function signature. `Any` is a defect unless it is genuinely opaque, and then
  it is commented.
- Pydantic models for anything crossing a boundary. Dataclasses for internal value objects.
- `TypedDict` for LangGraph state schemas — that is what the library reads to type a graph.
- **Do not introduce a `Protocol` to abstract something a library already abstracts.** ADR-002 deleted
  `StepRunner`, `EventSink` and `LLMProvider` for exactly that reason. A `Protocol` is justified when there
  are two real implementations today — `StorageClient` over MinIO and a local filesystem is the surviving
  example — and by nothing weaker than that.

## 11. Tests

- Deterministic domain code — indices, geometry, area, statistics, routing — is tested against **values
  computed by hand or by an independent tool**, not against whatever the code currently returns. A test
  that only pins current behaviour proves nothing about correctness. Because that code lives in `math/` (§8),
  these tests are plain sync functions over arrays.
- Everything above `math/` is tested with `pytest-asyncio` and `async def test_...`.
- Model inference is tested for shape, range and invariants, not for exact outputs.
- Every wire payload is validated against the vendored JSON Schema in `bcontext/contracts/`.
- Fixtures live in `tests/fixtures/` and are small. A test that needs a 400 MB scene is an integration
  test and is marked as one.

## 12. Third-party code

Do not modify vendored or generated code. Wrap it.

## 13. Keep the documents in sync

Changing a boundary, a storage decision, a convention or a feature's scope means editing the bcontext
document that owns it in the same change. `memory.md` gets an entry at the end of every session.
