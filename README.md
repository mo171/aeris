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
With the stack green, ask a question over a scene directory, a GeoTIFF or a plain picture. The router
names the graph (Phase 1.10: `single-image` or `temporal`), the run streams its S1–S19 trace, writes its
figures under `backend/runs/<run_id>/figures/`, prints the claims and what each rests on, and leaves
`provenance.json` and `evidence-graph.json` beside the journal:

```bash
uv run aeris analyse --scene notebooks/01_remote_sensing/data --query "unhealthy vegetation" --level L2A
```

```bash
uv run aeris analyse --scene backend/data/datasets/dota8/dota8/images/val/P1470__1024__3296___1648.jpg --query "count the basketball courts"
```

```bash
uv run aeris analyse --scene backend/data/datasets/sentinel2-l2a/mumbai_gate --level L2A --query "segment the buildings and give me their area"
```

```bash
uv run aeris analyse --scene backend/data/datasets/levir-cd/test/B/0271.png --before backend/data/datasets/levir-cd/test/A/0271.png --gsd 0.5 --registered --query "what changed between the two images"
```

The two Sentinel-2 dates over Mumbai are fetched as windows over the box - ten megabytes each, on the tile's
own grid, with the cloud-mask layer the older subset lacks:

```bash
uv run aeris dataset fetch sentinel2-l2a --bbox 72.8,19.0,72.9,19.1 --from 2026-03-22 --to 2026-03-23 --clip --name mumbai_gate_2026
```

`--level L2A` is needed for a subset whose files carry no product name. A picture with no georeference
gets figures and pixel claims and nothing on the globe; `--gsd 0.5` declares its pixel size, and every
hectare computed from it is labelled *nominal*. `--before` adds the earlier date of a pair; S9 measures
the co-registration and refuses a pair it cannot vouch for, and `--registered` is the operator's word that
the source already aligned it (recorded as a declaration, beside the measurement). A run stopped partway
resumes from its checkpoint: `uv run aeris run --resume <run_id> --graph single-image --intent DETECT`.

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

### 10. Query understanding and routing (`aeris route`)
Phase 1.8 puts a router in front of every question: cues and a kNN over a labelled bank choose the intent,
a table chooses the specialist and the graph, and four validations refuse with reasons. A count goes to the
detector, never the VLM. The first call downloads a 130 MB sentence encoder into `backend/data/models/`.

```bash
uv run aeris route "how many ships are in the harbour"
```

```bash
uv run aeris route "how many cars are parked here" --gsd 10
```

```bash
uv run aeris route --evaluate
```

The first prints DETECT, `dota-detector`, the objects; the second refuses - a 4.5 m car spans fewer than
8 pixels at 10 m; the third prints the gate tables (0.991 held-out, 1.000 fresh; rules alone and kNN alone
beside it; compound requests 1.000 exact on 50 after tuning, 0.50-0.67 untouched). A spoken request with
several questions becomes a plan of steps, answered in order:

```bash
uv run aeris route "hey aeris, show me the water bodies, then map the unhealthy vegetation and give me its area, and finally count the cars on the roads" --gsd 10
```
 `aeris ask` and `aeris analyse` run the same router before anything loads; `aeris ask
--force-vlm` bypasses it so the two answers can be compared.

### 11. The agent (`aeris agent`)
Phase 1.9 puts a language model behind the router, never in front of it: it arbitrates an uncertain routing
margin, writes the plan's prose (the steps are the router's), phrases the answer under the same numeral
guard as the VLM, and names which claim to spotlight (checked). Set `LLM_PROVIDER=openai` and
`OPENAI_API_KEY` in `backend/.env` (`aeris doctor` shows the model row); `LLM_PROVIDER=none` runs the same
agent with templates.

```bash
uv run aeris agent "how many basketball courts are there, and does it look like a school?" --image backend/data/datasets/dota8/dota8/images/val/P1470__1024__3296___1648.jpg
```

```bash
uv run aeris agent "map the water bodies and give me their area, then count the cars on the roads" --scene backend/data/datasets/sentinel2-l2a/mumbai_gate --level L2A --yes
```

```bash
uv run aeris agent "what changed between the two dates, then map the water and give me its area" --scene backend/data/datasets/sentinel2-l2a/mumbai_gate_2026 --before backend/data/datasets/sentinel2-l2a/mumbai_gate_2023 --level L2A --yes
```

From 1.10 every step the agent runs is a graph run - the same journal, figures, provenance record and
checkpoint `aeris analyse` writes - so a count, a land-cover map, a change map and a perception question
all leave the same kind of record.

The plan is shown and paused on; enter runs it, step ids keep only those, `--skip step-2` strikes one out
without a prompt, `--thread <id>` continues a conversation so "what did you find earlier" recalls it. Every
request writes `backend/runs/<request_id>/agent/` - `record.json`, `answer.txt` and a `README.md` saying
what to check - beside the graph runs it made.

### 12. The vision-language model (`aeris ask`)
Phase 1.7 serves Qwen3-VL (2B by default, `VLM_SIZE=4b` on an 8 GB card) 4-bit through the fleet, and puts
the constrained answer generator into S16: the model phrases the claims, and any number it writes that no
specialist computed rejects the phrasing. The first call downloads the 4 GB base into `backend/data/models/`.

```bash
uv run aeris ask --image backend/data/datasets/dota8/dota8/images/val/P1470__1024__3296___1648.jpg --question "How many basketball courts are visible?"
```

Routed: the detector answers **3** (the label file's count); with `--force-vlm` the VLM says 2. A question
the detector cannot count ("how many buildings") is refused by name and the VLM says only whether they are
present, labelled as not a count.

```bash
uv run aeris ask --image before.png --image after.png --question "What changed between the two dates?"
```

Without an adapter the version reads `qwen3-vl-2b-unadapted`. The remote-sensing adaptation - a LoRA
trained on BigEarthNet.txt and RSVQA-LR on a Kaggle T4 - is `backend/notebooks/08_vlm_finetuning/`
(read its README first); set `VLM_ADAPTER_REPOSITORY` to the pushed adapter and the fleet loads it.
