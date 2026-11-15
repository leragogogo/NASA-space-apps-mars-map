---
name: mars-mvp-data
description: Project context, requirements and exact datasets for the Mars astronaut-map MVP: a hyper-local, 4-layer map. It shows base imagery, relief/walkability and points of interest for East Melas Chasma, plus a seasonal dust-storm risk layer on a 1° grid over the wider Valles Marineris area. Use it whenever building, extending or debugging any part of this project: fetching NASA Trek tiles or vectors, computing slopes, querying MDAD storm data, showing risk and confidence labels, writing a layer ingestion module, defining per-profile edge costs and resource use (oxygen, water, energy), or building the multi-destination route planner (NumPy/SciPy graph + Google OR-Tools, per-profile edge weights for astronaut and car). Bundles the working Python scripts (scripts/01-08) as a reference implementation.
---

# Mars MVP: data skill

## 1. Project goal
An interactive Mars map for **astronauts and mission planners**, built from stacked layers. The MVP is a **short demo**, **hyper-localized** to the single area with the most overlapping data. It does not cover the planet.

## 2. Requirements (from the product owner, verbatim intent)
1. **Layer 1: base layer.** Plain imagery, no marks. Source: NASA Mars Trek.
2. **Layer 2: relief layer.** Height or depth of any point. Must show terrain astronauts can't walk (steep inclines), terrain passable only by vehicles ("cars"), extreme features (Olympus Mons ~22 km) and holes or pits usable as shelter. Source: NASA Mars Trek.
3. **Layer 3: points of interest.** Spots of scientific interest: minerals, ice, possible fossils or remains.
4. **Layer 4: weather (MVP = static version).** Zones affected by weather (e.g. frequent dust storms), marked as "zone of high risk", **clustered by season** (Winter/Autumn/Spring/Summer). A square can be risky in one season and safe in another.
5. **Data-sufficiency rule (mandatory):** where a frame (grid cell or area × season) lacks enough data, the UI must **explicitly state that there is not enough data to reliably calculate risk or weather**. It may show an **approximate value only if clearly labelled as approximate**, with the reason.
6. Tooling: Python, using the project venv (`./venv/bin/python`). Exploration scripts live in `scripts/01`–`07`.

## 3. Demo area (AOI)
**East Melas / Coprates Chasma, Valles Marineris**
- bbox (lon −180..180, planetocentric, Mars 2000 sphere R = 3,396,190 m):
  ```
  west = -71.8, south = -13.4, east = -68.0, north = -10.0   (~225 × 200 km)
  ```
- Chosen from 9 candidate regions by an overlap score of servable layers, relief coverage and POI density. It scored **0.89**, ahead of Mawrth Vallis (0.64), Deuteronilus (0.60) and Gusev (0.54). See `outputs/region_scores.csv`.
- Relief: −5,401 m to +4,596 m (**~10 km of relief**). Canyon walls, mesas and a chasma floor.
- Slope at 200 m DEM resolution: 53 % 0–5°, 33 % 5–15°, 11 % 15–25°, 3.5 % 25–35°, 0.4 % >35°. This **underestimates** local steepness.
- AOI latitude is ~12° S, so **seasons are named for the southern hemisphere**.

## 4. Access endpoints (all public, no auth)
| What | URL pattern |
|---|---|
| Trek layer catalogue | `https://trek.nasa.gov/mars/TrekServices/ws/index/eq/searchItems?proj=urn:ogc:def:crs:IAU2000::104905&start=0&rows=100000&facetKeys=itemType|serviceTypes&facetValues=product|Mosaic` |
| WMTS capabilities | `https://trek.nasa.gov/tiles/Mars/EQ/{label}/1.0.0/WMTSCapabilities.xml` |
| WMTS tile | Read `ResourceURL@template` from capabilities. Usually `.../{label}/1.0.0/default/default028mm/{z}/{row}/{col}.png` |
| ArcGIS REST (hidden, essential) | `https://trek.nasa.gov/mars/trekarcgis/rest/services?f=json` (76 services) |
| Vector query | `.../services/{svc}/MapServer/{layer}/query?f=geojson&where=1=1&outFields=*&geometry=W,S,E,N&geometryType=esriGeometryEnvelope&inSR=4326&outSR=4326&spatialRel=esriSpatialRelIntersects` |
| Elevation values | `.../services/{svc}/ImageServer/exportImage?bbox=W,S,E,N&bboxSR=104905&imageSR=104905&size=W,H&format=tiff&pixelType=F32&noData=-32767&f=image`, or `/identify?geometryType=esriGeometryPoint&geometry={"x":lon,"y":lat}&f=json` |
| Metadata / abstract | `https://trek.nasa.gov/mars/TrekWS/rest/cat/metadata/fgdc/html?label={label}` · `.../rest/cat/abstract?label={label}` |
| MDAD (weather) | `https://dataverse.harvard.edu/api/access/datafile/3607412?format=original` (CSV, ~2 MB) |

**WMTS gotchas**
- EQ tile matrix: top-left (−180, 90). Level 0 is 2 × 1 tiles.
- **Tile size varies by layer: 512 px (CTX global, HiRISE global) or 256 px (most others).** Always read `TileWidth` and `MatrixWidth` per zoom from capabilities.
- Ground resolution = `360 / MatrixWidth / TileWidth × 59,274.7 m/deg`.
- Missing tile = no coverage.

## 5. Datasets to use (final selection)

### Layer 1: base imagery
| Role | Title | Label / service | Notes |
|---|---|---|---|
| **Primary** | MRO CTX, Coprates EMelas Chasm Mosaic | `Coprates_EMelas_Chasm_CTX_BlockAdj_dd` (WMTS, 256 px) | ~98 % AOI coverage, ~10 m/px, seamless |
| Fallback | MRO CTX, Mosaic Global Uncontrolled (Caltech) | `CTX_beta01_uncontrolled_5m_Caltech` (WMTS, 512 px, Esri-hosted) | ~92 % coverage, holes in the SE |
| Zoom-in detail | MRO HiRISE, Mosaic Global Uncontrolled | `HiRISE_Global` (WMTS, 512 px) | ~16 % scattered footprints. Native 0.25 m; verify max served zoom |

### Layer 2: relief
| Role | Title | Label / service | Notes |
|---|---|---|---|
| **Values: elevation, slope, walkability** | MOLA + HRSC blended DEM, 200 m | ImageServer `Mars_MOLA_blend200ppx_HRSC_DEM_clon0dd_200mpp_lzw` | **Only Trek source of real metres** (int16). Also works for the global MOLA DEM `mola128_mola64_merge_90Nto90S_SimpleC_clon0` |
| Visual relief | MOLA+HRSC Color Hillshade Blend | `Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw` (WMTS, JPEG) | 100 % coverage, ~163 m/px |
| Hi-res visual | MRO CTX East Melas Hillshade / DEM | `CTX_Shade_East_Melas`, `CTX_DEM_East_Melas` (WMTS) | ~20 m/px, strips only (~45–85 %). **The DEM tiles are greyscale pictures, not values** |
| Hi-res slope picture | CTX Color Slope tiles | `CTX_ClrSlope_8bit_*` (e.g. `..._12S290E_24mp_D18_034250_1676_D21_035450_1674`) | Narrow strips |

