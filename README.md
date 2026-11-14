# Mars Map

React (Vite) frontend + FastAPI backend.

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then set JWT_SECRET_KEY: python -c "import secrets; print(secrets.token_urlsafe(32))"
uvicorn main:app --reload --port 8000 --env-file .env
```

The backend refuses to start without `JWT_SECRET_KEY`. Users are stored in SQLite at `data/app.db` (created on first start;
override with `MARS_DATABASE_URL`).

Auth: `POST /api/auth/register` (JSON: `email`, `password`, `body_mass_kg`, `birth_year`), `POST /api/auth/login`
(form fields `username` = email, `password`; returns a Bearer token), `GET`/`PATCH /api/users/me` (needs
`Authorization: Bearer <token>`). In http://localhost:8000/docs use the "Authorize" button to log in.

API docs: http://localhost:8000/docs

Layer endpoints: `/api/get-layer-one` (imagery sources), `/api/get-layer-two` (relief; `/point?lon=&lat=`, `/walkability.png`),
`/api/get-layer-three` (points of interest, `?category=`), `/api/get-layer-four?season=winter` (dust-storm risk),
`/api/tiles/{source}/{z}/{row}/{col}`. A layer whose data is missing answers 503 with the script to run.

Tests (pytest is in `requirements.txt`; tests mirror the code in `tests/<module>/`, real-data checks skip when `data/` is missing):

```bash
pytest
```

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
python scripts/build_weather/build_weather.py   # Layer 4 dust-storm grid -> data/derived/weather/
```

Script tests: `pytest scripts/build_weather/tests`

Project context for humans and agents: `context/skills/mars-mvp-data/SKILL.md`.
