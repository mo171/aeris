## Session — 2026-09-01 (1.3) · Preprocessing. **Four defects, none visible to a passing suite.**

Phase 1.3 arrived already written — services, math kernels and a first pass of tests, all green. The job
was the testing, and the testing found that green meant very little: **four defects in the maths, every one
of them producing a plausible raster rather than an error, and every one of them sitting under a test that
passed.** 41 tests now (25 unit, 16 integration), **337 green** with 60 deselected, ruff and lock clean.

### What was wrong

1. **Layover and shadow were swapped.** The slope was measured *away* from the sensor and then tested as
   though it were measured *towards* it. The test in place asserted that both masks were non-empty and
   differed from each other — which stays true when the sign flips. This is the §8 rule 7 distinction,
   inverted, and it is invisible in a figure because both cases put a plausible mask on plausible ground.
2. **The terrain correction was a gain.** `cos(slope)/cos(incidence)` multiplies *flat* ground by 1.22 at a
   35° incidence. A correction that is not the identity where there is nothing to correct biases every
   value in the scene by a constant nobody declared. Now `cos(θ)/cos(θ_local)`, exactly 1 on the flat.
3. **Speckle was filtered as additive noise** while the docstring said multiplicative. Measured: two
   regions of one scene, identical speckle statistics, differing only in brightness — 25× smoothing on the
   dark half against 1.4× on the bright. Water and shadow get flattened, vegetation keeps its speckle, and
   a change detector reads that variance collapse as a finding. Now Lee (1980) on the coefficient of
   variation, which is scale-free.
4. **Registration filled nodata with zero.** A hard zero block is a strong feature; tiles touching the
   margin locked onto it and returned a shift of exactly **(0, 0)** — which reads as *perfect* registration
   rather than as a failure. 1.3% nodata was enough to report 1.02 px on a pair aligned to 0.00 px.

### The measurement discipline, twice over

I got #4 wrong twice on the way. First I called a 0.97 px residual a defect; then I decided my own test
construction was at fault and said so; then measuring both constructions against both fills showed the
code was at fault after all — mean-fill gives 0.0000 px on *both* constructions, zero-fill ~1.0 px on both.
**Only the last of those three positions came from a measurement**, which is the whole lesson.

Then the regression test I wrote for it *survived its own mutation*: the NaN band was 24 rows deep against
a 64-row tile, so the affected tiles fell below the 0.8 validity floor and were skipped — no tile in the
test ever contained a nodata edge. Narrowing it fixed the construction and still did not catch the bug,
because no synthetic texture reproduces the failure (white noise locks through the artefact, smoothed noise
never locks at all). Pinned instead on the property the fix delivers — the filled tile is continuous.

### Mutation: 16 applied, 14 caught, 1 equivalent, 1 pending

Three survived the first pass and **all three were real gaps**, not equivalent mutations: nothing covered
the Lee filter beside a nodata margin; the median-vs-mean choice is only observable in the reported
*translation*, not in the residual; and the nodata fill needed the direct pin above.

### The gate, on real data

`aeris preprocess coregister` / `sar` / `relief`. The bad pair's **4.0000 px** is hand-checkable — half the
tiles at +4 and half at −4 about a median of 0. The flat local scene reports **0.00% obscured, and that is
correct**: Mumbai has 91 m of relief and layover needs a slope steeper than the incidence angle. So the
distinction is demonstrated where it exists — **Khumbu, 4461 m of relief, windowed 1477×1663 out of a
27577×21415 scene rather than downloaded**: radar *could not see* 8.55%, radar *saw nothing* 0.02%, and
reversing the orbit swaps which slopes fold and which hide. That last one is what proves it is geometry
rather than a property of the ground.

### Decisions worth not relitigating

- **`calibration_factor=None` is a first-class input**, not a missing argument. Every RTC product is
  already linear power; calibrating it again returns the square of the truth and opens cleanly.
- **The SAR figure uses a fixed dB domain**, for the reason every NDVI is drawn over [-1, 1] (1.2.1). A
  radar time series exists to be compared, and per-date percentiles make a flooded field look like a calm one.
- **`scenes.Polarisation` is upper case and is deliberately not `BandRole`.** One addresses a band in a
  file, the other is a value on the wire. This discharges `polarisationSchema`, which had sat in
  `FRONTEND_ONLY_VOCABULARIES` reading "Phase 1.3 — the SAR branch" since 0.7.
- **`obscuredFraction` counts *unjudged* pixels as unread**, not as clear. The frontend's own wording is
  "could not read at all", and a pixel the detector could not judge has not been shown to anyone.
- **The DEM is read as a window, never as a tile.** Whole-tile reads over HTTP were slow enough that the
  first run of the gate never returned.

### Next — Phase 1.4

Spectral indices and geospatial statistics, S12 and S15 measurement. 1.3 hands it the thing rule 1 is
about: `apply_optical_mask` exists and must run *before* any index formula, not after.

---

## Session — 2026-08-31 (1.2.1) · The rendering primitive. **A figure redraws byte-identically from its spec.**

`services/rendering/` built, `figure-ready` on the wire, and the gate passed: three figures from the
four-band Sentinel-2 subset, each with a machine-readable legend, a non-null `traceStepId` and a complete
`renderSpec` — and the index map **redraws byte-identically from that spec**. 37 new tests, **353 green**,
ruff and `uv lock --check` clean.

    rgb-composite   1066×1120  2518 KB   legend categorical  ramp true-color
    index-map       1066×1176  1444 KB   legend continuous   ramp index-vegetation  domain [-1, 1]
    mask-overlay    1066×1120  2554 KB   legend binary       ramp mask-amber        resampling nearest
    vegetated: 17.1%   ·   byte-identical re-render: 1,478,754 bytes   ·   3 in MinIO and on disk

### The decision the whole sub-phase turns on

**Matplotlib is used for its colormaps and nothing else** — no figure, no `Agg` canvas, no `savefig`.
Composition is NumPy and Pillow.

The reason is `api-contract.md` §6 rule 2: re-rendering from a recorded spec must be byte-identical,
because a figure the VLM reasoned over is part of the evidence chain. A matplotlib figure's bytes depend on
font metrics, DPI, backend version and a `Software` tag; an RGBA array encoded by Pillow with pinned
parameters depends on none of those. The colourbar is drawn by hand for the same reason — Pillow's bundled
bitmap font, never a system font, because a system font is present on one machine and absent on another.

The colour data is still matplotlib's, and that is worth not reimplementing: hand-picking control points
for a diverging ramp is how a product ends up with a midpoint that reads as a value.

### Two additions to the contract, both because rule 2 demands completeness

**`renderSpec.stretch` carries its `method`.** A percentile stretch is data-dependent and a fixed one is
not; the numbers alone cannot answer *"would this redraw the same way on other data"*.

**`renderSpec.decimation` was added outright** — it is not in `api-contract.md`'s example, and the example
is not complete without it. A figure is a picture for a person, so a 10980² scene is drawn from a decimated
read, and two decimations produce visibly different images. `figure-ready` is agreed and not yet on the
frontend (§6), so extending it now is a change to a contract nobody parses rather than a breaking one.

### The contract suite gained a direction

Adding `FIGURE_READY` to `AnalysisEventType` broke `test_the_backend_event_names_are_the_frontend_union
_exactly` — correctly, because the frontend does not parse it yet.

**Not weakened to a subset check.** `EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND` records the three
agreed-but-unimplemented events (§4 `ui-command`, §5 `speech`, §6 `figure-ready`) by name with a reason, and
a second test fails when the frontend ships one — at which point the equality check starts enforcing it.
The mirror of `EVENT_TYPES_NOT_YET_EMITTED`, so event drift is now tracked in both directions exactly as
vocabulary drift has been since 0.7.

### Decisions worth not relitigating

- **A normalised index is always drawn over [-1, 1], never its own extremes.** Two NDVI maps of one field
  in different weeks are only comparable if they share a scale; stretching each to its own data makes every
  week look equally varied and hides the change being looked for. A ramp with no fixed domain is *refused*
  for an index map rather than falling back.
- **A true-colour composite stretches each band separately**, and records all three. Their dynamic ranges
  genuinely differ, and a shared stretch produces a colour cast that reads as a property of the ground.
- **A composite is transparent where *any* band is missing.** A pixel with two of three bands is a colour
  with one channel invented.
- **A mask overlay is semi-transparent.** An opaque mask answers "where" and destroys "over what" — and an
  operator judging a mask is judging exactly whether it agrees with the ground beneath it.
- **A blend takes its alpha from the base, never the overlay**, or a mask makes the scene's nodata margin
  opaque and claims ground the sensor never saw.
- **The figure writer *downloads* rather than being handed the bytes.** Slower, and it proves the object is
  retrievable under a key something else can reconstruct — which is precisely what breaks silently and
  surfaces in Phase 2 as an image that will not load.
- **`--level` on `aeris figures`.** A band extracted into a research directory has lost its processing
  level, and §8 rule 5 forbids *guessing* it. A human stating what the data is is not the same thing.

### Mutation: 12 applied, 11 caught, 1 recorded as uncatchable

Three survived the first pass. Two were real gaps: "encode the same array twice" passes for any
deterministic choice, so it proved *stability* without proving *which value*. Two tests were added — the
invisible pixel's colour is pinned to a specific value, and a lossless round-trip proves the encoder does
not rewrite pixels nobody can see (which is what `exact=True` buys).

**The survivor is PNG `compress_level`**, and it is recorded rather than papered over: those parameters
change bytes between Pillow *versions* and are stable within one, so no in-process test can observe the
drift they guard against. Same category as `_require_in_range` in 1.2 — proven by reasoning, and the
reasoning is written down.

### A correction I made mid-phase

