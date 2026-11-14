# Agent notes

## Project
Interactive Mars map for astronauts and mission planners: 4 stacked layers (base imagery, relief/walkability, points of interest, seasonal dust-storm risk) for a single demo area (East Melas / Coprates Chasma, Valles Marineris), plus a route planner over a master graph that combines all layers.

## Read first
- Full context (requirements, exact datasets, endpoints, weather confidence rules, architecture decisions, repo structure): `context/skills/mars-mvp-data/SKILL.md`. `.claude/skills` is a symlink to `context/skills`.
- Reference analysis scripts (not needed to re-run): `context/skills/mars-mvp-data/scripts/`.

## Architecture rules
- **The frontend consumes ONLY our FastAPI backend**, never NASA/Harvard servers directly. The backend owns the response format of every layer (tiles, GeoJSON, route) so different sources look uniform to the client.
- **Static local data (MVP):** `scripts/download_data.py` is a one-off setup step -> `data/raw/` (gitignored) -> backend layer getters + master graph -> API -> React. The backend serves every layer directly from the downloaded files. **No external API calls, proxy or cache at runtime** (backend or frontend). Don't download datasets by hand; to get more data, extend the download script and re-run it.
- **Backend:** FastAPI. Four independent layer endpoints + one route endpoint. A routing engine runs over a master graph whose nodes hold data from all layers; layer getters feed the graph. Season is a query parameter, not part of the graph. Slope shown to users and slope used by the router must come from the same array.
- **Frontend:** React + Vite + Leaflet (`react-leaflet`) with `L.CRS.EPSG4326` (Mars tiles are plain lat/lon, not Web Mercator).
- **Data-sufficiency rule (mandatory):** where a layer frame lacks enough data, the UI must say so explicitly; approximate values must be labelled as approximate. Render the weather `message` field verbatim.

## Structure
```
context/skills/mars-mvp-data/   project skill + reference scripts
scripts/download_data.py        data pipeline
data/raw/                       downloaded data (gitignored)
backend/app/                    api/routes, core, schemas, layers/{base_imagery,relief,poi,weather}, tiles, graph, routing
backend/tests/
frontend/src/                   api, components, features/{map,layers,route}, hooks, config, utils
```
Most new folders are empty placeholders (`.gitkeep`); there is no application code yet beyond the Vite and FastAPI starters.

## Commands
- Data: `pip install -r scripts/requirements.txt && python scripts/download_data.py` (`--only dem|tiles|pois|mdad`, `--max-zoom N`, `--force`).
- Backend: see README (uvicorn on :8000). Frontend: see README (Vite on :5173, proxies `/api/*`).
