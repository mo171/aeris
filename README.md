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
