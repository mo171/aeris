# ScholarSync Frontend Architecture Context

---
# ATLUS — Backend Architecture & Engineering Standard

> This document is the authoritative backend architecture standard for ATLUS.
>
> Every human developer and AI coding agent working on the backend MUST follow
> the architecture, dependency rules, naming conventions, API contracts,
> scientific-computing boundaries, and infrastructure rules defined here.
>
> The goal is not maximum abstraction.
> The goal is a predictable, testable, scientifically correct, scalable system.

---

# 1. Project Overview

ATLUS is the intelligent mission-control and scientific computing backend
for LUNARSAFE.

The system combines:

- Lunar terrain processing
- DEM super-resolution
- Terrain analysis
- Hazard detection
- Landing-zone detection and ranking
- Lander trajectory propagation
- Monte Carlo simulation
- Dynamic-object tracking
- Mission risk analysis
- Real-time mission state
- Natural-language mission control through the ATLAS agent
- Deterministic engineering tools exposed to ATLAS

The backend MUST keep:

1. API concerns
2. Business/application logic
3. Scientific computation
4. Long-running computation
5. Agent orchestration
6. Data persistence
7. Infrastructure

as separate responsibilities.

---

# 2. Core Architectural Principle

ATLUS uses a layered architecture combined with domain-oriented
scientific pipelines.

The normal application flow is:

```text
Route
  ↓
Controller
  ↓
Service
  ↓
Helper / Domain Logic
  ↓
Model
  ↓
Database / Infrastructure


For scientific or long-running operations:
Route
  ↓
Controller
  ↓
Service
  ↓
Pipeline
  ↓
Domain Scientific Functions
  ↓
Worker
  ↓
Database / Object Storage
```

For ATLAS:
User
  ↓
ATLAS Agent
  ↓
Inngest Workflow
  ↓
Agent Tool
  ↓
Service / Pipeline
  ↓
Celery Worker (when computation is heavy)
  ↓
Scientific Engine
  ↓
Result
  ↓
ATLAS
  ↓
User
```

---


# ATLUS — Complete Backend Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend API | **Python + FastAPI** | Main REST API and backend service |
| API Validation | **Pydantic** | Request/response schemas and validation |
| API Documentation | **OpenAPI / Swagger** | Automatic API documentation |
| Async Agent Workflows | **Inngest** | ATLAS workflows, orchestration, retries, events |
| Heavy Background Jobs | **Celery** | ML inference, Monte Carlo, DEM processing, simulations |
| Message Broker | **Redis** | Celery task broker / fast transient state |
| Real-time Communication | **WebSockets** | Live mission/simulation updates to frontend |
| Database | **PostgreSQL** | Persistent application and mission data |
| Geospatial Database | **PostGIS** | Spatial regions, landing zones, trajectories, coordinates |
| ORM / DB Layer | **SQLAlchemy** | Python database access |
| Database Migrations | **Alembic** | Schema migrations |
| Scientific Computing | **NumPy** | Numerical computation |
| Scientific Computing | **SciPy** | Numerical methods, optimization, statistics |
| Geospatial Processing | **Rasterio** | DEM/raster reading and processing |
| Geospatial Processing | **GDAL** | Raster/geospatial transformations |
| ML Framework | **PyTorch** | Super-resolution and ML models |
| ML Utilities | **scikit-learn** | Metrics, preprocessing, classical ML |
| DEM / Terrain Engine | **Python + NumPy/SciPy/Rasterio** | Slope, roughness, curvature, relief |
| Super-Resolution | **PyTorch** | 5m → 1m DEM reconstruction |
| Hazard Engine | **Python** | Terrain hazard detection and scoring |
| LZ Engine | **Python + NumPy/SciPy** | Safe landing-zone detection and ranking |
| Physics Engine | **Python + SciPy** | Lander dynamics and trajectory propagation |
| Monte Carlo Engine | **NumPy + SciPy** | Uncertainty propagation and landing probability |
| Dynamic Object Tracking | **Python** | Object state propagation and closest approach |
| Risk Engine | **Python** | Static + dynamic + temporal mission risk |
| Agent / LLM Layer | **ATLAS** | Natural-language mission-control agent |
| Agent Tool Layer | **Python functions / APIs** | Deterministic engineering tools for ATLAS |
| Object Storage | **S3-compatible storage** | DEMs, imagery, rasters, model files, large outputs |
| Cache | **Redis** | Frequently accessed results / transient state |
| Task Monitoring | **Celery monitoring** | Background-job monitoring |
| Authentication | **JWT / OAuth2** | API authentication and authorization |
| Containerization | **Docker** | Package backend services and workers |
| Local Orchestration | **Docker Compose** | Run API, workers, DB, Redis, etc. |
| Testing | **Pytest** | Backend, scientific and simulation testing |
| API Testing | **HTTPX** | Async API integration testing |
| Logging | **Python logging / structured logging** | Backend and worker observability |
| Configuration | **Pydantic Settings + .env** | Environment/config management |

