# Phase 2.5 Inngest Binding & Postgres Checkpointing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bind Inngest for durable graph execution with automatic retries and backoff, migrate LangGraph checkpointer from SQLite to Postgres (`AsyncPostgresSaver`), and stream live run events across Redis Pub/Sub to SSE clients.

**Architecture:** An event-driven Inngest runner where `POST /api/v1/investigations/{id}/runs` emits `aeris/investigation.requested` to Inngest, the registered `run_investigation` worker executes the LangGraph graph using `AsyncPostgresSaver`, publishes streaming events to Redis channels (`aeris:run:<run_id>`), and enables automatic resumption from the latest Postgres checkpoint upon failure.

**Tech Stack:** FastAPI, LangGraph (`AsyncPostgresSaver`, `langgraph-checkpoint-postgres`), Inngest SDK (`inngest.fast_api.serve`), Redis Pub/Sub (`redis[hiredis]`), PostgreSQL/PostGIS.

---

### Task 1: Postgres Checkpointer Migration (`backend/app/services/pipeline/checkpointer.py`)

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/services/pipeline/checkpointer.py`
- Test: `backend/tests/integration/test_postgres_checkpointer.py`

**Step 1: Write the failing test**
Create `backend/tests/integration/test_postgres_checkpointer.py` asserting:
- `open_checkpointer()` yields a checkpointer backed by Postgres.
- `await checkpointer.setup()` creates `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` tables in Postgres.
- State written to a thread can be read back using `read_thread_state()`.

**Step 2: Run test to verify it fails**
Run: `uv run pytest backend/tests/integration/test_postgres_checkpointer.py`
Expected: FAIL (missing dependency or checkpointer still opens SQLite)

**Step 3: Write minimal implementation**
1. Add `langgraph-checkpoint-postgres>=3.1.2` and `psycopg[binary,pool]>=3.2` to `backend/pyproject.toml` and sync via `uv sync`.
2. Update `open_checkpointer()` in `checkpointer.py` to use `AsyncPostgresSaver.from_conn_string(settings.database_url)`.
3. Update `read_state_for_step()` to query the Postgres checkpointer.

**Step 4: Run test to verify it passes**
Run: `uv run pytest backend/tests/integration/test_postgres_checkpointer.py`
Expected: PASS

**Step 5: Verify working tree hygiene**
Run: `git status` (Keep all changes uncommitted per project rules)

---

### Task 2: Inngest Event Constants & Redis Pub/Sub Stream Bridge

**Files:**
- Modify: `backend/app/constants/tasks.py`
- Create: `backend/app/services/sessions/redis_stream.py`
- Test: `backend/tests/unit/test_redis_stream.py`

**Step 1: Write the failing test**
Create `backend/tests/unit/test_redis_stream.py`:
- Test `RedisEventPublisher` publishes JSON-serialized `AnalysisStreamEvent` models to `aeris:run:<run_id>`.
- Test `redis_event_subscriber` receives events asynchronously until terminal event (`run-complete` or `run-error`).

**Step 2: Run test to verify it fails**
Run: `uv run pytest backend/tests/unit/test_redis_stream.py`
Expected: FAIL (`redis_stream.py` does not exist)

**Step 3: Write minimal implementation**
1. Add `INVESTIGATION_REQUESTED = "aeris/investigation.requested"` and `SCENE_INGEST_REQUESTED = "aeris/scene.ingest_requested"` to `EventName` in `tasks.py`.
2. Implement `RedisEventPublisher` and `redis_event_subscriber` in `backend/app/services/sessions/redis_stream.py`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest backend/tests/unit/test_redis_stream.py`
Expected: PASS

**Step 5: Verify working tree hygiene**
Run: `git status`

---

### Task 3: Inngest Functions & FastAPI Serving

**Files:**
- Create: `backend/app/inngest/__init__.py`
- Create: `backend/app/inngest/functions/__init__.py`
- Create: `backend/app/inngest/functions/run_investigation.py`
- Create: `backend/app/inngest/functions/ingest_scene.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/investigations/run_service.py`
- Test: `backend/tests/integration/inngest/test_inngest_serve.py`

**Step 1: Write the failing test**
Create `backend/tests/integration/inngest/test_inngest_serve.py`:
- Asserts `GET /api/inngest` returns function definitions (`run-investigation`, `ingest-scene`).
- Asserts `POST /api/inngest` handles introspect and function sync.

**Step 2: Run test to verify it fails**
Run: `uv run pytest backend/tests/integration/inngest/test_inngest_serve.py`
Expected: FAIL (`/api/inngest` not mounted)

**Step 3: Write minimal implementation**
1. Implement `run_investigation.py` with `@inngest_client.create_function(...)`.
2. Implement `ingest_scene.py`.
3. In `backend/app/main.py`, mount `inngest.fast_api.serve(app, client=get_client(), functions=INNGEST_FUNCTIONS)`.
4. In `backend/app/services/investigations/run_service.py`, dispatch `EventName.INVESTIGATION_REQUESTED` and return `redis_event_subscriber(run_id)`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest backend/tests/integration/inngest/test_inngest_serve.py`
Expected: PASS

**Step 5: Verify working tree hygiene**
Run: `git status`

---

### Task 4: Inngest Retry & Checkpoint Resumption (The Gate Test)

**Files:**
- Create: `backend/tests/integration/inngest/test_run_investigation.py`

**Step 1: Write the failing test**
Create `backend/tests/integration/inngest/test_run_investigation.py`:
- Simulates a run where step 2 fails with an intentional exception.
- Triggers Inngest retry.
- Asserts the retried execution restores state from Postgres checkpointer and executes step 2 without re-running step 1.
- Verifies the final journal is identical to an undisturbed run.

**Step 2: Run test to verify it passes**
Run: `uv run pytest backend/tests/integration/inngest/test_run_investigation.py`
Expected: PASS

**Step 3: Verify full backend suite**
Run: `uv run pytest backend/tests/integration/api backend/tests/integration/inngest`
Expected: All tests pass.

---

### Task 5: End-to-End Live Verification & Walkthrough Update

**Files:**
- Modify: `walkthrough.md`
- Modify: `task.md`

**Step 1: Verify live servers**
- Backend uvicorn running with Inngest serve handler on `http://127.0.0.1:8000/api/inngest`.
- Inngest dev server dashboard at `http://localhost:8288` shows registered functions.
- Trigger an investigation run via `POST /api/v1/investigations/{id}/runs` and verify live SSE reception from Redis Pub/Sub.

**Step 2: Update documentation**
- Record all test outputs and architecture in `walkthrough.md`.
- Mark all items complete in `task.md`.