I read the contact sheet and said the mask looked like it covered water. Measured instead: 17.1% of pixels
tinted, exactly matching the mask, **zero outside it**, mean NDVI 0.428 inside against 0.009 outside. Amber
over green vegetation reads brown at thumbnail scale. *Squinting at a thumbnail is not a measurement* —
which is the same lesson the 1.2 notebook taught from the other direction.

### Fixed here, found by using it

A 245 MB scene download had **no retry**, and a remote reset lost the whole transfer — measured, after
three consecutive resets while fetching B02/B03 for this gate. `_download_to` now retries three times with
backoff. Each attempt restarts rather than resuming with a `Range` header: resuming without checking the
`ETag` risks stitching a scene from two versions of a file, which is a worse failure than a slow retry.

The B02/B03 fetch never did succeed — hence the gate running against the four-band subset in
`notebooks/01_remote_sensing/data`, which is real Sentinel-2 at 1066×1120 in the same UTM zone.

### Next — Phase 1.3

Preprocessing, S7–S10 and the SAR branch. Two things carry forward: the SAR backscatter figure is a *figure
kind*, not new rendering code (`sar-grayscale` is already in the ramp vocabulary), and the frontend's
`polarisationSchema` is `{VV, VH, ratio}` in **upper case** while `BandRole` has lower-case SAR members —
1.3 needs its own `Polarisation` enum matching the frontend exactly.

---

## Session — 2026-08-31 (1.2) · The raster engine. **An NDVI COG renders in a real browser.**

S1–S6 and S11 built, TiTiler in compose, and the gate passed end to end: an NDVI COG produced by this
pipeline, stored in MinIO, rendered at `http://localhost:3000` with seven checks green — including
`getImageData` on a canvas the tile was drawn into, which is what Cesium does and what a plain `<img>`
does not exercise. 46 new tests, **314 green**, ruff and `uv lock --check` clean.

    NDVI over 10980×10980   range [-1.000, 1.000]   vegetated (>0.3) 72.6%
    TileJSON  xyz, bounds [77.032, 27.901, 78.176, 28.913], minzoom 8, maxzoom 14
    CORS      allowed → ACAO: http://localhost:3000   ·   other → 200 with NO ACAO
    Tile      image/png, RGBA, 38,217 transparent px of 65,536 at the scene edge

### The bug worth carrying into every later phase

The first NDVI this pipeline produced ranged **[-337, +347]** against a mathematical range of [-1, +1]. It
wrote a **valid COG**. It rendered as a plausible map. 0.055% of pixels — invisible by eye, and more than
enough to set the colour scale of every figure drawn from the array, because a ramp is stretched to the
extremes it is given.

**My first fix was wrong.** I raised the denominator guard, on the reasoning that `(a−b)/(a+b)` blows up
near zero. It changed nothing. The actual cause: `|a−b| ≤ |a+b|` holds **only when a and b share a sign**,
and subtracting the L2A offset from dark ground — deep water, terrain shadow — gives a small *negative*
reflectance, which is an atmospheric-correction artefact rather than a measurement.

Measured: **0.52% of valid pixels have negative reflectance in one band, and 100% of the out-of-range
values came from exactly those pixels.** Masked, not clamped (§8 rule 4). `math/indices.py` carries a
post-condition that raises on any finite value outside [-1, 1].

Reproduced independently in `notebooks/03_raster_engine/01_cog_and_tiles.ipynb` — which itself found a
second lesson: a 1024×1024 window at the centre of the tile contains **none** of the artefact and reports
the bug as 0.0000%. The notebook now reads decimated over the whole scene. *A window that misses the
defect makes a real bug look fixed.*

### Four things measured after assuming otherwise

- **TiTiler listens on 80**, not 8000. Read from its own startup log after a health check that never went
  green.
- **Its settings are prefixed `TITILER_API_`.** Bare `CORS_ORIGINS` had no effect at all; read off the
  running container's `ApiSettings`.
- **Its default CORS is `*` *with* `allow-credentials: true`** — a pair every browser rejects outright, so
  the permissive-looking default is in fact the broken one. Now named to the frontend origin, same
  reasoning as `MINIO_API_CORS_ALLOW_ORIGIN` in 0.4.
- **`distinct / valid` is scale-dependent.** At 1e-6 the constant-raster check fired on a 10980² scene and
  silently passed a 20×20 one — the check existed and only worked on large rasters. Found by a failing
  test. Constancy is scale-free and is now *counted*.

One correction I made mid-phase: I called the COG predictor a second bug, then found `IMAGE_STRUCTURE`
reports `PREDICTOR: 3` correctly — rasterio's `.profile` simply does not surface it. The 508 MB NDVI is
just what float32 costs; not a defect.

### The mutation pass, and the one left uncaught on purpose

12 mutations, 8 caught immediately. Four survived the first pass, and each told me something:

| Survivor | Why | Resolution |
|---|---|---|
| nodata detected as `array != 0` | every test used `nodata=0`, so the two were indistinguishable | new test with a declared −9999 and real zeros |
| prediction-shape check dropped | nothing fed a wrong shape; NumPy broadcasts (1,64) into (64,64) happily and paints a stripe | new test |
| nodata masked *after* scaling | **the mutation was wrong**, not the test — it still masked before | mutation corrected → caught by 3 tests |
| `_require_in_range` call removed | **genuinely uncatchable, and recorded as such** | see below |

The last one is worth keeping. Once the masks are correct, no input can produce an out-of-range value, so
the post-condition is unreachable and deleting its call changes no behaviour. It is defence in depth
against a *future* regression in the masking — which a separate mutation shows is caught. The guard itself
is tested directly. Writing a test that forced the call site to fire would mean breaking the masks to do
it. **Recorded as uncaught rather than papered over.**

### Decisions worth not relitigating

- **A COG is not an optimisation, it is what makes the globe possible.** An ordinary GeoTIFF stores pixels
  in scanline order, so one 512² patch means reading most of the file. Both open identically in QGIS,
  which is why `is_cloud_optimised` *validates* rather than trusting an extension.
- **`web_optimized=False`.** The COG stays in its native CRS and TiTiler reprojects per request. Baking
  EPSG:3857 in is faster to serve and destroys the pixel grid every measurement depends on — an area from
  a reprojected raster is an area from resampled pixels (§8 rule 3).
- **The predictor follows dtype.** 2 for integers, 3 for float. Applying 2 to float32 writes without error
  and decompresses to noise.
- **Tiles overlap, and stitching is weighted.** A model's predictions near a window edge are made from
  cropped context; without overlap those errors land in a grid and read as seams. Averaging overlaps
  equally keeps half of that error, so the blend ramps to near-zero at the edge — never *to* zero, or
  normalisation divides by nothing.
- **The last window is shifted, not padded.** Padding feeds a model fabricated black pixels and asks it
  about them.
- **Measurement and policy are separate.** `math/` returns numbers and never decides; `validation.py`
  compares against `constants/raster.py` and decides. That is what let the index bug be fixed with a unit
  test instead of a two-minute scene conversion.
- **Severity, not a boolean.** 60% cloud and a missing CRS are not the same thing: one is a judgement call
  for a demo, the other means nothing downstream can proceed.
- **Quality reads are decimated, regularly.** 2.78% of a scene answers "is this mostly nodata" to within a
  fraction of a percent — and *regular* rather than random, so the same scene measures the same twice.

### What Phase 0 caught again

Three new `StrEnum`s failed `test_every_backend_enum_is_classified`; two new settings failed the
`.env.example` test. Checked against the frontend before declaring them backend-only — and that surfaced a
note for 1.3: the frontend's `polarisationSchema` is `{VV, VH, ratio}` in **upper case**, while `BandRole`
has lower-case SAR members alongside the optical ones. 1.3 needs its own `Polarisation` enum matching the
frontend exactly; `BandRole` is not it and must not reach the wire.

### Next — Phase 1.2.1

The rendering primitive: `services/rendering/`, colour ramps, stretches, the `figure-ready` event and
`cli/renderers/figure_writer.py`. Everything it needs is now in place — the scene, the index array, and the
statistics that decide a stretch (`p2`/`p98` rather than min/max, which this phase measured as 1108/3276
against a min/max of 252/15747).

---

## Session — 2026-08-31 (1.1) · Datasets, licences, and one loader. **A real scene is on disk.**

18 datasets catalogued from the PDF's Table 5, one loader over six declared layout shapes,
`aeris dataset list|show|fetch|search`, and a **real Sentinel-2 L2A scene fetched from Planetary Computer**
over Ghaziabad. 126 new tests, **268 green**, ruff and `uv lock --check` clean.

### The decision the whole phase rests on

The roadmap's gate is about *sequence*: "licences are recorded before any training begins, not after". A rule
about sequence needs something that refuses at the right moment, so:

**`Licence.UNVERIFIED` denies everything** — `training_permitted=False`, redistribution and commercial use
forbidden. An unknown licence is **not** a permissive one, and the two must never look alike in a table.
Recording a guess as though it were a fact is worse than recording nothing, because the guess is what
somebody relies on six months later when deciding whether a demo can be published.

Two of the eighteen are verified — Copernicus Sentinel-1 and Sentinel-2, which are genuinely open and
unambiguous. **The other sixteen are not**, and that is the honest state of a catalogue assembled from
published papers rather than from reading sixteen licence pages. Each carries the URL where its terms live,
`aeris dataset list` prints `UNVERIFIED` in red rather than leaving the cell blank, and `require_trainable()`
raises. Phase 1.6 cannot start a training run past it.

