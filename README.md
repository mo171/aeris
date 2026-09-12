# SatQuery AI (AERIS)

AERIS is an agentic Earth-observation intelligence backend that processes satellite imagery, runs specialist AI models, and uses a Vision-Language Model to answer operator queries.

## Quick Start (Backend Setup)

Follow these steps to get the backend running on a machine that has never run this project before.

### 1. Install `uv`
This project uses `uv` for lightning-fast Python dependency management.
- **Windows (PowerShell):** `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **macOS/Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 2. Install Dependencies (`pyproject.toml`)
Navigate to the `backend` directory. Use `uv sync` to automatically create a virtual environment and install all required dependencies exactly as locked in the `uv.lock` file.

```bash
cd backend
uv sync
```

If downloading the Matplotlib wheel times out on a slower connection, increase uv's HTTP timeout for that shell and retry:

```powershell
$env:UV_HTTP_TIMEOUT = "120"
uv sync --refresh --refresh-package matplotlib
```

The lock file already selects a CPython 3.14 Windows wheel for Matplotlib, so no source build or dependency downgrade is needed.

### 3. Activate the Virtual Environment
You must activate the virtual environment so your terminal uses the correct Python instance:
- **Windows (PowerShell):** `.venv\Scripts\activate`
- **macOS/Linux (Bash):** `source .venv/bin/activate`

### 4. Set Up Environment Variables
Create your local `.env` file from the provided example template:
- **Windows (PowerShell):** `Copy-Item .env.example -Destination .env`
- **macOS/Linux (Bash):** `cp .env.example .env`

### 5. Start the Docker Infrastructure
The backend relies on four containerized services (PostgreSQL/PostGIS, Redis, MinIO, and Inngest). 
Make sure Docker Desktop is installed and running, then start the services in the background:

```bash
docker compose up -d
```

### 6. Initialize the Database Schema
Run the database migrations to build the tables in your newly created Postgres container:

```bash
uv run alembic upgrade head
```

### 7. Verify the System (`aeris doctor`)
Finally, run the diagnostic tool. It will check every dependency (database, cache, object storage, and event bus). 

```bash
uv run aeris doctor
```
If the command outputs an `ok` status for all services, your backend is perfectly configured and ready to use!

### 8. Run an analysis (`aeris analyse`)
With the stack green, ask an index question over the bundled Sentinel-2 subset. The run streams its S7–S19
trace, writes three figures under `backend/runs/<run_id>/figures/`, prints the measured area and the claims
it rests on, and leaves `provenance.json` and `evidence-graph.json` beside the journal:

```bash
uv run aeris analyse --scene notebooks/01_remote_sensing/data --query "unhealthy vegetation" --level L2A
```

`--level L2A` is needed for that subset because its files carry no product name; a scene fetched with
`aeris dataset fetch` states its level in the path and does not need it. Other questions the phrase table
answers: `"vegetation"`, `"water"`, `"flood extent"`, `"built-up"`, or a bare index name such as `"ndwi"`.

---

## Local Database & GUI Connection Details

If you are connecting a GUI client (such as pgAdmin, DBeaver, TablePlus, or VSCode Database Client) to the local PostgreSQL database, use the following settings:

| Setting | Value to Enter | Notes |
| :--- | :--- | :--- |
| **Host** | `localhost` *(or `127.0.0.1`)* | Bound to localhost |
| **Port** | `5433` | Host port is `5433` (mapped from container port `5432` to avoid host collisions) |
| **User** | `aeris` | Application user |
| **Password** | `aeris_local_development` | Local development password |
| **Database** | `aeris` | Primary database name |


### 9. The specialist fleet (`aeris models`)
Phase 1.6 adds the first learned models. `uv sync` installs torch from the CUDA 13.0 index (about 3 GB);
without a CUDA device everything still runs, on the CPU, and reports itself `degraded`. Checkpoints are
fetched from the Hugging Face Hub into `backend/data/models/` on first use.

```bash
uv run aeris models status
```

```bash
uv run aeris models warm changeformer segformer-landcover --budget 700
```

```bash
uv run aeris dataset fetch levir-cd --split test
```

```bash
uv run aeris models evaluate --limit 256
```

The second command loads two models within a budget that fits one, so you watch the first go
`warming → online` and then get evicted for the second. The last two fetch LEVIR-CD's 256-crop test split
(73 MB) and score the change detector on it: change-class F1 and IoU, and the predicted and true areas.

The oriented-object detector (YOLO11s-OBB on DOTA, **AGPL-3.0** - see `constants/licences.py`) has its own
smoke test on Ultralytics' eight-crop DOTA8 sample: fetch the archive, unpack it in place, then score.

```bash
uv run aeris dataset fetch dota8
```

```bash
uv run aeris models evaluate --model dota-detector
```