- Slope classes used so far (**unconfirmed by product owner, keep configurable**): 0–5° easy walk · 5–15° walkable · 15–25° vehicle only · 25–35° hard / vehicle limit · >35° impassable. They now live in `config/mars.yaml` (`slope_classes`, with the profile limits and budgets); see `references/edge-cost-model.md` section 8.
- **Limitation:** the 24 m CTX DEM and Slope products (e.g. `CTX_DEM_12S290E_...`) appear in the Trek catalogue but have **no WMTS or value service**. For sharper slopes, get the source DTMs from PDS / USGS Astrogeology.
- Shelter candidates (pits, skylights) are not a Trek layer. Derive local depressions from the DEM, or mark this as future work.

### Layer 3: points of interest (vector via ArcGIS MapServer unless noted)
| Dataset | Service / layer | In AOI |
|---|---|---|
| RSLs, Fresh Gullies, New and Icy Craters | `RSLs_Gullies_New_IcyCraters_clon0` /0 | 3 RSL sites (seasonal brine flows) |
| Aqueous Mineral Distribution | `Aquieous_Mineral_Distribution_Options_clon0` /0 (**note the misspelling**) | 4 sulfate, 1 silica |
| Hydrous Mineral Detections (OMEGA, CRISM) | `Hydrous_Mineral_Detections_OMEGA_CRISM_clon0` /0 | 2 |
| CRISM Polyhydrated Sulfate Indicator (raster) | WMTS `MC18_PolySulfate_Mineral_IndicatorV2_SP` | ~70 % coverage, clear hotspots |
| NASA Human Exploration Zones | `EZMars` /0 EZ, /1 Hab_Zone, /2 Landing_Zone, /3 ROI, /4 EZ_Buffer | "Melas Chasma" EZ and its regions of interest |
| Dune fields | `Dune_Field` /0 | several (wind indicator) |
| Nomenclature | `combinedNom` /0 | place names (Ophir Labes, Garni, …) |
| Geology units | `SIM3292_Global_Geology` /0 | context polygons |
| CRISM targeted sites | `mars_mro_crism_mtrdr_c0a_humex_frt_sites` /0 | 2 footprints |

- Point coordinates in some layers use 0–360 east longitude. **Normalise to −180..180.**
- Ice and glacier layers (`Mars_Fans_Glaciers_Gullies`) have nothing in this equatorial AOI. Ice-rich POIs would need a mid-latitude AOI such as Deuteronilus.

### Layer 4: weather (static seasonal dust-storm risk)
- **Dataset:** Mars Dust Activity Database (**MDAD**, Battalio & Wang), Harvard Dataverse `doi:10.7910/DVN/F8R2JX`, file `MDAD.tab`, id 3607412.
  - ~15k storm-sol rows, 8,428 storms
  - Covers MY24 Ls150 to MY32 Ls171 (1999–2015)
  - Columns: Mars Year, subphase, Sol, Ls, centroid lon/lat, area km², Member ID, Sequence ID, max/min latitude, confidence, missing-data flag
- **No storm outlines.** Footprint = ellipse at the centroid. The N–S semi-axis comes from the lat span; the E–W semi-axis is solved from the area. Storm ID = `subphase + "_" + Member ID`.
- **Rejected:** ESA PSA "Mars maps" (`cosmos.esa.int/web/psa/mars-maps`) only has OMEGA albedo and mineral maps. Its nanophase-ferric map shows settled dust, not storms, so it has no seasonal or weather content. Trek also has no weather layer.
- Seasons (Ls quarters, southern-hemisphere names): Autumn 0–90, Winter 90–180, Spring 180–270 (perihelion, global-storm season), Summer 270–360.
- Risk thresholds (storm-days per Mars year): **Low < 1 · Moderate 1–4 · High ≥ 4** (configurable).

**AOI results** (`outputs/weather/aoi_weather_frames.json`):
| Season | Confidence | Value | Label |
|---|---|---|---|
| Autumn | reliable | 0 storm-days/yr (0 storms in 7.8 yrs; upper 95 % 0.47 storms/yr) | Low |
| Winter | reliable | 6.56/yr (95 % 4.5–9.2), 33 storms in 8.2 yrs, peak Ls 130–160 | **High** |
| Spring | **approximate** | typical year 0.3/yr → Low. **37 of 39 storm-days are from MY25 (2001 global storm).** Extreme year: High | Low (typical) / High (extreme) |
| Summer | reliable | 2.03/yr, 10 storms in 7.4 yrs, peak Ls ~310–320 | Moderate |

- Storms are far larger than the AOI (mean ~1.5M km² vs ~45k km²). Risk is nearly uniform inside the AOI (1° cells within ±10 %).

**DECISION: Layer 4 uses the wider Valles Marineris grid, not the AOI alone.** Layers 1–3 stay on the East Melas AOI.

Weather grid spec:
- **Extent:** `CONTEXT = (-90.0, -30.0, -50.0, 10.0)` (west, south, east, north), defined in `scripts/06_mdad_weather.py`.
- **Grid:** 1° × 1° cells (~59 km), 40 × 40 = **1,600 cells × 4 seasons = 6,400 frames**. The AOI sits inside it; draw its outline on top for context.
- **Delivered file:** `outputs/weather/context_weather_frames.geojson`. It is a FeatureCollection of 1° polygons; each feature's `properties` hold one frame (see the section 6 fields plus `season`). The top-level `caveat` must be shown in the UI.
- **Risk to colour in each cell (`display_risk`):**
  1. `typical_year_risk` if present: the frame is dominated by one extreme year. Also show `extreme_year` in the tooltip.
  2. else `risk`.
  3. else `neighbour_estimate.risk`: insufficient data, so draw it greyed or hatched with the "not enough data" message.
- **Styling:**
  - Low = green, Moderate = amber, High = red.
  - `approximate` = hatched.
  - `insufficient_data` = grey overlay.
  - Tooltip / click shows `message` verbatim.
- **Season switcher:** filter features by `properties.season`. The four values are exactly `S. Autumn (Ls 0-90)`, `S. Winter (Ls 90-180)`, `S. Spring (Ls 180-270, perihelion)` and `S. Summer (Ls 270-360)`.
- **Confidence counts on the grid** (from script 07):

  | Season | reliable | approximate | insufficient |
  |---|---|---|---|
  | Autumn | 1,341 | 259 | 0 |
  | Winter | 1,128 | 472 | 0 |
  | Spring | 220 | 1,380 | 0 |
  | Summer | 666 | 934 | 0 |

  Spring is mostly approximate because the MY25 (2001) global storm dominates it.