Mutation-checked, and this is the one that matters: giving `UNVERIFIED` `training_permitted=True` fails
`test_an_unverified_licence_permits_nothing` — without which every other test keeps passing while the gate
silently stops existing. Marking LEVIR-CD `licence_verified=True` without changing its licence fails **three**
tests; that is the human version of the same failure and deserves the redundancy.

### Three things measured, each of which changed something

**A Sentinel-2 10 m band is ~245 MB as a COG**, not the ~100 MB published figures suggest. The record said
"~200 MB per scene subset"; two bands came to 489 MB in 7m18s. The record now says so, and `--asset` exists
because of it — B04 and B08 alone are enough for NDVI.

**Forgetting the L2A reflectance offset moves the vegetated fraction from 75.1% to 61.4%** on a real scene —
13.7 percentage points, mean |ΔNDVI| 0.185. Both maps look like NDVI maps. That is the whole danger: there is
no error, only a different answer, and the difference is largest exactly where vegetation is sparse and the
decision is marginal. Measured in `notebooks/02_data_exploration/01_sentinel2_l2a.ipynb` and recorded back
into the dataset record's `quirks`.

**`Availability.PARTIAL` was added because a test showed the model was wrong.** "Train downloaded, test not"
was being reported as `MALFORMED`, which sends an operator to check how an archive unpacked when what they
need to do is finish downloading. The four states exist to prescribe different actions, so conflating two
removes the reason to have either. `require_trainable()` became **per-split** for the same reason: an absent
test split must never be quietly satisfied by a present train split, or an evaluation runs on training data
and produces a number that looks excellent and means nothing.

### Logging: the deny-list was the wrong shape, and three phases proved it

`THIRD_PARTY_LOG_LEVELS` was a deny-list — name a noisy library, pin its level. It **failed open**, and had
to be extended in 0.6 (botocore, 142 KB over a twenty-line table), 1.0 (aiosqlite, 76 KB for a four-row
trace) and 1.1 again (pystac-client printing every request header). Three phases, three floods, each found by
a human reading unreadable output.

Inverted: the **root logger sits at `WARNING`** and only `app` is raised to `LOG_LEVEL`. A new dependency is
quiet on the day it arrives, and the list is now a short allow-list of libraries worth hearing more from.
The pystac flood went from unreadable to 1.2 KB.

### Decisions worth not relitigating

- **The loader enumerates; it does not parse labels.** A LEVIR-CD mask, a DOTA oriented box and an RSVQA
  question have nothing in common, and a loader returning all three returns `Any` — which is a loader that
  has stopped promising anything. 1.1 owes acquisition, licensing, cataloguing and enumeration; parsing
  belongs to the phase with a model to feed (1.6, 1.7). Enumeration is not a placeholder: it is what proves
  a download is complete.
- **Six layout shapes cover the whole of Table 5.** That is the useful finding — these datasets differ
  enormously in content and barely at all in structure, which is what makes one loader honest rather than
  aspirational. It reads a `DatasetLayout` declaration; there is no branch per dataset.
- **A mismatched pair raises, never skips.** 637 images in `A`, 636 in `B`, and a run that trains on 636
  pairs and reports a number nobody can reproduce — with nothing anywhere saying a file was missing.
- **Three acquisition routes, and `manual` prints instructions rather than pretending.** Roughly half of
  Table 5 is behind a registration form or a hosted drive. A `fetch` that silently did nothing for those
  would be worse than one that refuses; the plan names the URL, the licence page and the target directory.
- **Filtering Sentinel-1 by cloud is refused.** SAR carries no cloud property, so the filter matches nothing
  and returns an empty list — which reads as "no radar over this area", a conclusion an operator would act
  on rather than a bug they would report. Same rule as `api-contract.md` §1 rule 3.
- **Planetary Computer assets must be signed.** An unsigned href 404s, which reads as "no such scene" rather
  than "not signed". Pinned by a test so it can never fail silently.
- **STAC tests run against the live catalogue, not a fixture.** What can break here is the *catalogue's*
  behaviour — a renamed collection, a property that stopped existing — and a recorded response would keep
  passing through every one of those. They skip without network.

### What Phase 0 caught again, unprompted

Six new `StrEnum`s failed `test_every_backend_enum_is_classified`; five new settings failed
`test_env_example_documents_every_configurable_field`. Both were verified against the frontend contracts
before being declared backend-only — no dataset or licence vocabulary shares a value with any frontend
schema, which was checked rather than assumed.

### Next — Phase 1.2

The raster engine: S1–S6 and S11, plus tiles. The Sentinel-2 scene is on disk and loads through the same
loader everything else will, so 1.2 starts with real pixels rather than a fixture. The NDVI notebook already
demonstrates the two things 1.2 has to get right — the reflectance offset, and reading windows rather than
whole 10980×10980 bands.

---

## Session — 2026-08-31 (1.0) · The LangGraph spine. **Phase 1 has started.**

`aeris run` starts, resumes and replays a real pipeline run with a live S1–S20 trace. **142 tests green**
(45 new), ruff clean, `uv lock --check` clean. LangGraph 1.2.11 and `langgraph-checkpoint-sqlite` 3.1.1 are
the only new dependencies.

Built: `schemas/events/` · `services/pipeline/` (state, checkpointer, memory_store, stream, cancellation,
`node.py`, `graphs/probe.py`) · `services/sessions/` (session, run_handle, fanout) · `cli/renderers/` ·
`cli/run.py`.

### The structural decision, and why it had to be 1.0

`services/sessions/run_handle.py` runs the graph as a **detached task**. Starting a run returns a handle
immediately; a background task consumes `astream()` and fans the events out. The obvious alternative —
`async for event in graph.astream(...)` in the caller — is one line, and everything AERIS is supposed to be
dies at it: the agent cannot narrate because it is inside the loop, cannot answer a mid-run question because
there is nowhere for one to arrive, and cannot be spoken over without cancelling the analysis.

**Two tasks, not one**, and that is what makes abandonment safe. The outer task is never hard-cancelled, so
it is always alive to emit the terminal event. A single task would produce, on the hard-cancel path, a run
that just stops — no `run-error`, no journal entry saying why, and a trace whose last row spins forever.

The gate is `test_a_run_survives_being_interrupted`, written as the operator's actual behaviour — ask
something long, then ask something else while it works — rather than as an assertion about a flag. It fails
on the inline design because there would be no line on which to ask the second question. **Verified by
mutation**: adding `await handle.wait()` to `Session.start` fails it.

### Three things measured rather than assumed

**`durability="sync"`.** A graceful `asyncio` cancellation cannot tell the three modes apart — LangGraph
flushes pending writes on the way out, so `exit` looked identical to `sync`, and my first assumption about it
was wrong. Under a **hard kill** (`TerminateProcess`; no `finally`, no atexit):

```
exit   -> checkpoints=0   writes=0     the whole run is recomputed
async  -> checkpoints=3   writes=4
sync   -> checkpoints=3   writes=4
```

`exit` disqualified. `async` versus `sync` is a race window this test does not measure the width of; `sync`
closes it rather than narrowing it, and a stage here is inference in minutes against a sub-millisecond commit.

**A checkpoint holds data, never Python objects.** Putting `Intent` (a `StrEnum`) into the state made
LangGraph write `app.constants.intents.Intent` into the checkpoint — it warns that it will refuse this in a
future version. The real cost is worse than the warning: **rename that module and every in-flight run becomes
unresumable.** The state now carries `intent: str`, and the rule is recorded in `state.py` for every key
added after this one.

**`aiosqlite` at DEBUG produced 76 KB of output for a run whose own trace is four rows.** Same class of
problem as botocore in 0.6, and worse in shape: aiosqlite logs every statement *and* its completion, and the
checkpointer writes after every node — so the flood scales with the length of the pipeline rather than being
a one-off at startup. `THIRD_PARTY_LOG_LEVELS` gained aiosqlite, langgraph, langchain_core, langsmith.

### The mutation pass found a real gap, which is the point of doing it

Eight mutations, seven caught immediately. The one that survived: **deleting the node-boundary cancellation
check changed nothing.** All twenty tests stayed green.

The reason is that three mechanisms stop an abandoned run — the decorator's entry check, its exit check, and
the node's own loop — and every end-to-end test was satisfied by whichever fired first. Three guards, one
observable behaviour, **none individually tested**. That is precisely how a guard quietly stops working.

Splitting them produced three new tests and one genuine finding: the exit check matters for exactly one case,
**the last stage**, where there is no next node whose entry check would catch it. Without it, a run the
operator was told was cancelled emits `run-complete` — the handle and the permanent record disagreeing,
which is the worst kind of bug to find later. Each mechanism now has the only test that catches it:

| Mutation | Caught by |
|---|---|
| entry check deleted | `test_a_node_does_not_start_when_the_run_is_already_abandoned` |
| exit check deleted | `test_a_run_abandoned_during_its_final_stage_does_not_report_success` |
| node stops checking its own loop | `test_abandoning_a_long_stage_does_not_wait_for_it_to_finish` — 29.8 s vs 13.0 s, the run waited out the whole 10 s stage |

Also caught: the inline-await design, a fresh step id per emission, a dropped `running` emission,
`serialise_event` without `by_alias`, session-close abandoning its runs, a failing consumer killing the run,
and a declined confidence coerced to `0.0`. Every mutated file was restored and **byte-compared**.

One process note worth keeping: I first wrote two mutation results into a test comment **without having run
them**. They were run afterwards and both behaved as claimed — but a recorded result nobody executed is
exactly the thing these comments exist to replace.

### Decisions worth not relitigating

- **`pipeline_node` is a decorator, not `StepRunner`.** ADR-002 deleted a protocol that owned retries, an
  executor, an event sink and a context object. This is `functools.wraps` around one async function: it
  chooses nothing, dispatches nothing, retries nothing. What it buys is that "emit the step twice, keyed on
  one id" and "check the boundary" are structural rather than remembered in the fourteenth node.
