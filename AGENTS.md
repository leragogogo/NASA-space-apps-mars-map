# Agent notes

## Project
Interactive Mars map for astronauts and mission planners: 4 stacked layers (base imagery, relief/walkability, points of interest, seasonal dust-storm risk) for a single demo area (East Melas / Coprates Chasma, Valles Marineris), plus a route planner over a master graph that combines all layers.

## Read first
- Full context (requirements, exact datasets, endpoints, weather confidence rules, architecture decisions, repo structure): `context/skills/mars-mvp-data/SKILL.md`. `.claude/skills` is a symlink to `context/skills`.
- Layer ingestion contract (what each layer module must output, shared grid, fixtures, parallel work packages): `context/skills/mars-mvp-data/references/layer-ingestion.md`.
- Per-profile edge cost and resource model (oxygen, CO2, water, energy): `context/skills/mars-mvp-data/references/edge-cost-model.md`.
- Reference analysis scripts (not needed to re-run): `context/skills/mars-mvp-data/scripts/`.
- `context/` is deliberately agent-agnostic (not Claude-specific); `.claude/skills` is a symlink to it so Claude Code still discovers the skill. Other agents read this file and follow the links above.

## Architecture rules
- **The frontend consumes ONLY our FastAPI backend**, never NASA/Harvard servers directly. The backend owns the response format of every layer (tiles, GeoJSON, route) so different sources look uniform to the client.
- **Static local data (MVP):** `scripts/download_data.py` is a one-off setup step -> `data/raw/` (gitignored) -> backend layer getters + master graph -> API -> React. The backend serves every layer directly from the downloaded files. **No external API calls, proxy or cache at runtime** (backend or frontend). Don't download datasets by hand; to get more data, extend the download script and re-run it.
- **Backend:** FastAPI. Four independent layer endpoints + one route endpoint. Each layer has an ingestion module (`app/layers/<layer>/`) that outputs normalised data on a shared `GridSpec`; the graph builder consumes only that output, never `data/raw/` directly.
- **One master graph, two profiles (`astronaut`, `car`).** Same topology; every directed edge stores per profile a routing `cost` plus resource use (`time_s`, `o2_g`, `co2_g`, `water_g`, `energy_wh`) as struct-of-arrays (not a dict per edge). Graph and costs are flat NumPy arrays; SciPy (`csgraph.dijkstra`) for paths, OR-Tools for stop order. Season is a request parameter, not part of the graph or the cost; weather only produces warnings. Slope shown to users and slope used by the router must come from the same array.
- **Parallel work:** code against the contracts and the synthetic fixtures (`app/layers/fakes.py`), not against another module's real implementation. Changing a contract means editing the reference doc in the same PR.
- **Frontend:** React + Vite + Leaflet (`react-leaflet`) with `L.CRS.EPSG4326` (Mars tiles are plain lat/lon, not Web Mercator).
- **Data-sufficiency rule (mandatory):** where a layer frame lacks enough data, the UI must say so explicitly; approximate values must be labelled as approximate. Render the weather `message` field verbatim.

## Structure
```
context/skills/mars-mvp-data/   project skill + reference scripts
scripts/download_data.py        data pipeline
scripts/weather/                MDAD -> data/raw/weather/ (Layer 4 grid), run by download_data.py, with tests/
data/raw/                       downloaded data (gitignored)
backend/app/                    api/routes, core, schemas, layers/{base_imagery,relief,poi,weather} (ingest + service each), tiles, graph, routing, auth, db
backend/tests/
frontend/src/                   api, components, features/{map,layers,route}, hooks, config, utils
```
**Shared contracts already exist (step 0, tested):** `app/core/{resources,profiles}.py`, `app/layers/{contracts,fakes,validate}.py`, `app/layers/relief/slope.py`, `app/graph/contracts.py` (`GraphData`), `app/routing/contracts.py`, `app/schemas/{route,layers}.py`. Import from these; do not redefine them. **Routing engine (package G) is done:** `app/routing/{graph,matrix,solver,assemble,service}.py` (flat NumPy arrays plus SciPy CSR matrices and `scipy.sparse.csgraph.dijkstra`, no per-edge Python objects), entry point `plan_route` (SKILL.md section 10, "Implementation"). **Graph (work package F) is built and tested:** `app/graph/{edges,geometry,attrs,nodes,build,store,loader,cli,fakes}.py`; real per-profile formulas are in `app/routing/profiles/` (all parameters still placeholders). Build the real graph with `cd backend && python -m app.graph` (inputs from `app/layers/inputs/load.py: load_all`, on the native 200 m grid by default, `Settings.grid_coarsen`; writes `data/graph/graph.npz`, about 40 s and 490 MB), or a dev graph with `--fake`. At startup `app/graph/loader.py: load_routing_context(settings)` loads it into a `RoutingContext` (the `RoutingGraph` plus a KD-tree for snapping). The API controllers exist (`app/api/routes/{layers,tiles,route}.py`, `app/routing/{request,snap}.py`); `POST /api/route` answers 503 until `graph.npz` exists. End-to-end tests: `backend/tests/integration/test_graph_integration.py` (layers -> graph -> `plan_route`) and `test_pipeline_api.py` (data -> `python -m app.graph` -> app startup -> `POST /api/route`, cross-checked against the layer endpoints; the real-data part builds the native graph, about a minute). Everything else is still an empty placeholder (`.gitkeep`) beyond the Vite and FastAPI starters.
The four layers follow `references/layer-ingestion.md`: `ingest.py` + `service.py` per layer (the service classes are still called `...Getter`), endpoints are the implemented `/api/get-layer-*` paths (listed in the reference, section 6), POI features carry `kind` and `category`, weather data lives in `data/raw/weather/` (computed by `scripts/weather/` through `download_data.py --only weather`). Auth is done: JWT + SQLite users with body mass and birth year (`app/auth/`, `app/db/`, `/api/auth/*`, `/api/users/me`; SKILL.md section 10a). Still missing: the frontend. Design notes of the earlier getters: `docs/superpowers/specs/2026-11-14-layer-getters-design.md` (its section 7a lists differences that are now settled).

## Commands
- Data: `pip install -r scripts/requirements.txt && python scripts/download_data.py` (`--only dem|tiles|pois|mdad|weather`, `--max-zoom N`, `--force`). The `weather` step computes the static weather layer into `data/raw/weather/`. Pipeline tests: `cd scripts && pytest`.
- Backend tests: `cd backend && pip install -r requirements.txt && pytest`.
- Backend: see README (uvicorn on :8000; needs `JWT_SECRET_KEY`, copy `backend/.env.example` to `backend/.env`). Frontend: see README (Vite on :5173, proxies `/api/*`).

## Development rules (all agents; full text in SKILL.md section 11)
- **Whenever you create new code, put it in a subdirectory named after the module, and create that directory if it does not exist.** Backend: `backend/app/<module>/` (with `__init__.py`). Frontend: `frontend/src/<area>/<Module>/`. Scripts: `scripts/<module>/`. No loose files at a package root.
- **Add tests for all code you write, in the same change.** Backend: pytest, mirroring the module path in `backend/tests/<module>/test_<file>.py`, run with `cd backend && pytest`. Frontend: Vitest with `<Name>.test.jsx` next to the source (add the dev dependencies and a `test` script when you add the first one).
- Tests are offline and deterministic: use the fixtures in `app/layers/fakes.py` and tiny hand-built graphs; tests needing the real `data/raw/` files skip when it is missing.
- Run the tests before finishing and report failures honestly.
- Update the matching doc (`references/*.md`, SKILL.md, this file) in the same change when you alter a contract, formula, endpoint or folder.
