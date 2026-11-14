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
- **One master graph, two profiles (`astronaut`, `car`).** Same topology; every directed edge stores per profile a routing `cost` plus resource use (`time_s`, `o2_g`, `co2_g`, `water_g`, `energy_wh`) as struct-of-arrays (not a dict per edge). rustworkx for paths, OR-Tools for stop order. Season is a request parameter, not part of the graph or the cost; weather only produces warnings. Slope shown to users and slope used by the router must come from the same array.
- **Parallel work:** code against the contracts and the synthetic fixtures (`app/layers/fakes.py`), not against another module's real implementation. Changing a contract means editing the reference doc in the same PR.
- **Frontend:** React + Vite + Leaflet (`react-leaflet`) with `L.CRS.EPSG4326` (Mars tiles are plain lat/lon, not Web Mercator).
- **Data-sufficiency rule (mandatory):** where a layer frame lacks enough data, the UI must say so explicitly; approximate values must be labelled as approximate. Render the weather `message` field verbatim.

## Structure
```
context/skills/mars-mvp-data/   project skill + reference scripts
scripts/download_data.py        data pipeline
data/raw/                       downloaded data (gitignored)
backend/app/                    api/routes, core, schemas, layers/{base_imagery,relief,poi,weather} (ingest + service each), tiles, graph, routing
backend/tests/
frontend/src/                   api, components, features/{map,layers,route}, hooks, config, utils
```
**Shared contracts already exist (step 0, tested, 67 tests):** `app/core/{resources,profiles}.py`, `app/layers/{contracts,fakes,validate}.py`, `app/layers/relief/slope.py`, `app/graph/contracts.py` (`GraphData`), `app/routing/contracts.py`, `app/schemas/{route,layers}.py`. Import from these; do not redefine them. Everything else is still an empty placeholder (`.gitkeep`) beyond the Vite and FastAPI starters.

## Commands
- Data: `pip install -r scripts/requirements.txt && python scripts/download_data.py` (`--only dem|tiles|pois|mdad`, `--max-zoom N`, `--force`).
- Backend: see README (uvicorn on :8000). Frontend: see README (Vite on :5173, proxies `/api/*`).

## Development rules (all agents; full text in SKILL.md section 11)
- **Whenever you create new code, put it in a subdirectory named after the module, and create that directory if it does not exist.** Backend: `backend/app/<module>/` (with `__init__.py`). Frontend: `frontend/src/<area>/<Module>/`. Scripts: `scripts/<module>/`. No loose files at a package root.
- **Add tests for all code you write, in the same change.** Backend: pytest, mirroring the module path in `backend/tests/<module>/test_<file>.py`, run with `cd backend && pytest`. Frontend: Vitest with `<Name>.test.jsx` next to the source (add the dev dependencies and a `test` script when you add the first one).
- Tests are offline and deterministic: use the fixtures in `app/layers/fakes.py` and tiny hand-built graphs; tests needing the real `data/raw/` files skip when it is missing.
- Run the tests before finishing and report failures honestly.
- Update the matching doc (`references/*.md`, SKILL.md, this file) in the same change when you alter a contract, formula, endpoint or folder.