- **Two SQLite files, not one.** Checkpoints are per-run scratch; long-term memory is what the operator
  taught the system. Opposite lifetimes — sharing a file makes "clear the checkpoints" a command that can
  destroy the second.
- **The thread id *is* the run id.** A checkpoint lineage belongs to one execution, so a session's runs must
  not share a thread or the second resumes into the first one's state. It also makes `--resume` a direct
  lookup with no mapping table.
- **Fan-out is sequential await, journal first, no queues.** Queues buy surviving a slow consumer at the
  price of a bound, a drop policy and silent loss. The consumers are a file append and a terminal draw
  against a producer whose steps are minutes. Phase 2.3 adds a network consumer and can revisit it then,
  with a reason rather than an anticipation.
- **A consumer that raises is detached, never fatal.** A broken terminal must not lose a ten-minute analysis.
- **Closing a session waits for its runs; it does not kill them.** Leaving is not the same statement as
  stopping — the §1.3 rule, one level up.
- **Five of seven analysis events modelled.** `layer-ready` and `claim` carry payloads no subsystem builds
  yet; they are recorded in `EVENT_TYPES_NOT_YET_EMITTED` with the phase that will, and a test fails if that
  list stops matching. Same discipline as 0.7's `FRONTEND_ONLY_VOCABULARIES`.
- **Notebooks excluded from ruff.** They are a research record and their imports are in narrative order.
  It also makes `ruff check .` a usable gate rather than one that must remember which directories count.

### What Phase 0 caught, unprompted

Adding three `StrEnum`s failed `test_every_backend_enum_is_classified` immediately, and six new settings
failed `test_env_example_documents_every_configurable_field`. Both are Phase 0 tests doing exactly what they
were written for, in the next phase, without anyone remembering they existed.

### One hazard found by accident, recorded rather than fixed

Demonstrating the resume gate from the CLI produced a journal with its tail duplicated. Diagnosed rather
than assumed: the two `S20 completed` steps carried **different `stp_` ids and near-identical durations**,
which means two processes wrote them. `kill -9` in Git Bash had reached the `uv` wrapper rather than the
Python process, and the orphan finished its stage half a minute later and appended to the same file.

**The application was correct; my demonstration was not.** Repeating it against the real process id gives a
clean 12-line journal, S1 not re-run, resume completing from the checkpoint.

What it exposed is genuine though: **nothing stops two processes appending to one run journal.** In Phase 1
that needs an orphan to happen at all, so it is left open and recorded in `journal_writer.py`. Phase 2.5
makes it real - several Inngest workers, any of which could be handed the same run - and the fix belongs
there, where the Redis lock from 0.3 already exists.

Worth keeping as a method note: the fastest way to a wrong conclusion here would have been to "fix" the
duplication in the fan-out. The step ids said it was two writers, not one writer emitting twice.

### Next — Phase 1.1

Datasets. PDF pp.21–24 and the learning roadmap; `notebooks/02_data_exploration/`. The spine is in place, so
1.1 onwards adds nodes to it rather than changing it, and `aeris run --graph` is the seam 1.10 extends.

---

## Session - 2026-08-31 (revision) - **The harness correction.** Barge-in must not kill the run.

A concept revision before Phase 1.0, and it turned up **one thing the documents had backwards and one they
never had at all.** Both were recorded into the docs, not just noted, because 1.0 is the phase that builds
the thing they affect.

### What was backwards

`api-contract.md` §5 and `product-truth.md` §1.3 both said: speech during an utterance cancels synthesis
**and the run behind it**, emitting `run-error`. The product owner: **no.**

The reasoning is sound and worth keeping. A ten-minute run is normal here. An operator who says *"wait, which
sensor is that?"* mid-run is asking a question, not withdrawing the request - and under the old rule they
would learn that speaking costs them ten minutes, so they would stop speaking. That kills the product's
identity, not a feature of it.

Now **three** signals where there was one:

| Signal | Stops | Survives |
|---|---|---|
| Barge-in | synthesis of that one utterance | the run, streaming, unaffected |
| Standby ("quiet down") | all speech until released | the run, silently |
| Abandon (explicit only) | the run at the next node boundary | the checkpoint |

Node-boundary cancellation is **still built in 1.0**, for row three, for the original reason. Only *who pulls
it* changed.

### The consequence nobody had drawn, and why it lands on 1.0 rather than 1.13

If the run outlives the interruption, **the conversation has to run concurrently with it.** That is not a
voice-loop concern; it is a shape constraint on the spine:

- the agent **narrates** from trace steps already on the stream;
- a mid-run question is answered from model knowledge, **labelled provisional, `claimIds` empty**, then
  superseded by the grounded answer (`supersedesUtteranceId`). An *unlabelled* provisional answer is the
  worst thing this system can emit - a fluent unsourced number, the exact failure the whole evidence
  architecture exists to prevent. So the label is a contract term, not a UI nicety;
- a finished run **interrupts the conversation** three turns later: *"coming back to the built-up question."*

None of that is possible if 1.0 awaits `graph.astream()` to exhaustion inside the turn. So 1.0 now owes
`app/services/sessions/` - a session owning a thread id and its runs, `run_handle.py` returning immediately
while a background task consumes the stream, and `fanout.py` splitting one stream to many consumers. **This
is the same argument the docs already made for cancellation**: nearly free now, a rewrite of every node
signature later.

New 1.0 gate: *with a run in flight, a second command into the same session is accepted and answered while
the run continues, and the run still reaches `run-complete` with the journal it would have produced
undisturbed.* That gate fails on any inline-await design, which is the point of it.

### What was missing entirely

**No memory of any kind existed in these documents** beyond the LangGraph checkpointer - and the checkpointer
is not memory, it is the resume point of one run. Grepped for it: no `BaseStore`, no long-term store, no
cross-session recall, anywhere in `bcontext/`.

The requirement is JARVIS-shaped: a session opened by keypress (the frontend already carries `shortcut` on
every `CommandDefinition`), **thread memory** for the session, **long-term memory** across sessions.

Two decisions worth not relitigating:

- **Long-term memory is opt-in.** The operator says "remember that", or the agent proposes and the operator
  agrees. Not a limitation - a system that silently retains everything an analyst said is unauditable, and
  this workload is disaster response and defence. Every entry records who, when, and which session: the
  provenance rule the evidence chain already runs on, applied to what the agent believes.
- **Recalled memory is context, never evidence.** It shapes what AERIS does; it can never become a claim. A
  claim comes from a specialist model, every time. This is the guardrail that keeps "add memory" from
  quietly becoming the RAG-over-chat-logs system that produces confident nonsense.

Mechanics are LangGraph's - checkpointer for the thread, `BaseStore` for the namespace - per ADR-002. 1.0
wires the store from `config.py` and leaves it empty; `remember` / `recall` become ordinary agent tools in
1.9.

### Documents changed

`product-truth.md` (§1.3 rewritten, §1.3.1 and §1.6 new) - `api-contract.md` §5 - `architecture-context.md`
- `architecture-decisions.md` - `roadmap.md` (1.0 deliverable + gate, 1.13 deliverable + gate) -
`folder-archtecture.md` (`services/sessions/`, `pipeline/memory_store.py`).

**Nothing in Phase 0 is affected** - 97 tests still green, no code touched.

---

# Backend Memory

Session log for the AERIS backend. Newest first. Written for the next agent or developer picking this up
cold: what was decided, why, what is still broken, and what not to relitigate.

---

## Session — 2026-08-31 (0.7) · Contract vendoring. **Phase 0 is complete.**

**Phase 0.7 is done, and with it all of Phase 0.** `pnpm run contracts:export` writes **92 schemas from 14
modules** into `bcontext/contracts/schemas.json`; 34 new tests hold the backend to them. **97/97 green**,
ruff clean, `uv lock --check` clean, `aeris doctor` exit 0, `contracts:check` exit 0.

### Zod 4 removed the hard part

The frontend is on **Zod 4.4.3**, which ships `z.toJSONSchema()` natively — no `zod-to-json-schema`
dependency, no conversion code to maintain. The only new devDependency is `tsx`, to run a TypeScript script
that resolves the `@/` path aliases.

**`io: "input"` is the whole correctness of the exporter, and it is not the obvious choice.** The frontend
calls `schema.parse(response.data)`, so a backend payload is the schema's *input*. Any schema carrying a
`.transform()`, a `.default()` or a coercion has a different output type, and exporting the output side would
produce a contract demanding values the backend cannot send — a `Date` object where the wire has a string.
Nothing currently transforms, which is exactly why the flag had to be set now rather than the day one does.

### The pairings were discovered, not guessed

Rather than hand-write which backend enum matches which frontend schema, I compared value sets
programmatically. **22 of 27 backend `StrEnum`s match a frontend schema exactly.** Two match *two* schemas
each — `SceneModality` is both `acquisitionModalitySchema` and `sensorModalitySchema`; `TraceStepState` is
both `traceStepStateSchema` and `executionStepStateSchema`. That is the frontend defining one vocabulary
twice, and both aliases are now checked, so if those two ever drift apart the backend finds out.

The five unpaired backend enums each carry a reason in `app/constants/contracts.py`. Two are worth knowing:
`FigureKind` and `LegendKind` have no counterpart because **`figure-ready` is agreed in `api-contract.md` §6
and not yet implemented on the frontend** — when it lands, the test starts matching. `ErrorCode` is unpaired
because the frontend types `ApiErrorPayload` in TypeScript rather than Zod, so there is nothing to compare
against; that was verified, not assumed.

