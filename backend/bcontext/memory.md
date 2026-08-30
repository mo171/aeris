# Backend Memory

Session log for the AERIS backend. Newest first. Written for the next agent or developer picking this up
cold: what was decided, why, what is still broken, and what not to relitigate.

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

- **0.6 — `aeris doctor`.** This is now mostly rendering. All four dependencies already return a
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
