# Layer ingestion contract

Status (2026-11-14):
- **Decided:** each layer has an ingestion module that turns `data/raw/` files into normalised, validated data aligned to one shared grid. The master graph builder consumes only that output and never reads `data/raw/` itself.
- **Proposed:** names, field lists and endpoint paths below. Treat them as the starting contract. Change one only by editing this file in the same PR.

Purpose: let every module be built **in parallel**. The contract plus synthetic fixtures means nobody waits for another module.

Parent doc: `../SKILL.md` sections 5, 9, 10. Graph side: `edge-cost-model.md`.

## 1. Where it sits

```
data/raw/ (static files)
   |  app/layers/<layer>/ingest.py     read + normalise + validate, aligned to GridSpec
   v
LayerData (in memory)                  RELIEF, POI, WEATHER (+ imagery catalog)
   |-- app/graph/build.py              GraphInputs -> master graph (offline) -> data/graph/graph.npz
   |-- app/layers/<layer>/service.py   client-facing format -> app/api/routes -> React
```

Every layer module has two halves:
- **`ingest.py`**: raw files -> `LayerData` for the graph. Pure and deterministic.
- **`service.py`**: the client-facing format (tiles, GeoJSON, PNG). Response models go in `app/schemas/`. Routers in `app/api/routes/` only call `service.py`.

## 2. Conventions (all layers)

- **Static local files only.** Read `data/raw/` and nothing else. No network, no proxy.
- **CRS:** geographic lon/lat on the Mars 2000 sphere, `R = 3,396,190 m` (IAU2000:104905). **Longitude is -180..180**; normalise 0-360 values at ingestion.
- **Units:** SI. Metres, degrees, seconds. Names carry the unit (`elev_m`, `slope_deg`).
- **Arrays:** shape `(nrows, ncols)` from the `GridSpec`; **row 0 is the north row** (raster order, like the DEM and the tiles); `float32` unless stated. Nodata is `NaN` plus an explicit `valid` mask where relevant.
- **Errors:** raise `LayerDataError(layer, message)`. A missing file says "run `python scripts/download_data.py`".
- **Data-sufficiency pass-through (mandatory):** never drop confidence information. Weather `confidence` and `message` travel with the data.
- **Provenance:** each `LayerData` carries `source_files` (relative paths + sha256) so the graph loader can detect stale graphs.
- Ingestion should run in seconds; no intermediate cache is needed.

## 3. `GridSpec` (shared by everything)

The one grid every layer is resampled to and the graph is built on.

| Field | Meaning |
|---|---|
| `west, south, east, north` | bbox in degrees (default: the AOI, `-71.8, -13.4, -68.0, -10.0`) |
| `ncols, nrows` | cell counts |
| `radius_m` | 3,396,190 |
| derived | `dlon`, `dlat` (deg/cell), `shape`, `n_nodes` |

Helpers: `node_id(row, col) = row * ncols + col` and its inverse, `lonlat_center(row, col)`, `lonlat_to_rc(lon, lat)`, `contains(lon, lat)`, `metric_spacing()` (dx, dy in m at each row).

Default grid: the 200 m DEM (1200 x 1073) coarsened by a factor of 2 (about 400 m, ~330k nodes). Configurable (`GridSpec.from_dem(path, coarsen=2)`). Nodes sit at cell centres.

## 4. Per-layer contract

### Relief (`app/layers/relief/`)
- Reads: `data/raw/dem/dem_blend200m_aoi.tif` (float32 m, nodata -32767 or NaN).
- `ReliefData`: `grid`, `elev_m` float32 (NaN = nodata), `valid` bool, `slope_deg` float32 (node slope), optional `roughness_m` float32 (std-dev of elevation in a 3x3 window).
- Resample to the grid with a NaN-aware block mean. Compute `slope_deg` **once**, from the resampled `elev_m` with central differences using the metric spacing. The graph builder derives signed edge gradients from the same `elev_m`. Display slope and routing slope therefore share one source.
- Caveat: at 200-400 m the slope underestimates local steepness.
- Service: slope-class overlay PNG + bounds (classes from config: 0-5 easy walk, 5-15 walkable, 15-25 vehicle only, 25-35 hard, >35 impassable), elevation at a point, hillshade tiles (served like imagery).

### Points of interest (`app/layers/poi/`)
- Reads: `data/raw/features/*.geojson` (see SKILL.md section 5, Layer 3).
- `PoiData.features: list[PoiFeature]`. `PoiFeature`: `id` (stable, `<service>:<layer_id>:<objectid-or-index>`), `kind` (enum: `rsl`, `mineral_sulfate`, `mineral_silica`, `mineral_hydrous`, `dune_field`, `exploration_zone`, `exploration_roi`, `crism_site`, `nomenclature`, `geology_unit`), `name` (optional), `geometry` (GeoJSON Point or Polygon, lon -180..180), `source` (`service/layer`), `properties` (raw attributes, trimmed).
- Optional node attributes for the graph: `nearest_poi_dist_m` float32, `nearest_poi_id` int32 (index into `features`, -1 = none). Not required by routing in the MVP (destinations are user clicks).
- Service: GeoJSON FeatureCollection, filter by `kind`.
- Shelter candidates (pits/depressions from the DEM) are not implemented; reserve `kind = "shelter_candidate"`.