- **Spatial pattern** (verified on `outputs/weather/weather_layer_preview.png`):
  - The east edge (east of ~60° W) is Moderate–High in every season. The south-east corner (55–50° W, 15–30° S) is High year-round.
  - The north-west (west of ~65° W, north of ~5° S) is Low in all four seasons.
  - **Winter:** almost the whole southern half (south of ~8° S, including the AOI) is High; the north is Low.
  - **Spring:** the west two-thirds are Low (typical year) but hatched as approximate because of the MY25 storm; the east is Moderate–High.
  - **Summer:** a Moderate band covers the AOI and the south; High is confined to the east.
- **AOI cells:** Autumn Low · Winter High · Spring Low (approximate) · Summer Moderate. This matches the AOI-level frames.
- **Preview / summary:** `scripts/08_weather_grid_summary.py` → `outputs/weather/grid_risk_confidence_summary.csv` and `outputs/weather/weather_layer_preview.png`.
- **AOI-level frames** (`aoi_weather_frames.json`, table above) remain available as a summary card for the demo area.

## 6. Data-sufficiency / confidence rules (implemented in `scripts/07_weather_confidence.py`)
MDAD lists only storms, never "observed, no storm". **Zero storms ≠ zero risk unless the frame was actually observed.** Coverage is rebuilt as follows:
- MY24 starts Ls150; MY32 ends Ls171.
- MOC era (MY24–27) is limited to 60° S–60° N. MARCI era (MY28–32) is global.
- Imaging gaps = any ≥10° Ls window with no storm anywhere on Mars:

  | Mars year | Gap (Ls) |
  |---|---|
  | MY24 | 245–255 |
  | MY25 | 250–260 and 265–275 |
  | MY27 | 260–275 |
  | MY28 | 290–305 |
  | MY29 | 330 → MY30 20 (MRO safe mode) |

  See `outputs/weather/observation_gaps.csv`.

Every frame gets `confidence`:
| Value | Rule | What the UI must show |
|---|---|---|
| `reliable` | ≥6 observed Mars years, ≥5 distinct storms (or 0 storms with ≥6 yrs), no single year >50 % of storm-days, ≤50 % records flagged missing | Risk level and rate |
| `approximate` | ≥3 observed years but fails any rule above | **"APPROXIMATE: not enough data to reliably calculate the risk…"**, best estimate, 95 % range or typical vs extreme year, and the reasons |
| `insufficient_data` | <3 observed years | **"NOT ENOUGH DATA: risk cannot be reliably calculated…"**, plus an estimate averaged from usable neighbours within 3°, labelled "indicative only". Otherwise "no estimate possible" |

- Every output also carries the global caveat: storms smaller than ~100,000 km² are not reliably catalogued, footprints are approximations, and values are historical frequencies, not forecasts.
- Each frame JSON has these fields: `observed_years, storm_days, storms, rate, rate_ci95, storms_per_year, risk, confidence, reasons[], typical_year_rate?, typical_year_risk?, extreme_year?, neighbour_estimate?, message`.
- **The UI should render `message` verbatim** and style by `confidence`.
- Current results:
  - Context grid: Spring is mostly `approximate` (the MY25 storm dominates).
  - Polar frames (>60°) are always `approximate` (~4.8 observed years).
  - No frame currently falls below 3 years. The `insufficient_data` path exists for other datasets and regions.
- **Apply the same three-level rule to any future layer with sparse data** (e.g. Mars Climate Database extensions, POI density).

## 7. Bundled scripts (reference implementation)
- Copies of every exploration script, plus `requirements.txt`, ship **inside this skill folder**: `context/skills/mars-mvp-data/scripts/` and `context/skills/mars-mvp-data/requirements.txt` (also reachable as `.claude/skills/...`, a symlink to `context/skills`).
- **You normally don't need to run them again.** The datasets are fetched by `scripts/download_data.py` at the repo root (see below). The numbered scripts are reference logic for the analysis (slopes, MDAD footprints, confidence rules).
- **Read them before re-implementing anything.** They contain the working versions of all the tricky bits:
  - catalogue query
  - WMTS tile maths with per-layer tile size
  - ArcGIS vector and DEM queries
  - MDAD ellipse footprints, observation-gap detection and the confidence rules
- **To run them in a new project:**
  - Copy `scripts/` to `<project root>/scripts/`. Every script resolves `ROOT = Path(__file__).resolve().parent.parent`, so if run from inside the skill folder its outputs land in the skill folder.
  - Install the deps: `pip install -r requirements.txt`.
  - Run in order: 01 → 08. Scripts 04–08 import constants (`REGIONS`, `AOI`, `SEASONS`, `CONTEXT`) from earlier scripts by file name, so keep the `NN_` names.
  - Scripts 01-03 and 05 query Trek and ArcGIS when run, and 06 reads `data/raw/mdad/MDAD_original`. They are exploration tools only; the application never calls those APIs (see section 9).
- **Canonical source:** the old `data-exploration` folder no longer exists, so the copies in `context/skills/mars-mvp-data/scripts/` are now the only ones. Edit them here.

### Files in the data-exploration repo
```
scripts/01_fetch_catalog.py        Trek catalogue (235 layers) -> outputs/catalog_all.csv
scripts/02_probe_services.py       WMTS availability + resolution -> outputs/catalog_with_services.csv
scripts/03_poi_features.py         POI vector counts per candidate region (REGIONS dict) -> data/raw/features/*.geojson
scripts/04_region_scoring.py       region score -> outputs/region_scores.csv
scripts/05_aoi_deep_dive.py        AOI const, DEM export, slope classes, tile stitching -> outputs/aoi/
scripts/06_mdad_weather.py         MDAD load, ellipse footprints, seasonal counts -> outputs/weather/
scripts/07_weather_confidence.py   confidence labelling -> aoi_weather_frames.json, context_weather_frames.geojson (THE weather layer)
scripts/08_weather_grid_summary.py weather grid summary + preview map (risk colours, approximate hatched, insufficient grey)
outputs/RECOMMENDATION.md          human-readable dataset recommendation
requirements.txt                   venv packages (requests, pandas, numpy, pillow, matplotlib, shapely, tifffile, scipy)
```
- Run with `./venv/bin/python scripts/NN_*.py` from the repo root, in order.
- Scripts 04–07 import constants from earlier scripts (`REGIONS`, `AOI`, `SEASONS`, `CONTEXT`).

## 8. Open questions / next steps
- Confirm slope thresholds for walking vs vehicles with the product owner.
- Confirm the per-profile cost formulas, resource formulas, units and parameter values (suit mass, capacities, rates). Proposed in `references/edge-cost-model.md`; all constants are placeholders.
- ~~Weather layer file~~ **done:** the data pipeline's `weather` step (`scripts/weather/`) regenerates `data/raw/weather/context_weather_frames.geojson` from the downloaded MDAD file. Its output reproduces the documented results (confidence counts per season, AOI frames).
- Where is the habitat (needed for walk-back feasibility, future)?
- Future, not in the MVP (details in `references/edge-cost-model.md` section 10): walk-back feasibility filter, solar-particle-event shelter reachability, per-astronaut calibration from heart rate, higher-resolution slopes (24 m CTX DTMs, optionally via GDAL), shelter-candidate detection from the DEM.
- Is the 200 m DEM enough for the demo, or should we pull the 24 m CTX DTMs from PDS for a sub-area?
- ~~Weather display scale~~: **decided, use the Valles Marineris 1° grid** (section 5, Layer 4).