The reverse direction turned out to be the more useful artefact. `FRONTEND_ONLY_VOCABULARIES` lists nine
frontend enums the backend has not met, each with the phase that will — `agreementStateSchema` and
`fusionRefusalIdSchema` at 1.11, `colorRampIdSchema` at 1.2.1, and so on. **Read down it and you are reading
what Phase 1 still owes the frontend**, and a test fails if a new frontend enum appears unclassified.

### The test that keeps the rest honest

`test_every_backend_enum_is_classified` is the one that matters. Not the pairings — those are checked easily
enough. The way a contract suite rots is that someone adds an enum, no test mentions it, and a year later the
two sides turn out to have spelled it differently all along. Every `StrEnum` in `app/constants/` must be
either paired or declared backend-only **with a reason**, and both maps are checked for staleness in the
other direction too, so an entry naming an enum that no longer exists is caught rather than silently doing
nothing.

Mutation-checked, including the exact bug `api-contract.md` §7 records as already made once:

| Mutation | Result |
|---|---|
| `ModelId.CHANGEFORMER = "mdl_changeformer"` | **4 tests failed** — the vocabulary check, the named-twelve check, and two payload validations |
| `RunStatus` gains a `PAUSED` the frontend never heard of | `test_a_shared_vocabulary_matches_the_frontend_exactly[statuses.RunStatus]` failed |
| a new unclassified `StrEnum` | `test_every_backend_enum_is_classified` failed |

### Three payload facts that were invisible from either side

**`nextCursor` is nullable *and required*.** Zod's `.nullable()` means "the key is present and may be null";
it is not optional. So `model_dump(by_alias=True, exclude_none=True)` — a reasonable-looking way to keep
payloads small — drops the key and the frontend rejects the whole page.

**A timestamp must end in `Z`.** The exported pattern ends `(?:Z)$`; Zod permits no numeric offset unless
asked. Measured, because the three obvious ways to serialise the same instant disagree:

```
datetime.isoformat()                    2026-08-31T12:00:00+00:00   REJECTED
model_dump(mode="json")                 2026-08-31T12:00:00Z        accepted
model_dump()          (mode="python")   datetime(...) object        not a string at all
```

So **`mode="json"` is part of the contract**, not a formatting preference — and Pydantic emitting exactly the
right form is luck rather than design. My first draft of that test claimed "Python's default is `+00:00`",
which is true of `datetime.isoformat()` and misleading about Pydantic; corrected to the measured three-way
result.

**The gate is written as the real mistake.** The roadmap asked for "a deliberately wrong field name". A
hand-typed typo would prove the validator works; `model_dump()` without `by_alias=True` proves it catches
*the* error — one keyword argument away at every call site, producing a dictionary that looks entirely
correct in a debugger.

### Decisions worth not relitigating

- **The exporter is TypeScript and lives in `frontend/`, not Python in `backend/scripts/`** as
  `folder-archtecture.md` planned. It has to *evaluate* Zod, which only Node can do; a Python version would
  parse TypeScript or shell out to Node anyway. It also belongs where `api-contract.md` §0 puts the
  authority. The doc now records the relocation and the reason rather than silently disagreeing with the
  tree.
- **`schemas.json` is committed, not generated at test time.** A test that regenerates its own fixtures
  passes by construction and proves nothing. Committing it also means `uv run pytest` works on a machine
  that has never installed the frontend — verified by running `tests/contracts/` alone.
- **Deterministic output: sorted keys, no timestamp.** Regenerating an unchanged contract is byte-identical,
  so a diff means the contract changed rather than someone ran the script. That is what makes
  `pnpm run contracts:check` meaningful; verified by tampering with the committed file and watching it exit 1.
- **Schemas are inlined rather than `$ref`-linked.** 276 KB for 92 schemas. The alternative puts a reference
  resolver between every Python test and the thing it validates; each entry here goes straight to a validator.
- **Discovery by directory scan, on both sides.** The exporter scans for `*.schema.ts`; the test walks
  `app/constants/`. A curated list on either side is a second thing to maintain, and the failure it invites —
  a vocabulary one side added and the other never saw — is silent.
- **Format checking is on.** `jsonschema` ignores `format` unless asked, and `date-time` is precisely the
  constraint most likely to be got subtly wrong. Off, the timestamp test above would pass against anything.
- **`.mts`, not `.ts`.** The frontend is not `"type": "module"`, so tsx compiled the script to CJS and
  top-level `await` and `import.meta.url` both failed. The `.mts` extension forces ESM.

### Phase 0 is complete

0.1 skeleton · 0.2 PostGIS · 0.3 Redis · 0.4 MinIO · 0.5 Inngest · 0.6 `aeris doctor` · 0.7 contracts.
**97 tests.** Four containers. The gate, stated honestly as three commands:

```
docker compose up -d
uv run alembic upgrade head
uv run aeris doctor          # exit 0, every row green
```

A full `docker compose down -v` clean-machine run has still **not** been done — it destroys the local
volumes, so it remains the product owner's call. The 0.6 entry demonstrates the equivalent against a
never-migrated database and an unused bucket prefix.

### Next session — Phase 1.0

The Typer CLI already exists (0.6 built `app/cli/main.py` and `doctor.py`), so 1.0 is the **LangGraph spine**
and nothing else: `services/pipeline/state.py` (the `TypedDict`), `checkpointer.py` (SQLite, selected from
config), `stream.py` over `get_stream_writer()`, `app/schemas/events/` (models only, no protocol),
`cli/renderers/` (the live S1–S20 trace and the JSONL journal), a two-node throwaway graph to exercise it,
and cancellation checked at every node boundary.

**Explicitly not built**: `StepRunner`, `EventSink`, `LLMProvider`, an executor, a context object, a retry
loop (ADR-002).

Two things 0.7 hands to 1.0 directly: the run journal has to validate against the vendored contracts, and
`tests/contracts/` is where that test goes. And `app/schemas/events/` will be the first place the
`mode="json"` / `Z`-suffix rule actually bites, because every event carries a timestamp.

---

## Session — 2026-08-31 (0.6) · `aeris doctor`. Two performance bugs and one race that had been passing.

**Phase 0.6 is done.** `aeris doctor` prints seven rows, exits 0 or 1, masks every credential, and is green
against the running stack. 10 new tests, **63/63 green across three consecutive full-suite runs**, ruff and
`uv lock --check` clean. `aeris` is now a real console script (`[project.scripts]` in `pyproject.toml`).

The command was supposed to be mostly rendering — 0.2–0.5 had already written and tested every probe. It was.
What it also did was **run all four dependencies together for the first time**, and that found three bugs
that no single sub-phase could have.

### 1. `localhost` costs 2.09 seconds per connection on this machine

The first doctor run reported 2720 ms for PostgreSQL and 2157 ms for Redis. My first guess — botocore
blocking the event loop during client construction — was wrong; measuring showed construction at 473 ms for
storage, 38 ms for the engine, 0.3 ms for Redis. The cost was in the **connection**:

```
localhost    -> [('IPv6', '::1'), ('IPv4', '127.0.0.1')]
127.0.0.1    -> [('IPv4', '127.0.0.1')]

connect to localhost      2089.4 ms
connect to 127.0.0.1        56.7 ms
connect to localhost      2089.8 ms      <- every connection, not just the first
connect to 127.0.0.1        44.9 ms
```

`localhost` resolves to `::1` first, and `docker-compose.yml` publishes every port on `127.0.0.1` only — a
deliberate choice from 0.2, and the right one. So each connection spends ~2.09 s on a doomed IPv6 attempt
before falling back. **Every DSN and endpoint in `.env` now uses `127.0.0.1`.** Postgres latency went
2720 → 668 ms, Redis 2157 → 107 ms.

**`STORAGE_BROWSER_ORIGIN` deliberately stays `localhost`**, and that exception matters: it is the `Origin` a
*browser* sends, and to a browser `http://localhost:3000` and `http://127.0.0.1:3000` are different origins —
which 0.4 demonstrated by using exactly that difference as its negative CORS test. Changing it would break
CORS while looking like a consistency fix.

This is worth remembering beyond Phase 0: a Phase 1 CLI run opens all four connections at start-up, so this
was about six seconds of dead time before any analysis began.

### 2. The Inngest round trip had been passing by luck

The doctor's round-trip row failed while the Phase 0.5 test passed. Measuring the propagation delay:

```
run 1: visible after 5 retries, 154.7 ms
run 2: visible after 8 retries, 232.4 ms
run 3: visible after 8 retries, 251.0 ms
run 4: visible after 8 retries, 264.5 ms
run 5: visible after 7 retries, 218.8 ms
```

The event API answers `200` on *acceptance*; the event becomes queryable 150–265 ms later. Both
`check_event_delivery()` and the 0.5 test read once, immediately. **The 0.5 gate was a coin flip that landed
heads three times.**

Fixed by polling to a deadline, and — more importantly — by giving both callers **one** function,
`find_event_on_bus()`, so the knowledge that the bus is eventually consistent lives in one place instead of
being re-remembered at each call site. The 0.5 test now goes through it too. Verified with three consecutive
full-suite runs rather than one.

This is the concrete instance of the thing the 0.4 and 0.5 entries kept circling: **passing is not evidence.**
It is also why the recorded-run convention now says how many times a suite was run, not just that it passed.

### 3. rich eats square brackets, and it ate the environment

`aeris version` printed `SatQuery AI (AERIS) 1.0.0` with nothing where `[local]` should be — rich parsed
`[local]` as a style tag. The same hazard applies to **every data cell in the doctor table**: an unescaped
version string or failure message containing brackets is silently altered, which in a command whose whole job
is reporting values accurately is a correctness bug, not a cosmetic one. Every value cell now goes through
`rich.markup.escape()`; the ok/FAILED cell is the exception because its markup is ours.

