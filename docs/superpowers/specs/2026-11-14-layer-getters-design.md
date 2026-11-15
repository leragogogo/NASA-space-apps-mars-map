# Layer getters + layer endpoints — design

Date: 2026-11-14 · Status: approved in discussion, awaiting spec review · Git: local changes only (no commits, no push)

## 1. Goal

Implement the "Layer Getter → Fetch requested layer" box of the architecture diagram: one getter per map layer that loads
the local datasets once, plus the four `/get-layer-*` endpoints that expose them to the frontend. The same getters are
the input for the master graph and routing engine, which are built later.

Sources of truth: `context/skills/mars-mvp-data/SKILL.md` (datasets, rules, architecture), `AGENTS.md`, the architecture
diagram (endpoint names), product scope v1.2 (five layer categories, data-transparency rules).

### Rules this design must keep
- **Local files only at runtime.** The backend reads `data/`; it never calls NASA, Harvard or any other service, and has no proxy or cache.
- **The frontend talks only to our backend.** The backend owns every response format.
- **Single source of truth for relief.** The slope the user sees and the slope routing uses come from the same array.
- **Data-sufficiency rule.** Approximate values are labelled; the weather `message` is passed through verbatim; "not enough data" is explicit.

### Out of scope
Master graph, routing engine, `/get-route`, frontend work, user accounts, oxygen/supplies estimate.

## 2. Approach

**One getter class per layer, built once at startup and held in a registry** (FastAPI lifespan → `app.state.layers`).
Endpoints are thin and only ask the right getter. Rejected alternatives: lazy per-endpoint functions (no common interface
for the graph, slow first request); pre-rendering everything to static files (point lookup and routing still need the
grid in memory).

## 3. Structure

```
backend/
  main.py                         app, CORS, lifespan builds the registry, includes routers
  requirements.txt                + numpy, tifffile, pillow, shapely, pytest, httpx
  app/core/config.py              Settings: data dir (env MARS_DATA_DIR, default <repo>/data), AOI, slope classes,
                                  risk colours, POI sample radius, tile source table
  app/layers/base.py              LayerGetter protocol, LayerUnavailable error
  app/layers/registry.py          builds the four getters; a getter that fails to load is stored as unavailable(reason)
  app/layers/base_imagery/getter.py
  app/layers/relief/getter.py     + slope.py (slope + classification), render.py (walkability PNG)
  app/layers/poi/getter.py        + normalize.py (per-dataset field mapping), clip via shapely
  app/layers/weather/getter.py
  app/api/routes/layers.py        /api/get-layer-one … four, /api/get-layer-two/point, /api/get-layer-two/walkability.png
  app/api/routes/tiles.py         /api/tiles/{source}/{z}/{row}/{col}
  app/schemas/layers.py           pydantic response models (shown in /docs)
  tests/<module>/test_<file>.py   mirrors app/ (SKILL.md section 11); conftest.py builds the synthetic data;
                                  tests/integration/ holds the real-data checks
scripts/build_weather/build_weather.py   new: data/raw/mdad → data/derived/weather
scripts/build_weather/tests/             regression test against the skill's own output
scripts/requirements.txt          + pandas, scipy, pytest
README.md                         + `python scripts/build_weather/build_weather.py` in the data steps
```

### Getter interface (all four)
- `describe() -> dict` — the summary returned by the layer's `/get-layer-*` endpoint.
- `sample(lon, lat, season=None) -> dict | None` — what this layer knows about one point; for the master graph.

Layer-specific methods:

| Getter | Extra methods | `sample()` returns |
|---|---|---|
| Base imagery | `sources()`, `tile_path(source, z, row, col) -> Path \| None` | `None` (routing does not use imagery) |
| Relief | `grid() -> (elevation, slope_deg, slope_class)` numpy arrays + geo-transform, `point(lon, lat)` | elevation, slope, class |
| POI | `features(categories=None)` | features within `poi_sample_radius_km` (default 2 km) |
| Weather | `cells(season)`, `aoi_frame(season)` | that cell's risk + confidence for **all four seasons**, keyed by season |

## 4. Endpoints

All under `/api` (the Vite dev server already proxies `/api/*`). Names follow the diagram.