## 9. Environment gotcha
- The repo lives under `~/Desktop`, which is **synced to iCloud with "Optimize Mac Storage"**. macOS can offload files (venv packages, scripts, outputs) to "dataless" placeholders.
- Python then **hangs at 0 % CPU on `import`** while each file downloads.
- Check with `find . -flags +dataless | wc -l`. Request a download with `brctl download <dir>`.
- Long term: keep the venv (or the whole repo) outside iCloud-synced folders, or mark the folder "Keep Downloaded" in Finder.
- Optional dynamic weather layer: Mars Climate Database (seasonal dust opacity, wind, temperature).
- Shelter detection (pits and depressions) from the DEM is not yet implemented.

## 8. Data download pipeline (repo root)
`python scripts/download_data.py` (deps: `scripts/requirements.txt`) fetches everything the MVP uses into `data/raw/` (gitignored). Re-runs skip existing files; `--force` re-downloads; `--only dem|tiles|pois|mdad|weather` limits it; `--max-zoom N` limits tile volume (default z5-9, ~1,000 tiles, ~46 MB total).

| Layer | Output | Source |
|---|---|---|
| 2 relief values | `data/raw/dem/dem_blend200m_aoi.tif` (float32 m, 1200x1073) | Trek ImageServer, MOLA+HRSC 200 m |
| 1, 2, 3 imagery | `data/raw/tiles/<label>/<z>/<row>/<col>.png\|jpg` | Trek WMTS: Coprates mosaic, CTX global, HiRISE, colour hillshade, CTX hillshade, CRISM polysulfate |
| 3 POIs | `data/raw/features/<service>__<layerId>.geojson` | Trek ArcGIS MapServers (empty layers are not written) |
| 4 weather input | `data/raw/mdad/MDAD_original` | Harvard Dataverse file 3607412 |
| 4 weather layer | `data/raw/weather/{context_weather_frames.geojson, aoi_weather_frames.json, observation_gaps.csv}` | computed from MDAD by `scripts/weather/` (pandas + scipy; ~5 s) |
| log | `data/raw/manifest.json` | counts per dataset |

- Tile row/col are WMTS indices with a top-left origin (same as XYZ rows). Read `TileWidth` per layer: 512 px for CTX global and HiRISE, 256 px for the rest.
- A few tiles are genuinely unavailable (e.g. some tiles of the CTX global mosaic intermittently return HTTP 500). They are reported as `unavailable`/`missing`, not failures.
- **13 CTX global mosaic tiles over the AOI (z5, z8, z9) are stored truncated on Trek:** HTTP 200 with a matching Content-Length, but the image is cut off, and every re-download returns the same bytes. The script fully decodes every tile (fresh and already on disk) and does not keep ones that fail; they are reported as `corrupt` and the app treats them as missing. The primary Coprates mosaic is unaffected.
- The weather layer is **computed, not downloaded**: the `weather` step runs `scripts/weather/build.py` (a port of skill scripts 06 -> 07 without their plotting and imaging dependencies) on `data/raw/mdad/MDAD_original`. Run it alone with `python scripts/download_data.py --only weather` (add `--force` to recompute). Tests: `cd scripts && pytest`. The API getter and the graph ingestion both read `data/raw/weather/`.

## 9. Application architecture (decided)

### Principles
- **The frontend consumes only our FastAPI backend.** It never calls NASA Trek, Harvard Dataverse or any other source directly. The backend owns the response format of every layer so that datasets from different sources look uniform to the client.
- **Static dataset, local files only.** For this MVP the data is static. `scripts/download_data.py` is a one-off setup step that fills `data/raw/`; after that, **neither the backend nor the frontend makes any call to an external API, and there is no proxy or cache layer.** The backend serves every layer directly from the downloaded files. If a tile or feature was not downloaded, it does not exist for the app (extend the download script and re-run it instead). Reasons: Trek returns HTTP 500 on some tiles, demo-venue wifi is unreliable, the graph must be built from identical data every time, and MDAD has no query API (weather is computed locally).
- **Single source of truth for relief.** The slope overlay shown to users and the slope used by the router must come from the same array.

### Backend (FastAPI)
- Four independent layer endpoints (base imagery, relief, points of interest, weather) plus one route endpoint: `POST /api/route`, a **multi-destination** route for a profile (`astronaut` | `car`; replaces the earlier `walker` | `vehicle` naming). Full spec in section 10.
- **Layer ingestion modules** (`backend/app/layers/<layer>/`): each turns `data/raw/` files into normalised, validated data aligned to one shared `GridSpec` (`ingest.py`), plus a client-facing half (`service.py`). The graph builder consumes only that output and never reads `data/raw/` itself. Imagery is tile-serving only; the graph does not use it. **Contract, per-layer fields, fixtures and parallel work packages: `references/layer-ingestion.md`.**
- **Master graph** (`backend/app/graph/`): one directed graph built offline from the layer getters' data and stored as **flat NumPy arrays** (`src`, `dst`, and one array per profile and attribute), not as Python objects. Every directed edge carries, **for each profile, a routing `cost` plus resource consumption** (time, O2, CO2, water, energy). Model and formulas: `references/edge-cost-model.md`. Nodes carry elevation, slope, nearby points of interest, and the four seasonal risk values with their confidence. **Season is a query parameter, not part of the graph or the edge weights.** The graph is built on the relief getter's **native 200 m grid** (1,287,600 nodes, 10,287,166 directed edges with 8 neighbours); `--coarsen N` averages it down if ever needed. Persist the built graph under `data/graph/` (gitignored). (This supersedes the earlier "implicit numpy grid + A*" decision.)
- **Routing engine** (`backend/app/routing/`): per-profile cost formulas, the SciPy cost matrix and the OR-Tools solver. Slope classes (0-5 easy, 5-15 walkable, 15-25 vehicle only, 25-35 hard/vehicle limit, >35 impassable) are unconfirmed by the product owner, so keep them configurable.
- **Caveats for routing:** weather risk is almost uniform inside the AOI (1 deg cells within +-10 %), so it acts as a season-wide warning, not a route discriminator. The 200 m DEM underestimates local slope.
- **Tiles** (`backend/app/tiles/`): serve `data/raw/tiles/<label>/<z>/<row>/<col>.<ext>` straight from disk (static files). No upstream fetching; a missing tile returns 404 or a transparent tile.