Two smaller rendering fixes from the same run: columns are `overflow="fold"` so a long DSN wraps instead of
being truncated with an ellipsis (a diagnostic must not hide the part someone needed), and the Postgres
version banner is trimmed to its first two words.

### The noise floor had never grown

The first doctor run emitted **142 KB** of botocore hook-registration chatter over a twenty-line table.
`THIRD_PARTY_LOG_LEVELS` existed from 0.1 and had not been extended when 0.4 and 0.5 added dependencies.
Added: `botocore`, `boto3`, `aiobotocore`, `s3transfer`, `httpx`, `httpcore`, `aiohttp`, `redis`, `alembic`.
Output went 142 KB → 6 KB.

One subtlety: the `inngest` entry did not silence the SDK, because `app/lib/inngest.py` **hands the client our
own logger**. It now hands it a child logger, `app.lib.inngest.sdk`, so the SDK's narration can be silenced
without also silencing our messages about Inngest. **A library given your logger inherits your level** — the
noise floor cannot reach it by the library's own name.

### The Phase 0 gate is three commands, not two

`roadmap.md` said `docker compose up` then `aeris doctor`. That was never going to be true: a fresh database
has no schema. Rather than make the diagnostic run migrations — **a diagnostic that alters a schema is one
nobody can safely run against a database they care about** — the gate is stated honestly as three commands,
and doctor reports the missing revision with the command that fixes it.

Demonstrated without destroying the working environment, by pointing the command at a database created empty
and a bucket prefix that had never existed:

```
aeris doctor          EXIT 1   PostgreSQL 17.5, no PostGIS / not migrated / 2 of 7 checks failed
                               ...and Object storage: ok, 5 buckets  <- provisioned by that run
alembic upgrade head  exit 0
aeris doctor          EXIT 0   All dependencies are healthy.
```

The temporary database and buckets were dropped afterwards. **A full `docker compose down -v` clean-machine
run has not been done** — it would destroy the local volumes, so it is the product owner's call.

### Decisions worth not relitigating

- **The exit code is the contract, and it is tested from a subprocess.** Calling the Typer callback in-process
  tests neither the exit status nor the console-script entry point, and `main.py` calls `asyncio.run()`, which
  raises inside the tests' already-running loop. `subprocess.run(...).returncode` is also the one form that
  cannot be misread — this session lost time twice to a pipe eating an exit code (`alembic … | tail` in 0.2,
  `docker exec … | head` in 0.5).
- **`doctor` writes by default; `--read-only` opts out.** It creates missing buckets and sends one
  health-probe event, both idempotent. A setup verifier that reports a fixable problem and refuses to fix it
  makes the operator run a second command to finish the job.
- **A row is not "reachable".** A Postgres with no schema, a Redis on `allkeys-lru`, storage with no buckets
  and an Inngest scanning for a nonexistent app all answer a ping perfectly, and every one is a real first-run
  failure. Each is its own row, and `test_a_reachable_redis_that_would_evict_a_lock_is_reported_unhealthy`
  pins the principle.
- **The credential test is written as a canary sweep, not a field list.** It runs the real command with
  distinctive passwords in every credential-bearing setting and fails if any appears in the output — so a
  *future* setting that carries a credential fails it without anyone remembering to add it. Forgetting is the
  whole failure mode: the code works perfectly while printing the password.
- **`MASKED_URL_PROPERTIES` in `config.py`** handles the secrets that cannot be `SecretStr` because
  SQLAlchemy and redis-py must parse them. Two masking mechanisms because there are two kinds of declaration.
- **Probes run concurrently.** Serially, a machine with three things down costs three timeouts one after
  another, and the command people run when something is broken must not be slowest exactly then.
- **`check_schema_version()` lives in `lib/database.py`, not the CLI.** It needs the engine, and "is the
  schema the shape this checkout expects" is a database question. `_read_current_revision` is sync because
  Alembic's `MigrationContext` is, and it is handed to `run_sync` — the §7 framework-callback case.

### Next session

**0.7 — Contract vendoring**, the last of Phase 0. **Done — see the 0.7 entry above.** A script exports the frontend's Zod schemas to JSON Schema
into `bcontext/contracts/`, and a pytest validates backend fixtures against them. Gate: a deliberately wrong
field name fails the contract test.

Worth deciding first: whether the export runs from Node (`zod-to-json-schema` against
`frontend/features/*/schemas/*.ts`) as a committed script, and whether the generated schemas are committed.
They should be — `bcontext/contracts/` is read by tests, and a test that regenerates its own fixtures proves
nothing.

Then **Phase 1.0** — the Typer CLI skeleton already exists, so 1.0 is the LangGraph spine: `state.py`,
`checkpointer.py`, `stream.py`, the renderers, and cancellation at every node boundary.

---

## Session — 2026-08-31 (0.5) · Inngest, provisioned and deliberately unbound. Plus a timeout in the wrong unit.

**Phase 0.5 is done, and the thing it delivers is partly a proof that something was *not* built.** Against a
live `inngest/inngest:v1.44.0`: the dev server is reachable, and an event sent through the Python SDK is read
back off the bus by the id the server handed out. 8 new integration tests, **53/53 green**, ruff clean,
`uv lock --check` clean.

### The bug that cost the most, and the trap in it

`inngest.Inngest(request_timeout=...)` is typed `int | timedelta`, and **the `int` branch is milliseconds** —
`client.py` does `request_timeout / 1000`. Passing `settings.inngest_request_timeout_seconds` (10) directly
meant every send timed out after **10 ms**. Every other timeout in this backend, and in botocore, redis-py
and asyncpg, is seconds.

What made it expensive is what the SDK reported: `SendEventsError: never received response while sending
events`. No mention of a timeout, no mention of a unit. It took reading the SDK source to find the `/ 1000`.

The fix passes `timedelta(seconds=...)`, which the signature also accepts. **Prefer the `timedelta` overload
whenever a library offers one** — it is the only form that carries its unit, and this class of bug is
invisible at the call site otherwise.

### Deferred by design, and asserted rather than asserted-in-prose

ADR-002 splits the work: LangGraph owns the graph, its state, its checkpointing and its resume; Inngest owns
durable *execution*; LangChain owns LLM access. Phase 1 runs the engine as a CLI where durability **is** the
LangGraph checkpointer, so there is nothing for Inngest to retry until Phase 2.5. No function, trigger or
step is defined.

Rather than leave that as a sentence in `roadmap.md`, `test_no_functions_are_registered_yet_and_that_is_deliberate`
checks it against the **dev server's own app list** — because the claim is about what the server was told,
not about what the repository contains. If a function appears before 2.5 the test fails and asks the useful
question: did the durability decision change, or did someone add a worker without noticing the checkpointer
already handles it?

Provisioning it now is not busywork. It proved three things that would otherwise have surfaced in 2.5 *while
blocking the binding*: the SDK installs and runs on cp314 (0.5.19), the dev server runs alongside the rest of
the stack, and the event round trip is real.

### Mutation checks — and one of them was itself wrong first

Three mutations, and **two are server mutations rather than code ones**, because the claims are about how the
dev server was started:

| Mutation | Caught by |
|---|---|
| A (code) read-back queries an event name never sent | `test_an_event_sent_..._read_back_off_the_bus` |
| B (server) started with `-u <app url>` | `test_no_functions_are_registered_yet_...` |
| C (server) started with no flags at all | `test_app_discovery_is_off_...` |

**C exists because B did not fail the discovery test.** Passing `-u` turns `autodiscover` *off* while filling
`urls`, so B alone would have left that assertion unproven — possibly vacuous. Measured:

```
no flags                   autodiscover=True   urls=[]        poll=True
-u http://localhost:3000/… autodiscover=False  urls=[<the url>] poll=True
--no-discovery --no-poll   autodiscover=False  urls=[]        poll=False   <- ours
```

The lesson generalises: **a mutation that does not fail the test has not proved the test is fine — it has
proved the mutation was the wrong one.** Keep going until the assertion has actually been seen to fail.

### The image has nothing in it

