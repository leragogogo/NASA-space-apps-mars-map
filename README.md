# Mars Map
Live app: [https://mars-map.design](https://mars-map.design)

Mars Map is an interactive planning map for astronauts and mission planners. It covers East Melas / Coprates Chasma in Valles Marineris and stacks four layers built from open NASA and Harvard Dataverse data: high-resolution imagery, terrain walkability from slope, scientific points of interest, and seasonal dust-storm risk. Users can plan a route through several destinations on foot or by rover. For each route, they get an estimate of travel time, oxygen, CO₂, water, and energy, personalised to their body mass. Wherever the data is too thin to be reliable, the map says so. 

The map layers are available without an account. To use the route planner you need to sign up first, because it uses your body mass to estimate the oxygen, CO₂ and water each route needs. The application is not optimized for phones.

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

Route: `POST /api/route` (login required). Minimal body `{"start": {"lon": .., "lat": ..}, "end": {"lon": .., "lat": ..}}`; `profile` is `auto` (default), `astronaut` or `car`; add `destinations` for a multi-stop route (visited in the order given). The walker's oxygen and water estimates use the logged-in user's body mass. The response's `mode` says which profile was chosen and why.

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

App: http://localhost:5173 — requests to `/api/*` are proxied to the backend (`MARS_API_URL=http://localhost:8001 npm run dev`
to use another backend port).

Tests and lint: `npm test`, `npm run lint`. Details: `frontend/README.md`.

## Data

The datasets are not stored in git (`data/` is gitignored). After cloning, run this once, before starting the backend:

```bash
pip install -r scripts/requirements.txt
python scripts/download_data.py        # DEM, map tiles, POI vectors, MDAD storm data and the Layer 4 dust-storm grid -> data/raw/
```

Script tests: `cd scripts && pytest`

Project context for humans and agents: `context/skills/mars-mvp-data/SKILL.md`.
