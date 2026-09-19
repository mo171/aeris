# Phase 2.6 Tiles & TiTiler Service Promotion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Promote TiTiler to a supported AERIS service by providing first-class `/api/v1/tiles` endpoints for TileJSON, XYZ raster tiles with server-side band selection, contrast stretching, and color mapping, ensuring the browser never performs band math.

**Architecture:** A dedicated FastAPI router (`app/routes/tiles.py`) and controller (`app/controllers/tiles_controller.py`) that resolves scene COGs from PostgreSQL/MinIO, communicates asynchronously with the TiTiler container via `httpx.AsyncClient`, translates server-side presets (`true_color`, `false_color_nir`, `ndvi`, `ndwi`, `sar_vv`), and streams reprojected WebMercatorQuad PNG tiles with alpha transparency to the Cesium frontend.

**Tech Stack:** FastAPI, TiTiler (`ghcr.io/developmentseed/titiler:0.24.0`), `httpx`, Pillow, PostgreSQL/PostGIS, MinIO.

---

### Task 1: Preset Vocabulary & Server-Side Band Parameter Resolver (`backend/app/constants/presets.py`)

**Files:**
- Create: `backend/app/constants/presets.py`
- Create: `backend/tests/unit/test_tile_presets.py`

**Step 1: Write the failing unit test**
Create `backend/tests/unit/test_tile_presets.py` verifying:
- Presets: `true_color`, `false_color_nir`, `ndvi`, `ndwi`, `sar_vv`.
- Resolves band selection (`bidx`), contrast stretch (`rescale`), colormaps (`colormap_name`), and expressions (`expression`).
- Rejects invalid presets with clear validation errors.

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/unit/test_tile_presets.py`
Expected: FAIL (module does not exist)

**Step 3: Write minimal implementation**
Implement `backend/app/constants/presets.py` with `BandPreset` enum and `resolve_preset_rendering(preset, band_count, modality)`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/unit/test_tile_presets.py`
Expected: PASS

**Step 5: Verify working tree hygiene**
Run: `git status --short` (Zero git commits rule).

---

### Task 2: Tiles Controller & TiTiler Proxy Client (`backend/app/controllers/tiles_controller.py`)

**Files:**
- Create: `backend/app/controllers/tiles_controller.py`
- Modify: `backend/app/lib/tiles.py`
- Test: `backend/tests/integration/api/test_tiles_controller.py`

**Step 1: Write the failing test**
Create `backend/tests/integration/api/test_tiles_controller.py`:
- Test `get_tilejson(scene_id)` queries TiTiler, rewrites tiles array to `/api/v1/tiles/{scene_id}/{z}/{x}/{y}.png`, and preserves bounds/minzoom/maxzoom.
- Test `get_tile_bytes(scene_id, z, x, y)` streams valid PNG bytes with alpha transparency.
- Test non-existent scene returns `ResourceNotFoundError` (404).

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/integration/api/test_tiles_controller.py`
Expected: FAIL

**Step 3: Write minimal implementation**
Implement `tiles_controller.py`:
- Check scene in DB (`DbScene.cog_object_key` or `raw_object_key`).
- Use `httpx.AsyncClient` with connection pooling to talk to `settings.tile_server` (`http://127.0.0.1:8080`).
- Implement `get_scene_tilejson()` and `render_scene_tile()`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/integration/api/test_tiles_controller.py`
Expected: PASS

**Step 5: Verify working tree hygiene**
Run: `git status --short`

---

### Task 3: FastAPI Routes & App Registration (`backend/app/routes/tiles.py`)

**Files:**
- Create: `backend/app/routes/tiles.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/api/test_tiles.py`

**Step 1: Write the failing test**
Create `backend/tests/integration/api/test_tiles.py`:
- `GET /api/v1/tiles/{scene_id}/tilejson.json` returns HTTP 200 and schema-valid TileJSON.
- `GET /api/v1/tiles/{scene_id}/11/1465/855.png` returns HTTP 200 and `image/png`.
- `GET /api/v1/tiles/{scene_id}/11/1465/855.png?preset=ndvi` returns HTTP 200 with server-side colormapped PNG.
- Invalid scene ID returns HTTP 404.

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/integration/api/test_tiles.py`
Expected: FAIL (route not registered)

**Step 3: Write minimal implementation**
- Implement `backend/app/routes/tiles.py` declaring endpoints.
- Mount `app.include_router(tiles.router, prefix="/api/v1")` in `backend/app/main.py`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/integration/api/test_tiles.py`
Expected: PASS

**Step 5: Verify working tree hygiene**
Run: `git status --short`

---

### Task 4: Investigation & Timeline Integration Verification

**Files:**
- Modify: `backend/app/services/investigations/investigation_service.py`
- Test: `backend/tests/integration/api/test_investigations.py`

**Step 1: Write test asserting AcquisitionTiles**
Verify that `GET /api/v1/investigations/{id}` returns `acquisitions` with valid `tiles.urlTemplate` that can be queried and returns HTTP 200.

**Step 2: Run test**
Run: `uv run pytest tests/integration/api/test_investigations.py`
Expected: PASS

---

### Task 5: End-to-End Live Verification & Documentation Update

**Files:**
- Modify: `walkthrough.md`
- Modify: `task.md`

**Step 1: Live Server Verification**
- Probe `/api/v1/tiles/{scene_id}/tilejson.json` against the live backend (`http://127.0.0.1:8000`).
- Probe `/api/v1/tiles/{scene_id}/11/1465/855.png` and verify tile image headers and alpha channel.
- Verify Cesium frontend tile loading.

**Step 2: Update documentation**
- Update `walkthrough.md` and `task.md`.