### Frontend (React + Vite + Leaflet)
- Use Leaflet (`react-leaflet`) with **`L.CRS.EPSG4326`**: Trek's equatorial tiles are plain lat/lon (top-left origin -180, 90), not Web Mercator. MapLibre/Mapbox are Mercator-only and would distort the imagery.
- Stored tiles are `z/row/col` with rows counted from the top, which matches Leaflet's `{z}/{y}/{x}`.
- The 512 px layers (CTX global, HiRISE) need `tileSize: 512` and probably a `zoomOffset`; verify against the WMTS capabilities.
- Layer mapping: imagery and colour hillshade are `TileLayer`s; walkability is a pre-rendered slope-class PNG as an `ImageOverlay` on the AOI bbox (Leaflet cannot read the GeoTIFF); POIs are `GeoJSON`; weather is a `GeoJSON` of 1 deg cells filtered by season and coloured by `display_risk`, with hatch for `approximate` (SVG pattern or CSS) and grey for `insufficient_data`. Elevation on click comes from a backend endpoint.
- Set layer `bounds` to the AOI, use a transparent error tile, and normalise POI longitudes from 0-360 to -180..180. Leaflet's scale control assumes Earth: write a custom one or omit it.

### GDAL (optional, not adopted)
Not needed for the MVP: numpy handles the 1200x1073 DEM. Consider `gdaldem` (slope, hillshade, color-relief; scale `-s 59274.7` for degree grids), `gdal2tiles.py` for slope-class tiles, or `/vsicurl/` reads of the 24 m CTX DEMs at PDS/USGS if sharper slopes are needed. Prefer `rasterio` (bundles GDAL) over a system GDAL in the backend.

### Repository structure
```
README.md, AGENTS.md
context/skills/mars-mvp-data/   this skill (SKILL.md, references/, scripts/01-08, requirements.txt)
  references/layer-ingestion.md   contract between raw data and the graph, fixtures, work packages
  references/edge-cost-model.md   per-profile edge cost and resource formulas
.claude/skills                  symlink -> ../context/skills
scripts/download_data.py        one-off data download (static dataset); scripts/requirements.txt
data/raw/                       downloaded datasets (gitignored): dem/, tiles/, features/, mdad/, manifest.json
backend/
  main.py                       starter app (will probably move to app/main.py)
  app/api/routes/               one router per endpoint group
  app/core/                     config, settings
  app/schemas/                  client-facing response models
  app/layers/{base_imagery,relief,poi,weather}/   one ingestion module per layer (ingest.py + service.py); shared `contracts.py`, `fakes.py`, `validate.py` live in `app/layers/` (done)
  app/tiles/                    serves tiles from data/raw/tiles (static, no upstream calls)
  app/graph/                    master graph builder (offline) and loader (startup), see section 10
  app/routing/                  profiles + weight formulas, cost matrix (SciPy Dijkstra on arrays), solver (OR-Tools), route assembly
  tests/
frontend/src/
  api/                          the only place that talks to the backend
  components/                   shared UI
  features/{map,layers,route}/  Leaflet map, layer toggles/season switcher, route UI
  hooks/, config/, utils/
```
Step 0 is done: the shared contracts exist and are tested (see `references/layer-ingestion.md` section 7). Package G (routing engine) and package H (API controller: layer, tile and route endpoints) are done (`app/routing/`, `app/api/routes/`, see section 10 "Implementation"). The four layer modules (packages A-D) are done: `app/layers/<layer>/ingest.py` + `service.py`, plus `app/layers/inputs/load.py: load_all`. The graph (package F) is built from `load_all` with the profile formulas of `app/routing/profiles/`; layers, graph, routing engine and API are integrated and tested end to end (`tests/integration/test_graph_integration.py`, and `test_pipeline_api.py` through the HTTP endpoints). All other module folders are still empty placeholders (`.gitkeep`).

## 10. Multi-destination routing (decided: SciPy Dijkstra on NumPy arrays + Google OR-Tools)
A user picks a profile, a start, several destinations and optionally an end. The backend returns one continuous path that visits the reachable destinations in the best order it finds, and reports the ones it had to drop.
- **`scipy.sparse.csgraph.dijkstra`** computes shortest paths on the terrain graph, which is held as NumPy arrays plus one CSR matrix per profile. (rustworkx was used first; its per-edge Python callback and per-edge Python objects made the 10 M-edge 200 m graph take 149 s and about 20 GB per plan.)
- **OR-Tools** (`ortools.constraint_solver`) orders the stops.
- Backend deps: `scipy` (Dijkstra, KD-tree), `numpy`, `ortools`. Checked with ortools 9.15.

### Profiles
| Profile | Who | Hard limit (from the slope classes, configurable) |
|---|---|---|
| `astronaut` | walking EVA crew | slope > 15° → ∞ |
| `car` | rover / vehicle | slope > 35° → ∞ |

- Profile ids are **`astronaut` and `car`** everywhere (graph keys, API, config).
- Each profile has **its own cost formula**, which combines every relevant parameter: 3D distance, signed slope (uphill ≠ downhill), roughness, energy and so on. **Besides `cost`, each profile also stores per-edge resource consumption** (`time_s`, `o2_g`, `co2_g`, `water_g`, `energy_wh`). Formulas, units and parameters: `references/edge-cost-model.md`.
- Weather risk is not in the cost: weights are precomputed and the season is a request parameter.
- The formulas are **not confirmed by the product owner**. Keep them in one place (`app/routing/profiles.py`) with their constants in config, and record a `formula_version` in the saved graph.
- `cost` is an abstract cost (flat-equivalent metres). Readable figures (time, O2, Wh) come from the stored resource attributes, summed per leg after solving.
- Slope must come from the same array as the relief layer (section 9).

### Step 1: graph construction (offline, once): `app/graph/build.py`
- **Nodes:** terrain points of the (coarsened) DEM grid. Use `node index = row * ncols + col` and add every cell in order, so the grid ↔ node mapping is plain arithmetic. Nodata cells become nodes with no edges.
- **Edges:** **directed**, one per ordered pair of neighbours (8-neighbourhood), because uphill and downhill cost differently. A→B and B→A are separate edges with separate weights.
- **One attribute set per profile on every edge:** `cost` (what routing minimises) plus the resources. Logical view per edge: `{"astronaut": {"cost": .., "o2_g": .., "water_g": ..}, "car": {...}}`; physically one array per `(profile, attribute)`, never a dict per edge. Compute all profiles with vectorised numpy over edge arrays, not one Python loop per edge.
- **Impassable = `math.inf`.** If a profile can't use an edge, its `cost` (and resource attributes) are ∞. **Every edge has every attribute for every profile;** an edge is never left out for one profile, so all profiles share the same topology.
- **`cost` and resources must be ≥ 0 and never NaN.** A downhill bonus must still leave a weight ≥ 0. Infinite-cost (impassable) edges are left out of the CSR matrix, so the search never uses them.
- **Inputs come only from the layer ingestion output (`GraphInputs`)**, never from `data/raw/` directly (`references/layer-ingestion.md`).
- **Persist** to `data/graph/` (gitignored) as `graph.npz`:
  - node arrays (each length `n_nodes`): `lon`, `lat`, `elev_m`, `valid` (required), plus `slope_deg`, `nearest_poi_dist_m`, and the per-season weather as 1-D arrays `weather_risk_0..3` and `weather_conf_0..3` (`SEASONS` order)
  - `cost` is stored as float64 (the solver sums many of them); the resources as float32
  - edge arrays: `src`, `dst`, and for every profile `p` and attribute `a` an array named `p__a` (e.g. `astronaut__cost`, `astronaut__o2_g`, `car__energy_wh`)
  - metadata (the "fingerprint"): format version, grid, `formula_version` (per profile), sha256 of every source file, build parameters (neighbourhood). A saved graph is stale when it no longer matches; `python -m app.graph` rebuilds only then (`--force` to override)