### Layer 1 — `GET /api/get-layer-one`
```json
{ "layer": "base_imagery", "default_source": "ctx_coprates",
  "sources": [ { "id": "ctx_coprates", "title": "CTX mosaic, Coprates / East Melas",
                 "tile_url": "/api/tiles/ctx_coprates/{z}/{y}/{x}", "format": "png", "tile_size": 256,
                 "min_zoom": 5, "max_zoom": 9, "bounds": [[-13.4, -71.8], [-10.0, -68.0]],
                 "coverage_note": "98 % of the demo area" } ] }
```
Sources: `ctx_coprates` (primary), `ctx_global` (fallback, gaps in the south-east), `hirise` (~17 % coverage).
`tile_size`, zoom range and format are read from what is on disk / the manifest, not hard-coded per request.

### Tiles — `GET /api/tiles/{source}/{z}/{row}/{col}`
- Serves `data/raw/tiles/<folder>/<z>/<row>/<col>.<ext>` with the right content type.
- `source` must be a key of the config tile-source table (short id → NASA folder name + extension). Anything else → 404,
  so no path outside the tile folders can be reached; `z`, `row`, `col` are integers.
- Missing tile → 404 (the frontend uses a transparent error tile).
- The table also holds `hillshade_color`, `hillshade_ctx` (Layer 2) and `crism_sulfate` (Layer 3).

### Layer 2 — `GET /api/get-layer-two`
- `bounds`, `resolution_m` (~185), `elevation_range_m`.
- `slope_classes`: 5 entries `{id, label, min_deg, max_deg, color, walkable, vehicle}`; thresholds from config
  (0–5 easy walk · 5–15 walkable · 15–25 vehicle only · 25–35 hard / vehicle limit · >35 impassable — unconfirmed by the product owner).
- `overlay`: `{ "url": "/api/get-layer-two/walkability.png", "bounds": … }`.
- `hillshade_sources`: colour hillshade (z5–8, ~98 %), CTX hillshade (z5–9, ~48 %).
- `caveats`: e.g. "The 200 m elevation grid underestimates local slope; all slope values are approximate."

`GET /api/get-layer-two/walkability.png` — RGBA PNG, one pixel per grid cell, coloured by slope class; rendered once at startup.

`GET /api/get-layer-two/point?lon=&lat=` → `{lon, lat, elevation_m, slope_deg, slope_class, walkable, vehicle, approximate: true}`.
Outside the demo area → 404 "outside the area covered by the elevation data".

Slope: `numpy.gradient` on the elevation grid with pixel sizes in metres (Mars sphere R = 3,396,190 m; east–west scaled
by cos(latitude of the AOI centre)) → degrees. Expected class shares on the real data: 52.8 / 32.7 / 10.7 / 3.5 / 0.4 %.

### Layer 3 — `GET /api/get-layer-three?category=`
GeoJSON FeatureCollection; every feature has the same `properties`:
`id`, `category`, `name`, `description`, `source`, `raw` (all original fields).

| Source file | category | name / description |
|---|---|---|
| `Aquieous_Mineral_Distribution_Options_clon0__0` | `mineral` | "Sulfate detection" / "Silica detection" (from `Class`) |
| `Hydrous_Mineral_Detections_OMEGA_CRISM_clon0__0` | `mineral` | "Hydrous mineral detection" + instrument |
| `RSLs_Gullies_New_IcyCraters_clon0__0` | `water_activity` | from `Type` (e.g. "Confirmed recurring slope lineae (RSL)") + reference |
| `EZMars__0` | `exploration_zone` | "<name> exploration zone (centre)" + links |
| `EZMars__3` | `exploration_zone` | "<ez_name> ROI <name>" (coded columns stay in `raw`) |
| `EZMars__4` | `exploration_zone` | "<name> exploration zone boundary" |
| `Dune_Field__0` | `dunes` | "Dune field <Dune_ID>" + dune type |
| `SIM3292_Global_Geology__0` | `geology` | "<UnitDesc> (<Unit>)"; geometry clipped to the AOI |
| `combinedNom__0` | `place_name` | `name` + feature type and origin |
| `mars_mro_crism_mtrdr_c0a_humex_frt_sites__0` | `observation` | "CRISM observation <ProductId>" + date |

- `id` = `<file stem>:<FID or index>`; stable across restarts.
- Top-level extras: `categories` (count per category), `overlays` (the `crism_sulfate` tile source).
- `?category=mineral,water_activity` filters; unknown category → 422.
- Real data: 50 features before clipping (7 + 2 + 3 + 1 + 18 + 2 + 5 + 8 + 2 + 2).
- Coordinates are already −180..180 in the downloaded files; the getter still normalises any longitude > 180.