### Weather (`app/layers/weather/`)
- Reads: `data/raw/weather/context_weather_frames.geojson` (1 deg cells x 4 seasons). **This file is not produced by the download script yet.** Until that decision lands (copy from `data-exploration/outputs/weather/` or run skill scripts 06 -> 07), develop against `fake_weather` or a copy of that file.
- `WeatherData`: `seasons` (the four exact strings, fixed order: `S. Autumn (Ls 0-90)`, `S. Winter (Ls 90-180)`, `S. Spring (Ls 180-270, perihelion)`, `S. Summer (Ls 270-360)`), `risk` int8 `(4, nrows, ncols)` (0 Low, 1 Moderate, 2 High, -1 no estimate), `confidence` int8 `(4, nrows, ncols)` (0 reliable, 1 approximate, 2 insufficient_data), `frame_idx` int32 `(nrows, ncols)` into `frames`, `frames` (one record per 1 deg cell with the full per-season frame fields from SKILL.md section 6, including `message`), `caveat` (the global caveat string).
- `risk` is the **display risk**: `typical_year_risk`, else `risk`, else `neighbour_estimate.risk`, else -1.
- `frame_at(lon, lat, season) -> WeatherFrame` for warnings.
- Season never enters edge weights; these arrays only back warnings and node attributes.
- Service: GeoJSON filtered by `season`, properties `display_risk`, `confidence`, `message`; top-level `caveat`. The UI renders `message` verbatim.

### Base imagery (`app/layers/base_imagery/`)
- Reads: `data/raw/tiles/<label>/<z>/<row>/<col>.<ext>`.
- Not an input to the graph. `ImageryCatalog`: per layer `id`, `label`, `role`, `tile_size` (512 for CTX global and HiRISE, else 256), `ext`, `min_zoom`, `max_zoom`, `bounds`, and `tile_path(layer_id, z, row, col) -> Path | None`.
- Service: tile bytes (404 or transparent tile when missing) + a catalog JSON the frontend uses to build its layer list.

## 5. What the graph builder receives

```python
class GraphInputs:        # produced by app.layers.load_all(grid)
    grid: GridSpec
    relief: ReliefData
    weather: WeatherData
    poi: PoiData
```

`app/graph/build.py` imports only `GridSpec`, `GraphInputs` and the profile functions. It never opens a file under `data/raw/`.

## 6. Proposed API endpoints (frontend and backend agree on these)

| Endpoint | Returns |
|---|---|
| `GET /api/layers` | catalog: layers, tile sizes, zoom ranges, bounds, season names |
| `GET /api/layers/imagery/{layer_id}/{z}/{row}/{col}` | tile image |
| `GET /api/layers/relief/hillshade/{z}/{row}/{col}` | tile image |
| `GET /api/layers/relief/slope-overlay` | PNG + `bounds` (or JSON with a data URL) |
| `GET /api/layers/relief/elevation?lon=&lat=` | `{elev_m, slope_deg}` |
| `GET /api/layers/poi?kind=` | GeoJSON |
| `GET /api/layers/weather?season=` | GeoJSON + `caveat` |
| `POST /api/route` | SKILL.md section 10 |

All coordinates in responses are lon/lat (-180..180). Pydantic models in `app/schemas/`.

## 7. Fixtures and validation (what unblocks parallel work)

**Implemented (step 0 done, 67 passing tests in `backend/tests/`).** Import these; do not redefine them:
- `app/layers/contracts.py`: `GridSpec` (+ `default_grid()`, `from_bbox`), `ReliefData`, `PoiData`, `PoiFeature`, `WeatherData`, `WeatherFrame`, `ImageryCatalog`, `ImageryLayerInfo`, `GraphInputs`, enums `RiskLevel`, `Confidence`, `PoiKind`, `SEASONS`, `LayerDataError`.
- `app/layers/fakes.py`: `fake_grid`, `fake_relief(grid, kind="flat|ramp|bowl|ridge|cliff")`, `fake_weather`, `fake_poi`, `fake_inputs`.
- `app/layers/validate.py`: `validate_relief`, `validate_poi`, `validate_weather`, `validate_inputs`.
- `app/layers/relief/slope.py`: `slope_deg(elev_m, grid)`, the one slope implementation.
- `app/core/resources.py`: `ProfileId`, `EDGE_ATTRS`, `UNITS`, `attr_key`.
- `app/core/profiles.py`: `EdgeGeometry`, `ProfileModel` protocol, `check_edge_attrs` (the graph builder <-> profile formulas interface).
- `app/graph/contracts.py`: `GraphData` (struct-of-arrays graph, `edge_attrs(edge_id)` logical view, `save`/`load` to `graph.npz`).
- `app/routing/contracts.py`: `RouteQuery`, `CostMatrix`, `SolverResult`, `Leg`, `RoutePlan`, `RouteLimits`, `EndMode`, `DropReason` (hand-offs between request, matrix, solver and assembly).
- `app/schemas/route.py`, `app/schemas/layers.py`: the API models.

Every ingestion module's definition of done: its real `ingest` passes `validate_*` on the real data, its output type is identical to the fake's, and it ships with tests in `backend/tests/layers/<layer>/` (offline; tests that need the real data skip when `data/raw/` is missing). See SKILL.md section 11.

## 8. Work packages (all can start immediately after step 0)

| Package | Depends on | Develops against |
|---|---|---|
| 0. contracts + fakes + validators + `app/core/resources.py` | **done** | |
| A. relief ingest + service | 0 | real DEM |
| B. poi ingest + service | 0 | real features |
| C. weather ingest + service | 0 | copy of the weather GeoJSON or `fake_weather` |
| D. imagery catalog + tile service | 0 | real tiles |
| E. profile cost/resource functions (`compute_edge_attrs`) | 0 | pure arrays, no layers |
| F. graph builder, saver, loader | 0, E | `fake_inputs` |
| G. routing matrix, solver, assembly | 0 | tiny hand-built graphs |
| H. API routers + schemas | 0 | fakes |
| I. frontend | endpoint table above | mocked JSON |

Integration happens when A-D replace the fakes in `load_all`.