- The loader rebuilds only when the metadata no longer matches. It is not rebuilt on every start.

### Step 2: startup: `app/graph/loader.py` (FastAPI lifespan)
- Load `graph.npz` once and build the `RoutingGraph` (`RoutingGraph.from_graph_data`): `src`/`dst` int32, per-profile `cost` float64 and resource arrays indexed by **edge id**, a sorted `src * n + dst` key array for edge-id lookup, and (lazily, per profile) a SciPy CSR matrix of the finite-cost edges.
- If `graph.npz` is missing the app fails at startup with a clear message to run `python -m app.graph` (it does not build silently).
- The loader's output is a `RoutingContext` (`app/graph/loader.py`): the `RoutingGraph` (`app/routing/graph.py`: arrays, `shortest_paths`, `trace_path`, `edge_id(s)`, `path_cost`, `path_resources`, `coords`) plus the KD-tree used by `app/routing/snap.py`. Routing codes against it.
- Keep every array as NumPy: nothing is stored per edge as a Python object (no cost lists, no per-edge callbacks).
- Keep the lookup structures in app state:
  - node index → (lon, lat) from the arrays
  - (lon, lat) → node index through a `scipy.spatial.cKDTree` built over the **valid** nodes only, in a local metric projection (scale lon by cos(lat))
- The graph is read-only after startup, so it is safe to share across requests.

### Step 3: request handling: `POST /api/route`
Request:
```json
{
  "profile": "astronaut",
  "start": {"lon": -70.1, "lat": -11.5},
  "destinations": [{"lon": -69.8, "lat": -11.2}, {"lon": -70.4, "lat": -12.0}],
  "end_mode": "round_trip",        // "round_trip" (default) | "fixed" | "open"
  "end": null,                     // required only when end_mode = "fixed"
  "time_limit_s": 10,              // optional, default DEFAULT_TIME_LIMIT_S = 10 (app/routing/contracts.py), clamped to 1..30
  "season": "winter"  // autumn | winter | spring | summer (same keys as /api/get-layer-four); optional, for weather warnings only, never for weights
}
```
- **Snap** each point to the nearest valid node with the KD-tree. Return the snapped coordinates and the snap distance. Reject points outside the graph bbox or farther than a configurable maximum (e.g. 1 km).
- **Validate (HTTP 422):**
  - the profile exists
  - there is at least 1 destination and no more than a configurable maximum (e.g. 25)
  - `end` is present if and only if `end_mode = "fixed"`
  - **all snapped nodes are distinct** (start, destinations and end). Two clicks can snap to the same node; reject that and name the duplicates.

### Step 4: cost matrix (SciPy Dijkstra): `app/routing/matrix.py`
- Points: `P = [start, *destinations] (+ end if fixed)`, so N = 1 + len(destinations) (+1).
- **One Dijkstra per point**, using only the chosen profile's `cost`: `dist, pred = routing_graph.shortest_paths(profile, sources)` (SciPy `csgraph.dijkstra` on the profile's CSR matrix, in chunks of 8 sources to bound memory). `dist[k, target]` is the leg weight; `routing_graph.trace_path(pred[k], source, target)` recovers the node path from the predecessors. Either way, one search per point.
- **Fill the matrix** `M[i][j]` (floats, unscaled) with the best path weight from `P[i]` to `P[j]`. **The diagonal is 0.** The graph is directed, so M is **not symmetric**.
- **Unreachable pairs** (both cases verified):
  - **The distance is `inf`:** impassable edges are not in the search graph, so a target reachable only over them has distance `inf`. Treat the pair as unreachable: the cell stays ∞, and **no leg path is saved**.
  - **The target is not connected at all:** its distance is also `inf`. Same treatment.
- **Save each reachable leg's node path** as `legs[(i, j)]` for step 6.
- **Output:** the N×N float matrix with ∞ meaning unreachable, plus `legs`.
- The matrix holds shortest-path costs, so **reachability is transitive**. If start→A and A→B are finite, start→B is finite. Step 5 relies on this to explain drops.
- **Performance (measured on the native 1,287,600-node / 10,287,166-edge graph with the real profiles, Apple silicon):** building the `RoutingGraph` from a loaded `GraphData` ~0.1 s, each profile's CSR matrix ~0.3 s, one Dijkstra ~0.4 s, a 3-stop plan ~2.3 s, the KD-tree for `snap` ~0.5 s once and ~0.1 ms per snap. Peak memory for the whole process (getters, graph build and routing) ~3.5 GB. The previous rustworkx engine took 149 s and ~20 GB for one plan on the same graph.

### Step 5: route solving (OR-Tools): `app/routing/solver.py`
- **Prepare the matrix:**
  - **Scale to integers** (OR-Tools requires them): `round(M[i][j] * SCALE)`. `SCALE` is configurable, e.g. 1000.
  - **Replace ∞ with `BIG = 10**12`.** It must be larger than any real route cost, but small enough that summing a whole route can't overflow int64: (N + 1) · BIG plus all penalties stays far below 9.2·10¹⁸.
  - **Drop penalty:** `PENALTY = N * max_finite_scaled_cell + 1`. This is higher than any real route cost, because a route uses at most N arcs. Assert `PENALTY < BIG`; if it isn't, lower `SCALE`.
- **Start and end:**
  - `round_trip`: `RoutingIndexManager(N, 1, 0)`, where node 0 is the start and depot.
  - `fixed`: `RoutingIndexManager(N, 1, [0], [N-1])`, where the end is the last point.
  - `open`: add a dummy node D with `M[i][D] = 0` for every i, and `M[D][i] = BIG`, then use `RoutingIndexManager(N+1, 1, [0], [D])`. D and its zero legs are never shown to the user.
- **The model:** register the matrix as the transit callback and call `SetArcCostEvaluatorOfAllVehicles`.
- **Allow dropping stops:** call `routing.AddDisjunction([manager.NodeToIndex(d)], PENALTY)` for **each destination only**, never for the start, end or dummy node. Because PENALTY < BIG, an unreachable stop is skipped instead of being "travelled to" along an impossible leg.
- **Search settings:**
  ```python
  params = pywrapcp.DefaultRoutingSearchParameters()
  params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
  params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
  params.time_limit.FromSeconds(time_limit_s)   # mandatory: GLS never stops by itself
  ```
  After the time limit, OR-Tools returns the best route found so far.