### Layer 4 — `GET /api/get-layer-four?season=`
- `season` required: `autumn | winter | spring | summer` → mapped to the data names
  (`S. Autumn (Ls 0-90)`, `S. Winter (Ls 90-180)`, `S. Spring (Ls 180-270, perihelion)`, `S. Summer (Ls 270-360)`). Missing/other → 422.
- Response: FeatureCollection of 1,600 cells for that season (≈1.2 MB) with all original properties, plus
  - `display_risk`: `typical_year_risk` if **not null**, else `risk`, else `neighbour_estimate.risk` (null-safe; in the file
    every cell has every key, often with `null`).
  - `display_style`: `solid` (reliable), `hatched` (approximate), `grey` (insufficient_data).
- `message` passed through verbatim.
- Top level: `caveat`, `season`, `season_name`, `legend` (risk → colour, from config), `aoi_summary` (the demo-area
  frame for that season from `aoi_weather_frames.json`).

## 5. Weather build script — `scripts/build_weather/build_weather.py`

- Input `data/raw/mdad/MDAD_original`; outputs `data/derived/weather/context_weather_frames.geojson` and `aoi_weather_frames.json`.
- A port of the skill scripts 06 + 07 logic (storm ellipses, observation gaps, observed years, Poisson interval,
  confidence rules, neighbour fill, messages) with the same constants. It does **not** import the skill scripts: importing
  them creates `outputs/` and `data/` folders inside the skill directory.
- Left out: the global 5° run, preview PNGs, intermediate CSVs.
- **Regression check:** the current `data/derived/weather/` files (built with the skill's own scripts) are copied aside
  first; the new output must be identical (same 6,400 cells, same values, same `message` text).

## 6. Errors

| Situation | Response |
|---|---|
| A layer's files missing or unreadable at startup | Server starts; that layer's endpoints → 503 `{detail, fix}` naming the script to run (`download_data.py` / `build_weather/build_weather.py`). Other layers work. |
| Bad `season`, unknown `category`, missing / non-numeric `lon`/`lat` | 422 |
| Point outside the AOI | 404 with explanation |
| Unknown tile source or missing tile | 404 |

## 7. Testing (pytest, test-first)

Unit tests on a small synthetic data folder generated by `backend/tests/conftest.py` (6×8 elevation GeoTIFF, a few
features per POI dataset, a few weather cells, a handful of tiles), so no binary fixtures are stored:
- slope values and class edges; walkability PNG size and colours
- POI field mapping per dataset, category filter, longitude normalisation, geology clipping
- `display_risk` / `display_style` with `null` fields; season mapping
- tile route: unknown source → 404, path tricks rejected, content type
- registry: missing data → 503 on that layer only

Real-data tests (skipped automatically when `data/` is absent):
- Layer 1: 3 sources; a known tile is served
- Layer 2: class shares 52.8 / 32.7 / 10.7 / 3.5 / 0.4 % (±0.1); point lookup equals the grid value
- Layer 3: 50 features before clipping; counts per category
- Layer 4: 1,600 cells per season; demo-area cell (−69.5, −11.5) → Winter High, Spring Low (approximate)
- `build_weather.py` output equals the reference copy (`pytest scripts/build_weather/tests`)

Environment: `backend/.venv` (as in the README).

## 7a. Differences from the team's layer ingestion contract

`references/layer-ingestion.md` (added after this design was approved) proposes a different shape. This change keeps the
approved design and only adopts the team's folder and test rules. Open differences for the team to settle:
- Module halves: here one `getter.py` per layer; the contract proposes `ingest.py` + `service.py`, plus shared
  `contracts.py`, `fakes.py`, `validate.py` and a `GridSpec`.
- Endpoints: here `/api/get-layer-one … four` (from the architecture diagram); the contract proposes `/api/layers/…`.
- POI field: here `category` (7 values); the contract proposes `kind` (10 values).
- Weather file: here `data/derived/weather/` built by `scripts/build_weather/`; the contract reads `data/raw/weather/`.
- Error type: here `LayerUnavailable(detail, fix)`; the contract proposes `LayerDataError(layer, message)`.

## 8. Assumptions to revisit
- Slope thresholds are unconfirmed by the product owner (config).
- The ROI coded columns (`scibio_1_d`, …) have no lookup table; names stay numeric.
- Product scope lists five layer categories; here "resources" and "points of interest" share Layer 3 via `category`, and
  "hazards" is Layer 4 (dust storms) plus the impassable slope class in Layer 2.
