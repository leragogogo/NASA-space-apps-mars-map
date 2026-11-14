# Mars Map

React (Vite) frontend + FastAPI backend.

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

## Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173 — requests to `/api/*` are proxied to the backend.

## Data

The datasets are not stored in git (`data/` is gitignored). After cloning, run this once, before starting the backend:

```bash
pip install -r scripts/requirements.txt
python scripts/download_data.py        # DEM, map tiles, POI vectors and MDAD storm data -> data/raw/
```

Project context for humans and agents: `context/skills/mars-mvp-data/SKILL.md`.