`inngest/inngest` carries the `inngest` binary and essentially nothing else: **no curl, no wget, no nc, no
busybox**, and `/bin/sh` is `dash`, so not even bash's `/dev/tcp` trick. The first healthcheck (`wget
--spider`) left the container permanently `unhealthy` while the server was answering fine from the host.

The answer is the image's own binary: `inngest api health`, which targets the local dev server by default.
Verified to exit **0** when the server answers and **1** when it does not — checked without a pipe, because
`docker exec … | head` reports `head`'s exit code and I briefly mis-read it as "always 0". That is the second
time this session's family of bugs has been a pipe eating an exit code; the first was `alembic … | tail` in
0.2. **When measuring an exit code, never pipe.**

### What was built

| File | What it settles |
|---|---|
| `docker-compose.yml` | `inngest/inngest:v1.44.0`, `--no-discovery --no-poll`, healthcheck via its own binary |
| `app/constants/tasks.py` | `aeris/<domain>.<action>`, past tense, and the one event that actually exists |
| `app/config.py` | App id, both base URLs, request timeout; `inngest_is_production` derived from `environment` |
| `app/lib/inngest.py` | The client, `send_event`, `check_health`, `check_event_delivery` |
| `tests/integration/test_inngest_connectivity.py` | The gate, and the proof of what was not built |

### Decisions worth not relitigating

- **The client lives in `lib/inngest.py`; the functions will live in `app/inngest/`.** Same split as
  `lib/database.py` vs `app/db/models/`. `folder-archtecture.md` updated to say so, so nobody puts the
  Phase 2.5 functions in `lib/`.
- **Every SDK argument is passed explicitly.** The Inngest client falls back to `INNGEST_EVENT_KEY`,
  `INNGEST_SIGNING_KEY`, `INNGEST_DEV` and `INNGEST_BASE_URL` from the process environment when an argument
  is omitted — a second source of configuration that `.env.example` does not document and `aeris doctor`
  cannot report. `code-standards.md` §4 is *config.py or nowhere*, and a library's own defaults do not get an
  exemption. Pinned by a test.
- **`is_production` is derived from `environment`, never configured separately.** Two switches would
  eventually disagree, and the failure is a deployed process posting events at a dev server that is not
  there — or a local run writing into the production event history.
- **Acceptance is not delivery.** The event API answers `200` the moment it accepts a well-formed request, so
  `check_event_delivery()` sends *and then reads back by id*. A check that stopped at the 200 would pass
  against a server dropping every event. Same shape as 0.4's status-code-versus-header lesson.
- **`reset_client()`, not `close_client()`.** The Inngest SDK exposes no shutdown and its
  `AuthenticatedHTTPClient` has no `aclose` — checked, not assumed. Naming it `close_client` for symmetry with
  the other three `lib/` modules would claim connections were released when they are only dereferenced. It is
  deliberately *not* wired into the conftest teardown, because there is nothing to tear down.
- **No volume and no `--persist`.** Nothing in this server is durable state: the events sent here are health
  probes with no consumer, and Phase 2.5's durable record is Inngest Cloud's, not a local disk's.
- **`app/constants/tasks.py` lists one event, not the Phase 2.5 ones.** An event name is the hardest string
  in the system to change — it is written into durable history and matched by triggers that deploy
  separately. The *convention* is fixed now; the names are not invented before something sends them.

### Phase 0 is now one sub-phase from done

0.1–0.5 are all **done**. What remains:

- **0.6 — `aeris doctor`.** **Done — see the 0.6 entry above.** This is now mostly rendering. All four dependencies already return a
  purpose-built dataclass for their row: `DatabaseHealth`, `RedisHealth`, `StorageHealth`, `InngestHealth`,
  plus `CrossOriginAccess` and `EventDeliveryProof`. The command is a Typer entry point, a `rich` table, and
  the masked-settings block — the probing is written and tested.
- **0.7 — Contract vendoring.** Zod → JSON Schema into `bcontext/contracts/`, and a pytest that fails on a
  deliberately wrong field name.

Then **Phase 0's own gate**: `docker compose up` then `aeris doctor`, all green, on a machine that has never
run this project. Worth actually doing on a clean volume rather than declaring — four services now, and
`ensure_buckets()` and the migrations both have to run on first contact.

---

## Session — 2026-08-31 (0.4) · Object storage. The CORS rule everyone gets wrong, measured rather than assumed.

**Phase 0.4 is done and the gate is demonstrated.** Against a live MinIO `RELEASE.2025-09-07T16-13-09Z`: five
buckets provisioned by application code; a file PUT through a presigned URL **with no credentials and no
SDK** and read back byte-identical; CORS proven in a real browser. 12 new integration tests, **45/45 green**,
ruff clean, `uv lock --check` clean.

Checked by mutation, each intended test confirmed to catch its break (recorded at the foot of the test file):

| Mutation | Caught by |
|---|---|
| CORS judged by status code, not the header | `test_an_unknown_origin_is_refused_...` |
| `get_object` returns `b""` for a missing key | `test_a_missing_object_raises_...` |
| `NotImplemented` treated as a hard failure | `test_the_provider_reports_which_cors_...` |

### The finding. It corrects a claim this repository had written down twice.

`roadmap.md` and `architecture-decisions.md` both justified CORS on `figures` with *"the browser loads these
as `<img>` cross-origin"*. **That justification is wrong, and it is wrong in the direction that ships broken
configurations.** A page was served at the configured origin and asked to load a real PNG from the `figures`
bucket three ways. From the allowed origin `http://localhost:3000`:

```
plainImage:     loaded (64x64)
corsFetch:      ok (185 bytes, image/png)
canvasReadback: ok - read pixel rgba(16,185,129,255)
```

and from `http://127.0.0.1:3000` — a **different origin** to a browser, and not on the allow-list:

```
plainImage:     loaded (64x64)          <-- still loads
corsFetch:      FAILED: Failed to fetch
canvasReadback: FAILED to load with crossOrigin=anonymous
```

**A plain `<img>` loads in both cases.** Images are exempt from CORS unless the page reads their pixels back.
So "the picture shows up" is not evidence of anything, and checking it that way is precisely how a broken
configuration reaches production. What actually needs CORS is `fetch()` and
`crossOrigin="anonymous"` → canvas → `getImageData` — which is Cesium's path for every tile, and the reason
`api-contract.md` §8 rule 2 says the globe "silently renders nothing". Both documents are corrected.

Second half of the same lesson, and why the health probe is written the way it is: **a disallowed origin
still receives HTTP 200 and the object's bytes.** CORS is enforced by the browser; the server's only signal
is the *absence* of `Access-Control-Allow-Origin`. A check written against the status code passes against a
completely closed server. `check_cross_origin_access()` therefore asserts on the header and never on the
status, and a test pins that so nobody simplifies it back.

### MinIO does not implement `PutBucketCors`

Measured, not assumed: it answers `NotImplemented`, and `GetBucketCors` answers `NoSuchCORSConfiguration`.
Per-bucket CORS from application code is impossible there. It is a **server-wide** setting instead,
`MINIO_API_CORS_ALLOW_ORIGIN`, which `docker-compose.yml` now sets.

Real S3 *does* implement the API — and starts with **no** CORS at all. So neither provider is the special
case, and `configure_cross_origin_access()` applies the rules where they are supported and returns
`CrossOriginMechanism.SERVER_LEVEL` where they are not. Writing only the env var would have worked locally
and silently failed on S3; writing only the API call would have crashed on MinIO.

**MinIO's default is worse than no setting.** With `MINIO_API_CORS_ALLOW_ORIGIN` unset it reflects whatever
`Origin` it was sent *and* sends `Access-Control-Allow-Credentials: true` — any page on the internet could
read these objects from a browser. It is set explicitly even locally so the setting is exercised in
development rather than discovered in production.

### What was built

| File | What it settles |
|---|---|
| `docker-compose.yml` | `minio:RELEASE.2025-09-07T16-13-09Z`, API on 9000, console on 9001, persistent volume |
| `app/constants/storage.py` | The five roles, and `BROWSER_FACING_BUCKETS` — the two CORS is derived from |
| `app/config.py` | Endpoint, credentials, prefix, addressing style, browser origin, presign lifetimes |
| `app/lib/storage.py` | The one client, presigned PUT/GET, `ensure_buckets()`, both health probes |
| `tests/integration/test_storage_round_trip.py` | The gate, the CORS pair, the refusals |

### Decisions worth not relitigating

- **`aioboto3`, against the S3 API — never MinIO's SDK.** MinIO is a local development choice; S3, R2 or
  Supabase Storage is the deployed one. The only line that knows the difference is
  `storage_addressing_style` (`path` for MinIO, which has no wildcard DNS and cannot serve `bucket.host/key`).
- **Storage raises where the Redis cache degrades.** A cache miss costs a recomputation; a missing artefact
  is a broken provenance chain. A caller that read absence as empty bytes would render a blank figure and
  attach it to a claim — the confidently-wrong answer this product exists not to produce.
- **Presigned URLs are signed against `storage_signing_endpoint`, not the internal one.** The signature
  covers the host, so a URL signed for `http://minio:9000` **cannot** be repaired by substituting
  `localhost` into it afterwards. They are the same today; they stop being the same the moment the backend
  moves into the compose network. Pinned by a test.
- **`AnyHttpUrl` adds a trailing slash and an `Origin` header never has one.** `http://localhost:3000/` vs
  `http://localhost:3000` compared as strings is a CORS check that fails against a perfectly configured
  server. `settings.storage_browser_origin_header` strips it, once.
- **The content type is signed into the upload URL**, so `required_headers` is a commitment, not advice.
  Sending a different one is a *signature* mismatch: an opaque 403 arriving at the end of a long upload,
  naming nothing. Pinned by a test that uploads with the wrong type and asserts 403.
- **An upload into `raw` is refused at ticket time** when the content type is not ingestible, rather than
  after several gigabytes have been transferred and rasterio has failed on an unrecognised driver. Only
  `raw` is guarded — the other four buckets hold things this backend wrote.
- **`ensure_buckets()` is Python, not an `mc` command in an init container**, so the same code path
  provisions a local MinIO and a real S3 account. Idempotent; `BucketAlreadyOwnedByYou` is swallowed because
  two processes starting at once is normal.
- **`require_healthy_storage()` deliberately does not check CORS.** A run writes figures server-side and
  succeeds whether or not a browser could read them; failing the run would turn a display problem into a
  lost analysis. It is an `aeris doctor` row instead.
- **The MinIO volume persists, unlike Redis's.** A COG costs minutes of GDAL and a raw scene costs a
  download; losing them to `docker compose down` would make every restart an acquisition run.
- **Bucket names are `{prefix}-{role}`.** The role is a fixed vocabulary (constants); the prefix is
  configuration, so one account can host several deployments. Five separate name settings kept in step with
  a five-member enum would be the same decision written twice.

### Smaller things

- **`ruff` caught a real defect**, not a style one: nine `raise` sites inside `except` blocks with no
  `from`, discarding the botocore cause. Fixed, and `_as_upstream_error` was made sync in the process — it
  builds an exception from values already in memory and is only ever called from an `except` block, the same
  §7 carve-out `_error_code` beside it uses. `raise _as_upstream_error(...) from error` now reads as a raise.
- **`INGESTIBLE_CONTENT_TYPES` was declared and unread**, which this project treats as a defect in its own
  right. It is now the refusal above rather than a claim nothing verified.
