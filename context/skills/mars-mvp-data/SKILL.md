---
name: mars-mvp-data
description: Project context, requirements and exact datasets for the Mars astronaut-map MVP: a hyper-local, 4-layer map. It shows base imagery, relief/walkability and points of interest for East Melas Chasma, plus a seasonal dust-storm risk layer on a 1° grid over the wider Valles Marineris area. Use it whenever building, extending or debugging any part of this project: fetching NASA Trek tiles or vectors, computing slopes, querying MDAD storm data, or showing risk and confidence labels. Bundles the working Python scripts (scripts/01-08) as a reference implementation.
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

- Slope classes used so far (**unconfirmed by product owner, keep configurable**): 0–5° easy walk · 5–15° walkable · 15–25° vehicle only · 25–35° hard / vehicle limit · >35° impassable.
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
  - Inputs are fetched live from Trek, ArcGIS and Dataverse; there is nothing to pre-download.
- **Canonical source:** `data-exploration/scripts/`. When a script changes there, re-copy it here (`cp scripts/0*.py context/skills/mars-mvp-data/scripts/`) so other agents don't use stale logic.

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
`python scripts/download_data.py` (deps: `scripts/requirements.txt`) fetches everything the MVP uses into `data/raw/` (gitignored). Re-runs skip existing files; `--force` re-downloads; `--only dem|tiles|pois|mdad` limits it; `--max-zoom N` limits tile volume (default z5-9, ~1,000 tiles, ~46 MB total).

| Layer | Output | Source |
|---|---|---|
| 2 relief values | `data/raw/dem/dem_blend200m_aoi.tif` (float32 m, 1200x1073) | Trek ImageServer, MOLA+HRSC 200 m |
| 1, 2, 3 imagery | `data/raw/tiles/<label>/<z>/<row>/<col>.png\|jpg` | Trek WMTS: Coprates mosaic, CTX global, HiRISE, colour hillshade, CTX hillshade, CRISM polysulfate |
| 3 POIs | `data/raw/features/<service>__<layerId>.geojson` | Trek ArcGIS MapServers (empty layers are not written) |
| 4 weather input | `data/raw/mdad/MDAD_original` | Harvard Dataverse file 3607412 |
| log | `data/raw/manifest.json` | counts per dataset |

- Tile row/col are WMTS indices with a top-left origin (same as XYZ rows). Read `TileWidth` per layer: 512 px for CTX global and HiRISE, 256 px for the rest.
- A few tiles are genuinely unavailable (e.g. 3 tiles of the CTX global mosaic return HTTP 500). They are reported as `unavailable`/`missing`, not failures.
- The delivered weather layer (`context_weather_frames.geojson`) is derived from the MDAD file by skill scripts 06 -> 07; the download script only fetches the input.

## 9. Application architecture (decided)

### Principles
- **The frontend consumes only our FastAPI backend.** It never calls NASA Trek, Harvard Dataverse or any other source directly. The backend owns the response format of every layer so that datasets from different sources look uniform to the client.
- **Hybrid data strategy.** At build time `scripts/download_data.py` fetches everything into `data/raw/` (the only step that touches the network). At runtime the backend reads local files only. An optional tile proxy with a disk cache may cover zooms that were not pre-fetched. Reasons: Trek returns HTTP 500 on some tiles, demo-venue wifi is unreliable, the graph must be built from identical data every time, and MDAD has no query API (weather is computed locally).
- **Single source of truth for relief.** The slope overlay shown to users and the slope used by the router must come from the same array.

### Backend (FastAPI)
- Four independent layer endpoints (base imagery, relief, points of interest, weather) plus one route endpoint. Planned: `POST /route` with start, end, mode (`walker` | `vehicle`) and season; it returns a polyline, stats and warnings (including the `message` of any `approximate` or `insufficient_data` frame the route crosses).
- **Layer getter module** (`backend/app/layers/<layer>/`): one getter per layer with a common interface (for example `sample(lon, lat)` and `cells(bbox)`). Elevation and slope come from the DEM array held in memory, points of interest from a spatial index, weather from a season lookup. Imagery is tile-serving only; the graph does not use it.
- **Master graph** (`backend/app/graph/`): nodes carry elevation, slope class, nearby points of interest, and the four seasonal risk values with their confidence. **Season is a query parameter, not part of the graph.** Use an implicit grid held in numpy arrays and A*, not a `networkx` object. Native DEM is 200 m (~1.3M nodes over the AOI); start coarsened to ~400 m (~330k nodes), configurable. Persist the built graph under `data/graph/` (gitignored).
- **Routing engine** (`backend/app/routing/`): cost models per mode. Slope classes (0-5 easy, 5-15 walkable, 15-25 vehicle only, 25-35 hard/vehicle limit, >35 impassable) are unconfirmed by the product owner, so keep them configurable.
- **Caveats for routing:** weather risk is almost uniform inside the AOI (1 deg cells within +-10 %), so it acts as a season-wide penalty or warning, not a route discriminator. The 200 m DEM underestimates local slope.
- **Tiles** (`backend/app/tiles/`): serve `data/raw/tiles/<label>/<z>/<row>/<col>.<ext>` and the optional cache-proxy fallback.

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
context/skills/mars-mvp-data/   this skill (SKILL.md, scripts/01-08, requirements.txt)
.claude/skills                  symlink -> ../context/skills
scripts/download_data.py        data pipeline (build time); scripts/requirements.txt
data/raw/                       downloaded datasets (gitignored): dem/, tiles/, features/, mdad/, manifest.json
backend/
  main.py                       starter app (will probably move to app/main.py)
  app/api/routes/               one router per endpoint group
  app/core/                     config, settings
  app/schemas/                  client-facing response models
  app/layers/{base_imagery,relief,poi,weather}/   layer getters
  app/tiles/                    tile serving + optional cache proxy
  app/graph/                    master graph builder/loader
  app/routing/                  routing engine, cost models
  tests/
frontend/src/
  api/                          the only place that talks to the backend
  components/                   shared UI
  features/{map,layers,route}/  Leaflet map, layer toggles/season switcher, route UI
  hooks/, config/, utils/
```
The new folders are empty (`.gitkeep`); no application code exists yet beyond the starters.