- **Read the solution:**
  - **Order:** walk from `routing.Start(0)` via `solution.Value(routing.NextVar(i))` until `routing.IsEnd(i)`.
  - **Dropped:** destination d is dropped when `solution.Value(routing.NextVar(idx)) == idx`.
- **Sanity checks:**
  - If `SolveWithParameters` returns `None`, or the chosen route still uses a BIG arc, then no feasible route exists. This happens when the start can't reach a fixed end, and it returns a clear error (no path).
  - **Reason for a drop:** d is `unreachable_for_profile` if `M[start][d]` is ∞ or `M[d][end]` is ∞, where the end is the start for a round trip; for an open end, only `M[start][d]` counts. This test is exact because reachability is transitive. Otherwise the stop was dropped by the time limit (`not_scheduled_within_time_limit`). This should be rare, but report it honestly.
- **Output:** the ordered stop indices and the dropped stops with their reasons.

### Step 6: route assembly: `app/routing/assemble.py`
- **Join the saved leg paths** in the solved order into one continuous node path, dropping the duplicate node at each join (each leg starts where the previous one ended). Only legs between consecutive visited stops are used, and those are all finite, so every leg exists in `legs`. Skip the leg into the dummy open-end node.
- **Total weight:** add up the legs using the **original unscaled** `M` values, never the scaled integers or the solver objective, which also includes penalties.
- **Resources:** for each leg, sum `attrs[profile][a][edge_id]` over its edges (`routing_graph.edge_ids(nodes)`), for every attribute. Report per leg and in total, and compare the totals with the capacities in config; add a warning for each exceeded budget. Budgets are not enforced inside the search in the MVP (walk-back filtering is future work, see `references/edge-cost-model.md` section 7).
- **Response:**
  ```json
  {
    "profile": "astronaut",
    "path": {"type": "LineString", "coordinates": [[-70.1, -11.5], ...]},   // [lon, lat]; Leaflet needs [lat, lon]
    "stop_order": [1, 0],                  // indices into the request's destinations
    "legs": [{"from": "start", "to": 1, "weight": 812.4}, ...],
    "total_weight": 2150.7,
    "resources": {"time_s": 5400, "o2_g": 910, "co2_g": 1050, "water_g": 1800, "energy_wh": 52},   // totals; each leg has the same keys
    "dropped": [{"index": 2, "point": {...}, "reason": "unreachable_for_profile"}],
    "snapped": {"start": {...,"distance_m": 140}, "destinations": [...], "end": null},
    "warnings": [],                        // e.g. the weather `message` for `season`, verbatim (section 6)
    "body_mass_kg": 72.0                   // the user's mass behind the o2/co2/water estimates (astronaut); null for the car
  }
  ```
- A dropped stop is a normal result, not an error; the UI must list it with its reason. A drop does mean the rest of the route is incomplete for that profile, so show it clearly (data-sufficiency spirit, section 2).

### Implementation (package G, done): `backend/app/routing/`
| File | Entry point |
|---|---|
| `graph.py` | `RoutingGraph.from_graph_data(GraphData)`: NumPy arrays (`src`, `dst`, per-profile `cost` and resources, node lon/lat/valid) plus lazy per-profile CSR matrices. `shortest_paths`, `trace_path`, `edge_id`/`edge_ids`, `path_cost`, `path_resources`, `coords(nodes) -> [[lon, lat], ...]`. `app/graph/loader.load_routing_context` calls `from_graph_data` at startup. |
| `matrix.py` | `build_cost_matrix(routing_graph, profile, point_nodes) -> CostMatrix` (step 4) |
| `solver.py` | `solve(cost_matrix, end_mode, time_limit_s) -> SolverResult` (step 5); `NoFeasibleRoute` when no route exists at all (unreachable fixed end) |
| `assemble.py` | `assemble(routing_graph, query, cost_matrix, solution, capacities=None, reserve_margin=0.0) -> RoutePlan` (step 6); budget warnings only when capacities are passed |
| `service.py` | `plan_route(routing_graph, query, capacities=None, reserve_margin=0.0) -> RoutePlan`: the one function the API (package H) calls |

Notes for package H (API):
- Catch `NoFeasibleRoute` and return a clear error (e.g. HTTP 422 with its message). Dropped stops are not errors.
- `LegOut` labels: `from`/`to` is `"start"`, a destination index (0-based, request order) or `"end"` (fixed end). `Leg.from_point`/`to_point` are CostMatrix point indices: point 0 = `"start"`, point k (1..D) = destination k-1, point D+1 = `"end"`. A round trip's last leg goes `to: "start"`; an open end has no final leg.
- `path`: `{"type": "LineString", "coordinates": routing_graph.coords(plan.nodes)}`. A round trip that visits nothing has a single coordinate.
- `weight`/`total_weight` in the API = `cost`/`total_cost` internally.

### Implementation (package H, API controller, done)
| File | Role |
|---|---|
| `app/api/routes/route.py` | `POST /api/route`: thin controller; login required (401), 503 if the graph is unavailable, 422 for `SnapError`, `RouteRequestError`, `NoFeasibleRoute`; passes the user's body mass to `handle_route_request` |
| `app/routing/request.py` | `handle_route_request`: snap, duplicate check (names the points, e.g. `destination 0 = destination 1`), `plan_route`, `RoutePlan` -> `RouteResponse`; weather `message` of every visited point's cell goes verbatim into `warnings` (only when `season` is given; "unknown" warnings if the cell or the layer is missing) |
| `app/routing/snap.py` | `snap`: nearest valid node, rejects points outside the grid bbox or farther than `Settings.max_snap_distance_m` (1000 m) |
| `app/graph/loader.py` | `load_routing_context(settings)`: `data/graph/graph.npz` -> `RoutingContext` (RoutingGraph + KD-tree over valid nodes); called in the FastAPI lifespan, stored in `app.state.routing` (a `LayerUnavailable` if the file is missing, so only `/api/route` answers 503) |
- `Settings` gained `capacities` ({profile: {resource: capacity}}, empty = no budget warnings until the values are confirmed), `reserve_margin` (0.2), `max_snap_distance_m`, `graph_file`.
- `app/graph/build.py` (package F, writes `graph.npz`) does not exist yet: until it does, `/api/route` returns 503 with a `fix` hint.
- Season: both `/api/get-layer-four` and `/api/route` take the short key (`autumn|winter|spring|summer`); the long names (`S. Winter (Ls 90-180)`) only exist inside the weather data.

### Tests (`backend/tests/routing/`, see section 11)
Use tiny hand-built graphs:
- an ∞-only target (cell stays ∞, no leg path saved)
- an isolated target (missing from the result)
- an asymmetric uphill/downhill pair
- each `end_mode`
- duplicate snapped points (rejected)
- a fixed end that can't be reached (error)
- a total weight that matches the sum of the unscaled legs