- **Port 9001 is bound for MinIO's console** so an upload the tests say succeeded can be looked at. Without
  `--console-address` MinIO picks a random port on every start.
- **The compose file reads `STORAGE_BROWSER_ORIGIN` from `backend/.env`** — the same variable `config.py`
  reads. The allowed origin is stated once, and `app/lib/storage.py` can then prove the two agree.
- **`aiohttp` is declared explicitly** in `pyproject.toml` even though `aioboto3` already pulls it in. It is
  imported directly by the CORS probe, and importing a transitive dependency is how a `uv lock` upgrade
  becomes an unexplained `ImportError`.

### Next session

0.5 — **Done; see the 0.5 entry above.** Inngest, and it is deliberately the smallest sub-phase in Phase 0. Dev server in compose, event keys in
config, connectivity proven, **no workflow logic**: Phase 1 durability comes from the LangGraph checkpointer
and Inngest is not bound until Phase 2.5 (ADR-002). Record it as *deferred by design* rather than as
unfinished. Then 0.6 — `aeris doctor` — which is now four `check_health()` functions away from existing,
since every one of them already returns the dataclass its row will print.

---

## Session — 2026-08-31 (0.3) · Redis. One server, two namespaces, opposite failure policies.

**Phase 0.3 is done and the gate is demonstrated.** Against a live Redis 8.2.9: a value round-trips through
the cache and comes back carrying a TTL; a lock held by one holder makes a second wait and then refuses it
with `CONFLICT`; a lock whose holder vanished is reacquired only after its TTL runs out. 6 new integration
tests, 2 new config tests, **33/33 green**, ruff clean.

Passing is not evidence on its own, so each load-bearing claim was re-checked by breaking the code beneath
it and confirming that exactly the intended test caught it (recorded at the foot of the test file):

| Mutation | Caught by |
|---|---|
| `clear_cache_namespace` calls `FLUSHDB` | `test_clearing_the_cache_does_not_touch_a_held_lock` |
| `cache_set` omits the `ex=` expiry | `test_a_cached_value_round_trips_and_carries_an_expiry` |
| `held_lock` proceeds when acquisition fails | `test_a_held_lock_blocks_a_second_acquirer` |

### The idea the whole sub-phase turns on

The roadmap said "two uses, kept separate: model-manager locks and short-lived cache." The separation is
**not** about storage. It is that the two have *opposite failure policies*:

- A **cache** miss costs a recomputation. Every cache function swallows `RedisError` and reads as a miss, so
  a Redis outage degrades AERIS rather than stopping it.
- A **lock** is exclusive access to the GPU's VRAM. Every lock function raises, because a caller that carried
  on unlocked loads a second model into a card with room for one — and that surfaces stages later as a CUDA
  out-of-memory error with nothing pointing back at Redis.

Everything else in `app/lib/redis.py` follows from that sentence, and it is why the two live in one server
under two key prefixes rather than in two servers or two logical databases.

### The finding worth keeping: `maxmemory-policy` can silently break a lock

**Under any `allkeys-*` policy Redis may evict any key when memory fills. Under any `volatile-*` policy it
may evict any key that carries a TTL — and every lock carries one, because the TTL *is* how a crashed holder
releases.** Either setting therefore lets Redis delete a lock a process is still holding, after which two
processes both believe they own the GPU. No amount of correct code on our side detects it.

So `noeviction` is required, and it is not a preference:

- `docker-compose.yml` starts the server with `--maxmemory-policy noeviction --maxmemory 256mb`.
- `constants/redis_keys.py` states it as `REQUIRED_MAXMEMORY_POLICY` — a constant, not a setting, because it
  is an invariant of the design rather than something an environment may tune.
- `check_health()` reads the **live** value and `require_healthy_redis()` refuses a run when it is wrong.
- A test asserts it, so the other five tests cannot keep passing after the guarantee they rest on has gone.

The consequence is that under memory pressure *writes fail* instead of keys disappearing. The cache absorbs
that as a miss; the lock reports it. Which is also why **every cache entry must expire**: nothing here is
evicted, so a cache key without a TTL is permanent, and enough of those fill the instance — and the first
thing that then fails is a lock write. The TTL on a cache key is what stops the cache breaking the locks.

An **unknown** policy is treated differently from a wrong one. Several managed providers disable `CONFIG GET`;
`check_health` reports `maxmemory_policy=None` with a reason, and `require_healthy_redis` warns rather than
refusing. Refusing would make AERIS unrunnable on every such provider, which is a bigger failure than the one
being guarded against.

### What was built

| File | What it settles |
|---|---|
| `docker-compose.yml` | `redis:8.2-alpine` on **127.0.0.1:6379**, `noeviction`, no RDB, no AOF, no volume |
| `app/constants/redis_keys.py` | `aeris:lock:*` / `aeris:cache:*`, and `REQUIRED_MAXMEMORY_POLICY` |
| `app/config.py` | `REDIS_URL` (required, no default) + five tunables + `redis_url_without_password` |
| `app/lib/redis.py` | The one pool, `held_lock()`, four cache functions, `check_health()` |
| `tests/integration/test_redis_lock_and_cache.py` | The gate, the policy, and the asymmetry |
| `tests/conftest.py` | `REDIS_URL` added to `MANDATORY_ENVIRONMENT`; teardown closes both clients |

### Decisions worth not relitigating

- **The lock is redis-py's `Lock`, not a hand-written recipe.** It already implements the correct one —
  `SET key token NX PX ttl`, released by a Lua script that compares the token before deleting. The token
  comparison is the easy part to omit and the expensive one: without it a holder whose TTL expired releases
  the *next* holder's lock. `held_lock()` adds only the prefix, the timeouts, and "a failed acquisition
  raises". Same reasoning as ADR-002 — do not rebuild what the library already does.
- **A fresh `Lock` object per acquisition, which is why `held_lock` is a context manager.** redis-py keeps
  the token in `threading.local()`, and every coroutine on one event loop shares a thread — so two concurrent
  acquisitions through a *shared* `Lock` would share one token and the first release would delete the other's
  key. Never cache a `Lock` object.
- **Prefixes, not logical databases.** Redis Cluster and most managed providers expose only database 0, so
  `SELECT` is not portable and a deployment relying on it would silently collapse the two namespaces.
- **Never `FLUSHDB`.** It would free every lock a live process still believed it held. `clear_cache_namespace`
  scans the cache prefix instead, and a test fails the moment someone reaches for the shorter version.
- **Two distinct errors on the lock path.** Redis unreachable → `UpstreamUnavailableError` (503, retryable).
  Redis answered and somebody else holds it → `ConflictError` (409, busy). The frontend branches on the code,
  so the distinction is contract rather than wording.
- **A release failure raises only when the body succeeded.** If the body already failed, re-raising from the
  exit path would replace a more informative exception and would swallow `RunCancelledError` on the barge-in
  path. On the success path, `LockNotOwnedError` means the critical section outlived its TTL and another
  holder may have run concurrently — that must surface. A plain `RedisError` there only warns: the key
  expires on its own, so the cost is a delay, not a correctness failure.
- **One lock TTL answers two questions that pull opposite ways** — how long a crashed holder blocks everyone,
  and how long a live holder may safely work. No value is right for both. It is sized for the second (120 s,
  a model load onto an 8 GB card); a holder needing longer calls `extend()` rather than having the setting
  raised, because raising it also lengthens every crash recovery.
- **`asyncio.CancelledError` is caught nowhere in this module.** It derives from `BaseException`, so
  `except RedisError` cannot absorb it — which is what barge-in needs.
- **No persistence and no volume on the container.** A cache entry is reconstructible and a lock that
  outlived the process holding it would be a bug. Anything that must survive a restart belongs in Postgres.

### Smaller things

- **Port 6379 was free**, checked rather than assumed. The 5432 collision that pushed Postgres to 5433 has no
  counterpart here, so Redis is on its default port. Do not "fix" the inconsistency.
- **`redis[hiredis]` installs clean on Python 3.14** — redis 8.1.0, hiredis 3.4.1, both with cp314 wheels.
- **Redis 8 is AGPLv3.** 7.4 was the source-available RSAL/SSPL interval, so 8.x is also the licence-clean
  choice for a project that will be judged and published.
- **`.env.example` said "Inngest (Phase 0.3)"** — Inngest is 0.5. Corrected.
- **`MANDATORY_ENVIRONMENT` grew again**, exactly as the 0.2 entry predicted it would. Every new required
  setting re-arms `test_invalid_enumerated_value_is_rejected`; add the field there in the same change.
- **`aeris doctor` does not exist yet** (it is 0.6), so the "a row in `aeris doctor`" step of the Phase 0
  setup pattern is outstanding for both PostGIS and Redis. Both `check_health()` functions return the
  dataclass that row will print, so 0.6 is rendering, not probing.

### New convention, from this session onward

**Every test file records its own successful run as a comment at the foot of the file** — the command, the
date, the pass list and the environment it ran against. Product owner's request, and it makes a gate
reviewable without re-running it. Where a claim was checked by mutation, the mutation table goes there too.

### Next session

0.4 — MinIO. Same pattern: provision in compose, client in `app/lib/storage.py`, health probe, a row in
`aeris doctor`, a test. **Done — see the 0.4 entry above.** Buckets `raw`, `cog`, `artefacts`, `figures`, `reports`; presigned PUT/GET; **CORS
configured on `figures`**, which the browser loads cross-origin as an `<img>` (`api-contract.md` §6). The
frontend's memory names CORS as the most common first-day failure, so the gate is a real cross-origin load,
not a `curl`.

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
a row in `aeris doctor`, a test. **Done — see the 0.3 entry above.**

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
