# Phase 2.1 (Serving Read Endpoints) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish the FastAPI application shell and the foundational read endpoints for the AERIS frontend, strictly adhering to `bcontext/folder-archtecture.md`.

**Architecture:** A FastAPI application in `backend/app/main.py`. Routes go in `app/routes/` (declaration only) and delegate logic to `app/controllers/`. Exceptions and error handlers go in `app/lib/`. Constants go in `app/constants/`.

**Tech Stack:** FastAPI, Uvicorn, SQLAlchemy (Async), Redis.

---

### Task 1: FastAPI Shell & Health Endpoints

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/app/routes/health.py`
- Create: `backend/app/controllers/health_controller.py`
- Modify: `backend/app/lib/error_handler.py` (or `exceptions.py`)
- Create: `backend/tests/integration/api/test_health.py`

**Step 1: Write the failing test**
Create `backend/tests/integration/api/test_health.py` and write tests asserting `/health` returns `200 OK` and a payload matching the doctor check.

**Step 2: Run test to verify it fails**
Run: `uv run pytest backend/tests/integration/api/test_health.py`
Expected: FAIL (main app doesn't exist yet)

**Step 3: Write minimal implementation**
1. Implement `health_controller.py` containing the logic to check PostGIS, Redis, etc. (reuse `cli/doctor.py` logic if possible).
2. Implement `routes/health.py` mapping `/health` and `/ready` to the controller.
3. Update `lib/error_handler.py` (or `exceptions.py`) to map `AerisError` subclasses to FastAPI HTTP exception responses.
4. Implement `main.py` with FastAPI initialization, `config.CORS_ORIGINS` setup, lifespan context manager (DB/Redis), exception handler registration, and include the `health` router.

**Step 4: Run test to verify it passes**
Run: `uv run pytest backend/tests/integration/api/test_health.py`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/main.py backend/app/routes backend/app/controllers backend/app/lib backend/tests/integration/api/test_health.py
git commit -m "feat: initialize FastAPI shell and health endpoints with routes and controllers"
```

---

### Task 2: Imagery & Catalogue Endpoints

**Files:**
- Create: `backend/app/routes/imagery.py`
- Create: `backend/app/controllers/imagery_controller.py`
- Create: `backend/app/routes/catalogue.py` (if separate, or within imagery)
- Create: `backend/tests/integration/api/test_imagery.py`

**Step 1: Write the failing test**
Create `backend/tests/integration/api/test_imagery.py` asserting `GET /api/v1/imagery` returns paginated items and `GET /api/v1/imagery/{id}` returns a specific scene in camelCase.

**Step 2: Run test to verify it fails**
Run: `uv run pytest backend/tests/integration/api/test_imagery.py`
Expected: FAIL (404 Not Found)

**Step 3: Write minimal implementation**
1. Implement `imagery_controller.py` and `routes/imagery.py` using cursor pagination (limit, nextCursor).
2. Create `routes/catalogue.py` and a controller for `POST /api/v1/catalogue/search`.
3. Include routers in `main.py`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest backend/tests/integration/api/test_imagery.py`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/routes/imagery.py backend/app/controllers/imagery_controller.py backend/app/routes/catalogue.py backend/tests/integration/api/test_imagery.py
git commit -m "feat: add imagery and catalogue read endpoints via controllers"
```

---

### Task 3: Missions, Globe & Models Endpoints

**Files:**
- Create: `backend/app/routes/missions.py`
- Create: `backend/app/controllers/mission_controller.py`
- Create: `backend/app/routes/models.py`
- Create: `backend/app/controllers/model_controller.py`
- Create: `backend/tests/integration/api/test_read_endpoints.py`

**Step 1: Write the failing test**
Create tests for `/api/v1/missions`, `/api/v1/globe/markers`, and `/api/v1/models/status`.

**Step 2: Run test to verify it fails**
Run: `uv run pytest backend/tests/integration/api/test_read_endpoints.py`
Expected: FAIL

**Step 3: Write minimal implementation**
1. Implement missions controller and route.
2. Implement globe route (can be under missions or separate).
3. Implement model controller/route mapping to `ModelManager` status.
4. Include routers in `main.py`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest backend/tests/integration/api/test_read_endpoints.py`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/routes backend/app/controllers backend/tests/integration/api/test_read_endpoints.py
git commit -m "feat: add missions, globe, and models read endpoints"
```