## 10a. Authentication (JWT + SQLite)
- **Endpoints:** `POST /api/auth/register` (JSON: `email`, `password` (no length check), `body_mass_kg` 30-250, `birth_year` from 1900 to the current year (no age rule); 201 + user, 409 if the email is taken), `POST /api/auth/login` (OAuth2 password **form**: the email goes in `username`; returns `{access_token, token_type: "bearer"}`; 401 with the same message for an unknown email and a wrong password), `GET /api/users/me` and `PATCH /api/users/me` (Bearer token; PATCH changes only the fields sent).
- **Protected endpoints:** `/api/users/me` and `POST /api/route` (`Depends(get_current_user)`: 401 without a valid token). Layer and tile endpoints stay public.
- **Code:** `app/db/{models,session}.py` (SQLAlchemy 2.x, `User` table, one engine per app on `app.state`, tables created in the lifespan, no migrations yet), `app/auth/{security,service,dependencies}.py` (Argon2 via pwdlib, HS256 tokens via PyJWT with `sub` = user id and `exp`, `get_current_user`), `app/schemas/auth.py`, `app/api/routes/{auth,users}.py`.
- **Config:** `JWT_SECRET_KEY` is required (the app refuses to start without it; `backend/.env.example`). Database: `MARS_DATABASE_URL`, default `sqlite:///<data_dir>/app.db` (gitignored with `data/`). Token lifetime 60 min (`Settings.access_token_expire_minutes`). No refresh tokens, logout, password reset or rate limiting yet.
- **Body mass is used for the astronaut's resource estimates, never for the route.** Body mass cancels in the cost formula, so the path and `total_weight` are the same for everyone. `POST /api/route` loads the requesting user's row (token -> user id -> database) and recomputes oxygen, CO2 and water over the returned path's edges only (`app/routing/profiles/personalize.py`, which calls the same `AstronautModel.resources` the graph builder uses); time and suit energy do not depend on mass. The response reports `body_mass_kg` (null for the car, or when the reference mass was used). If the saved graph was built with other profile parameters than the current models, the reference-mass numbers are kept and a warning says to rebuild with `python -m app.graph`. Birth year is stored but not modelled (no data to calibrate age).

## 11. Development rules (all agents)
These apply to every agent and every change.

1. **One subdirectory per module.** Whenever you create new code, put it in a subdirectory named after the module, and create that directory if it does not exist. Never leave loose files at a package root.
   - Backend: `backend/app/<module>/` with an `__init__.py` (for example `app/graph/`, `app/routing/`, `app/layers/relief/`). `main.py` only wires things together.
   - Frontend: `frontend/src/<area>/<Module>/` (for example `components/RouteLegend/`, `features/map/`).
   - Scripts: `scripts/<module>/`.
2. **Every piece of new code ships with tests, in the same change.**
   - Backend: pytest. Tests mirror the module path: code in `backend/app/<module>/<file>.py` is tested in `backend/tests/<module>/test_<file>.py`. Create `backend/tests/<module>/` (with an `__init__.py`, so equal file names in different modules don't clash) if it does not exist. Run `cd backend && pytest`. If `pytest` is not in `backend/requirements.txt` yet, add it.
   - Frontend: Vitest (+ React Testing Library, jsdom), with the test next to the source as `<Name>.test.jsx`. None is installed yet: the first agent that adds a frontend test also adds the dev dependencies and a `"test": "vitest run"` script in `frontend/package.json`.
   - Scripts: tests in `scripts/<module>/tests/`.
3. **Tests are offline and deterministic.** No network (the project reads static local files only). Use the synthetic fixtures (`app/layers/fakes.py`) and tiny hand-built graphs and arrays. A test that needs the real downloaded data must skip itself when `data/raw/` is missing (`pytest.mark.skipif`), so a fresh clone still passes.
4. **Cover the edge cases named in this skill:** unreachable and isolated stops, `inf` weights, uphill versus downhill asymmetry, missing-data confidence labels, longitude wrap (0-360 versus -180..180), nodata cells.
5. **Run the tests before you finish, and report failures honestly.** Do not mark work done on a red or skipped suite without saying so.
6. **Keep the docs in step with the code.** If a change alters a contract, formula, endpoint or folder, update the matching file in `references/` (or this file) and `AGENTS.md` in the same change.

## 12. Notes for the team: changes from the controller / layer work (2026-11-15)
Read this if you work on the frontend or the graph builder. Details live in `references/layer-ingestion.md` (sections 4-6, 8) and section 10 "Implementation (package H)".

**API contract changes (frontend)**
- `POST /api/route`: `season` takes the short keys `autumn | winter | spring | summer`, the same as `GET /api/get-layer-four?season=`. The long name (`S. Winter (Ls 90-180)`) is rejected with 422. The weather GeoJSON still carries the long name in `properties.season` (and `season_name` in the response); use that for display.
- POI ids are now `<service>:<layer>:<id>`, e.g. `EZMars:3:0` (was `EZMars__3:0`). POI features also carry `kind` (graph-side enum) next to `category` (the API filter).
- Layer 1 sources have an extra field `role` (`primary | fallback | zoom-in detail`).
- Endpoint paths are the implemented ones (`/api/get-layer-one` ... `four`, `/api/tiles/...`), listed in `layer-ingestion.md` section 6.
- `POST /api/route` answers 401 without a valid token, 503 (`detail` + `fix`) until `data/graph/graph.npz` exists; 422 for points outside the graph, farther than `max_snap_distance_m` (1000 m) from a node, snapped to the same node, or an unreachable fixed end. Dropped stops are a normal 200 result.

**Layer structure (graph builder)**
- Every layer has `ingest.py` (raw files -> contract data on the shared grid, validated) and `service.py` (client format; the classes are still called `...Getter`). `app/layers/inputs/load.py: load_all(settings, grid=None)` returns `GraphInputs` and raises `LayerDataError` when data is missing. The graph builder must use only that.
- Shared grid: `app/layers/relief/ingest.py: grid_for(settings)`, the DEM shape divided by `Settings.grid_coarsen` (default 2, about 400 m). The relief overlay shown to users and the slope used for routing are the same array (`ReliefData.slope_deg`). With `grid_coarsen=1` the graph would have ~1.3M nodes.
- Weather data lives in `data/derived/weather/` (built by `python scripts/build_weather/build_weather.py`), not in `data/raw/`.
- Not implemented (optional in the contract): `ReliefData.roughness_m`, `PoiData.nearest_poi_*`.

**Still open**
- Graph builder (`app/graph/build.py`) and the per-profile cost/resource formulas (`app/routing/profiles.py`) do not exist yet.
- `Settings.capacities` is empty (no budget warnings) until the product owner confirms the values.
- Everything is tested against synthetic fixtures only; nobody has run it against the real `data/` yet.
- Use Python >= 3.11 (`enum.StrEnum`).
