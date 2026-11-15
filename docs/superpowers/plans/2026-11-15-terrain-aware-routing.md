# Terrain-Aware Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `POST /api/route` build start→end (and multi-stop) routes that respect the map's slope classes, avoid POI hazards (dune fields, RSL sites), penalise rough terrain, and choose walking or driving automatically (least oxygen per person), while still letting the user force a mode.

**Architecture:** All terrain and hazard rules are baked into the precomputed per-profile edge `cost` of the master graph, so routing stays one SciPy Dijkstra per point. The graph builder derives per-edge terrain fields (map slope of both end cells, roughness, dune/RSL flags rasterised from POIs) and hands them to each profile's cost formula. At request time, points snap to nodes the chosen profile can actually use. `profile: "auto"` (the new default) runs both profiles and picks one with a pure, tested selection rule. A request with only `start` + `end` is a point-to-point route.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, NumPy, SciPy (`csgraph.dijkstra`, `cKDTree`), Shapely 2.2 (`shapely.contains_xy`), OR-Tools, pytest.

---

## Context

The pulled code already has a working routing engine (`backend/app/routing/`, `backend/app/graph/`): a 200 m grid graph (1.29 M nodes, 10.3 M edges), two profiles (`astronaut`, `car`) with Tobler/Minetti and traction cost formulas, hard slope limits of 20° and 25°, and OR-Tools for stop order. 421 unit tests pass. What's wrong or missing:

1. **The slope rule doesn't match the map.** An edge is blocked only by its *travel* gradient (`dz/d` along the step). Walking along the contour of a 30° hillside has dz≈0, so the router walks through cells the map paints "Impassable". AGENTS.md requires the slope shown and the slope routed to come from the same array, and the Artemis 20° limit covers walking "up/down/across" a slope. On the real DEM, map-slope blocking closes 8.5% of the cells to walking and 3.8% to the car.
2. **Only elevation feeds the cost.** Dune fields (5 polygons in the demo area) and RSL sites (3 points) are display-only, and `ReliefData.roughness_m` is never computed.
3. **The user must pick the mode.** Nothing chooses between walking and driving.
4. **No plain start→end request.** It needs `destinations=[end]` and `end_mode=open`.

Decisions taken with the user:
- Hazards: dunes block the car and slow walking (×1.5); RSL sites block both profiles within a configurable buffer (500 m placeholder); roughness raises the cost of both, more for the car.
- Mode: `profile` takes `"auto"` (default), `"astronaut"` or `"car"`. Auto picks the profile that reaches the most destinations, then the one with **less oxygen per person**, then the faster one.
- Backend only (no frontend work).

Known consequence to tell the product owner: with the placeholder parameters, the rover's crew uses roughly 6 g O2 per person over 2.4 km of flat ground against about 86 g for a walker. Auto will therefore choose the car whenever the car can reach the points.

Out of scope: weather in the cost (it stays warnings-only, by design); frontend; showing hazards in `/api/get-layer-two/point`; resource changes from roughness or dunes (no calibrated data, so only `cost` changes).

## Conventions for every task

- Work in `NASA-space-apps-mars-map/` (the git repo). Backend commands run from `NASA-space-apps-mars-map/backend` with `.venv/bin/python -m pytest …`.
- New code goes in a subdirectory named after its module, with `__init__.py` (AGENTS.md rule). Tests mirror the module path under `backend/tests/`.
- Tests are offline: fakes from `app/layers/fakes.py` and tiny graphs from `tests/routing/helpers.py`.
- When a step says "add these imports at the top if missing", merge them into the file's existing import block.

## File map

| File | Change | Responsibility |
|---|---|---|
| `backend/app/layers/relief/roughness.py` | create | `roughness_m(elev)`: deviation from the local plane |
| `backend/app/layers/relief/ingest.py` | modify | fill `ReliefData.roughness_m` |
| `backend/app/graph/hazards/{__init__,masks}.py` | create | `hazard_masks(grid, poi, rsl_buffer_m) -> HazardMasks` (dune / RSL cell masks) |
| `backend/app/core/profiles.py` | modify | `EdgeGeometry` gains `terrain_slope_deg`, `dune`, `rsl` |
| `backend/app/graph/geometry.py` | modify | per-edge terrain fields from grids |
| `backend/app/routing/profiles/params.py` | modify | roughness and hazard parameters per profile |
| `backend/app/routing/profiles/terrain.py` | create | shared terrain terms: effective slope, roughness, dune factor, hazard blocking |
| `backend/app/routing/profiles/{astronaut,car}.py` | modify | use the terrain terms; formula version 2 |
| `backend/app/graph/build.py` | modify | `BuildConfig.rsl_buffer_m`; pass slope + masks to geometry |
| `backend/app/core/config.py`, `app/core/configfile/loader.py`, `config/mars.yaml` | modify | `hazards.rsl_buffer_m`, new profile keys, confirmation entry |
| `backend/app/graph/startup/prepare.py`, `app/graph/cli.py` | modify | pass `rsl_buffer_m` from settings |
| `backend/app/graph/loader.py`, `app/routing/snap.py` | modify | per-profile KD-trees; snap to nodes the profile can use |
| `backend/app/routing/contracts.py`, `app/routing/service.py`, `app/schemas/route.py` | modify | point-to-point; `profile: auto`; `ModeSelection` in the response |
| `backend/app/routing/modes/{__init__,select}.py` | create | `choose(outcomes)`: the auto rule and its explanation |
| `backend/app/routing/request.py` | modify | run one or both profiles, attach `mode` |
| docs: `context/skills/mars-mvp-data/SKILL.md`, `references/edge-cost-model.md`, `references/layer-ingestion.md`, `AGENTS.md`, `README.md` | modify | contract and formula changes |

---

### Task 0: Branch and save the plan

- [ ] **Step 1: Branch from the current dev**

```bash
cd /Users/sielprar/PycharmProjects/NASA/NASA-space-apps-mars-map
git status --short   # expect clean; if not, stop and ask the user
git checkout -b feature/terrain-aware-routing
```

- [ ] **Step 2: Copy this plan into the repo and commit**

```bash
mkdir -p docs/superpowers/plans
cp /Users/sielprar/.claude/plans/i-pulled-last-version-hidden-nebula.md docs/superpowers/plans/2026-11-15-terrain-aware-routing.md
git add docs/superpowers/plans/2026-11-15-terrain-aware-routing.md
git commit -m "docs: plan for terrain-aware routing"
```

---

### Task 1: Terrain roughness from the DEM

**Files:**
- Create: `backend/app/layers/relief/roughness.py`
- Modify: `backend/app/layers/relief/ingest.py` (the `ReliefData(...)` call in `ingest_relief`)
- Test: `backend/tests/layers/relief/test_roughness.py`, `backend/tests/layers/relief/test_ingest.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/layers/relief/test_roughness.py`:
```python
import numpy as np

from app.layers.relief.roughness import roughness_m


def test_any_plane_has_zero_roughness_however_steep():
    rows, cols = np.mgrid[0:6, 0:7]
    plane = (50.0 * cols - 30.0 * rows + 1000.0).astype(np.float32)
    assert np.allclose(roughness_m(plane), 0.0, atol=1e-3)


def test_a_bump_is_rough_and_its_neighbours_half_as_much_on_one_axis():
    z = np.zeros((5, 5), dtype=np.float32)
    z[2, 2] = 10.0
    r = roughness_m(z)
    assert r[2, 2] == np.float32(10.0)
    # north neighbour: north/south pair deviates by 5, west/east pair by 0 -> mean 2.5
    assert r[1, 2] == np.float32(2.5) and r[0, 0] == 0.0


def test_nodata_stays_nan_and_a_cell_without_a_full_neighbour_pair_is_zero():
    z = np.array([[1.0, np.nan], [np.nan, np.nan]], dtype=np.float32)
    r = roughness_m(z)
    assert r[0, 0] == 0.0 and np.isnan(r[0, 1]) and np.isnan(r[1, 0]) and np.isnan(r[1, 1])
    assert r.dtype == np.float32
```

Append to `backend/tests/layers/relief/test_ingest.py`:
```python
def test_ingest_computes_roughness_on_the_same_grid(fixture_settings):
    d = ingest_relief(fixture_settings)
    assert d.roughness_m is not None and d.roughness_m.dtype == np.float32
    assert d.roughness_m.shape == d.grid.shape
    assert (np.isnan(d.roughness_m) == ~d.valid).all() and (d.roughness_m[d.valid] >= 0).all()
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/layers/relief/test_roughness.py tests/layers/relief/test_ingest.py -v`
Expected: FAIL, with `ModuleNotFoundError: No module named 'app.layers.relief.roughness'` and `roughness_m is not None` assertion.

- [ ] **Step 3: Implement `roughness.py`**

```python
"""Terrain roughness from the elevation grid: how far each cell sits from the plane through its neighbours.

For each axis (north/south, west/east) whose two neighbours both have data, the deviation is
mean(neighbour pair) - z; roughness_m is the absolute mean of those deviations (0 when no axis has a full
pair). It is 0 on any plane, however steep, so it measures bumps, pits, ridges and breaks in slope, not slope
itself (slope is already in the cost). On the 200 m DEM of the demo area 90 % of cells are below ~3 m.
"""
from __future__ import annotations

import numpy as np


def roughness_m(elev_m: np.ndarray) -> np.ndarray:
    """float32, same shape as elev_m; NaN exactly where elev_m is NaN."""
    z = np.asarray(elev_m, dtype=np.float64)
    p = np.pad(z, 1, constant_values=np.nan)
    pairs = ((p[:-2, 1:-1], p[2:, 1:-1]), (p[1:-1, :-2], p[1:-1, 2:]))  # (north, south), (west, east)
    deviation = np.zeros_like(z)
    n_axes = np.zeros_like(z)
    for a, b in pairs:
        both = ~np.isnan(a) & ~np.isnan(b)
        deviation += np.where(both, (a + b) / 2.0 - z, 0.0)
        n_axes += both
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(n_axes > 0, np.abs(deviation / n_axes), 0.0)
    out[np.isnan(z)] = np.nan
    return out.astype(np.float32)
```

- [ ] **Step 4: Fill it in during ingestion**

In `backend/app/layers/relief/ingest.py` add `from app.layers.relief.roughness import roughness_m` and change the `ReliefData(...)` call to:
```python
    data = ReliefData(
        grid=grid, elev_m=elev, valid=valid, slope_deg=slope_deg(elev, grid), roughness_m=roughness_m(elev),
        source_files=(f"{path.relative_to(settings.raw_dir).as_posix()}:{hashlib.sha256(path.read_bytes()).hexdigest()}",),
    )
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/bin/python -m pytest tests/layers/relief tests/graph/test_nodes_build.py -v`
Expected: PASS. `test_node_table_has_required_and_per_season_arrays` still asserts `"roughness_m" not in node` for the *fake* inputs, whose `fake_relief` keeps `roughness_m=None`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/layers/relief/roughness.py backend/app/layers/relief/ingest.py backend/tests/layers/relief/
git commit -m "feat(relief): compute terrain roughness during ingestion"
```

---

### Task 2: Hazard masks from POIs

**Files:**
- Create: `backend/app/graph/hazards/__init__.py`, `backend/app/graph/hazards/masks.py`
- Test: `backend/tests/graph/hazards/__init__.py` (empty), `backend/tests/graph/hazards/test_masks.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/graph/hazards/test_masks.py`:
```python
import numpy as np
import pytest

from app.graph.hazards import HazardMasks, hazard_masks
from app.layers.contracts import PoiData, PoiFeature, PoiKind
from app.layers.fakes import fake_grid

GRID = fake_grid(10, 10)


def feature(kind, geometry, i=0):
    return PoiFeature(id=f"t:0:{i}", kind=kind, geometry=geometry, source="t/0")


def centre(row, col):
    return float(GRID.lon_centers()[col]), float(GRID.lat_centers()[row])


def test_dune_polygon_covers_the_cells_whose_centre_is_inside():
    mid = (GRID.west + GRID.east) / 2  # the boundary between columns 4 and 5
    ring = [[GRID.west - 0.01, GRID.south - 0.01], [mid, GRID.south - 0.01], [mid, GRID.north + 0.01],
            [GRID.west - 0.01, GRID.north + 0.01], [GRID.west - 0.01, GRID.south - 0.01]]
    masks = hazard_masks(GRID, PoiData((feature(PoiKind.DUNE_FIELD, {"type": "Polygon", "coordinates": [ring]}),)), 0)
    assert masks.dune[:, :5].all() and not masks.dune[:, 5:].any() and not masks.rsl.any()


def test_rsl_buffer_covers_cells_within_the_radius():
    _, dy = GRID.metric_spacing()
    lon, lat = centre(5, 5)
    poi = PoiData((feature(PoiKind.RSL, {"type": "Point", "coordinates": [lon, lat]}),))
    assert hazard_masks(GRID, poi, 0).rsl.sum() == 1 and hazard_masks(GRID, poi, 0).rsl[5, 5]
    wide = hazard_masks(GRID, poi, 1.5 * dy).rsl  # the 3 x 3 block (diagonal ~1.4 cells), not the next ring
    assert wide.sum() == 9 and wide[4:7, 4:7].all()


def test_other_kinds_and_point_dunes_make_no_hazard():
    lon, lat = centre(2, 2)
    poi = PoiData((feature(PoiKind.MINERAL_SULFATE, {"type": "Point", "coordinates": [lon, lat]}, 0),
                   feature(PoiKind.DUNE_FIELD, {"type": "Point", "coordinates": [lon, lat]}, 1)))
    masks = hazard_masks(GRID, poi, 10_000)
    assert not masks.dune.any() and not masks.rsl.any()


def test_empty_masks_and_negative_buffer():
    empty = HazardMasks.empty(GRID)
    assert empty.dune.shape == GRID.shape and empty.dune.dtype == bool and not empty.rsl.any()
    with pytest.raises(ValueError, match="rsl_buffer_m"):
        hazard_masks(GRID, PoiData(()), -1)
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/graph/hazards -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.graph.hazards'`.

- [ ] **Step 3: Implement**

`backend/app/graph/hazards/__init__.py`:
```python
"""Grid cells covered by POI hazards (dune fields, RSL sites), derived by the graph builder from GraphInputs.poi."""
from app.graph.hazards.masks import HazardMasks, hazard_masks

__all__ = ["HazardMasks", "hazard_masks"]
```

`backend/app/graph/hazards/masks.py`:
```python
"""Hazard masks: which grid cells a POI hazard covers (edge-cost-model.md section 4a).

Dune fields (Polygon / MultiPolygon) cover the cells whose centre lies inside them; point-only dune features
have no area and are ignored. RSL sites cover every cell whose centre lies within `rsl_buffer_m` of the site's
representative point. Computed from GraphInputs.poi, never from data/raw/.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import shapely
from shapely.geometry import shape

from app.layers.contracts import GridSpec, PoiData, PoiKind

_AREAS = ("Polygon", "MultiPolygon")


@dataclass(frozen=True, eq=False)
class HazardMasks:
    dune: np.ndarray  # bool (nrows, ncols)
    rsl: np.ndarray  # bool (nrows, ncols)

    @classmethod
    def empty(cls, grid: GridSpec) -> "HazardMasks":
        return cls(dune=np.zeros(grid.shape, dtype=bool), rsl=np.zeros(grid.shape, dtype=bool))


def _area_mask(grid: GridSpec, geometries: Iterable[dict]) -> np.ndarray:
    lon, lat = grid.node_lonlat()
    mask = np.zeros(grid.n_nodes, dtype=bool)
    for geometry in geometries:
        mask |= shapely.contains_xy(shape(geometry), lon, lat)
    return mask.reshape(grid.shape)


def _buffer_mask(grid: GridSpec, points: Iterable[tuple[float, float]], radius_m: float) -> np.ndarray:
    lon, lat = grid.node_lonlat()
    m_per_deg = np.radians(1.0) * grid.radius_m
    mask = np.zeros(grid.n_nodes, dtype=bool)
    for p_lon, p_lat in points:
        dx = (lon - p_lon) * np.cos(np.radians(p_lat)) * m_per_deg
        dy = (lat - p_lat) * m_per_deg
        mask |= dx * dx + dy * dy <= radius_m * radius_m
    return mask.reshape(grid.shape)


def hazard_masks(grid: GridSpec, poi: PoiData, rsl_buffer_m: float) -> HazardMasks:
    if rsl_buffer_m < 0:
        raise ValueError(f"rsl_buffer_m must be >= 0, got {rsl_buffer_m}")
    dunes = [f.geometry for f in poi.features if f.kind == PoiKind.DUNE_FIELD and f.geometry.get("type") in _AREAS]
    rsl = [f.lonlat() for f in poi.features if f.kind == PoiKind.RSL]
    return HazardMasks(dune=_area_mask(grid, dunes), rsl=_buffer_mask(grid, rsl, rsl_buffer_m))
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/python -m pytest tests/graph/hazards -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/hazards backend/tests/graph/hazards
git commit -m "feat(graph): rasterise dune fields and RSL buffers into hazard masks"
```

---

### Task 3: Terrain fields on the edge geometry

**Files:**
- Modify: `backend/app/core/profiles.py` (`EdgeGeometry`)
- Modify: `backend/app/graph/geometry.py` (`edge_geometry`)
- Test: `backend/tests/core/test_profiles.py`, `backend/tests/graph/test_geometry.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/core/test_profiles.py` (add `import numpy as np`, `import pytest`, `from app.core.profiles import EdgeGeometry` at the top if missing):
```python
def test_terrain_fields_default_to_none_and_are_validated():
    g = EdgeGeometry(d_m=np.array([1.0, 2.0]), dz_m=np.zeros(2))
    assert g.terrain_slope_deg is None and g.dune is None and g.rsl is None
    g = EdgeGeometry(d_m=np.array([1.0, 2.0]), dz_m=np.zeros(2), terrain_slope_deg=[3, 40], dune=[0, 1], rsl=[1, 0])
    assert g.terrain_slope_deg.dtype == np.float64 and g.dune.dtype == bool and g.dune.tolist() == [False, True]
    with pytest.raises(ValueError, match="terrain_slope_deg"):
        EdgeGeometry(d_m=np.array([1.0]), dz_m=np.zeros(1), terrain_slope_deg=[95.0])
    with pytest.raises(ValueError, match="dune"):
        EdgeGeometry(d_m=np.array([1.0]), dz_m=np.zeros(1), dune=[True, False])
```

Append to `backend/tests/graph/test_geometry.py` (add `import numpy as np`, `import pytest`, `from app.graph.geometry import edge_geometry`, `from app.layers.fakes import fake_grid` at the top if missing):
```python
def test_terrain_fields_take_the_steeper_end_and_a_hazard_at_either_end():
    g = fake_grid(1, 4)
    elev = np.zeros(g.shape, dtype=np.float32)
    slope = np.array([[5.0, 30.0, 0.0, 7.0]], dtype=np.float32)
    dune = np.array([[False, True, False, False]])
    rsl = np.array([[False, False, False, True]])
    geom = edge_geometry(g, elev, np.array([0, 2, 3]), np.array([1, 3, 2]), slope_deg=slope, dune=dune, rsl=rsl)
    assert geom.terrain_slope_deg.tolist() == [30.0, 7.0, 7.0]
    assert geom.dune.tolist() == [True, False, False]
    assert geom.rsl.tolist() == [False, True, True]


def test_terrain_fields_are_optional_and_checked_against_the_grid():
    g = fake_grid(1, 3)
    elev = np.zeros(g.shape, dtype=np.float32)
    geom = edge_geometry(g, elev, np.array([0]), np.array([1]))
    assert geom.terrain_slope_deg is None and geom.dune is None and geom.rsl is None
    with pytest.raises(ValueError, match="slope_deg shape"):
        edge_geometry(g, elev, np.array([0]), np.array([1]), slope_deg=np.zeros((2, 2), np.float32))
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/core/test_profiles.py tests/graph/test_geometry.py -v`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'terrain_slope_deg'` / `'slope_deg'`.

- [ ] **Step 3: Extend `EdgeGeometry`**

In `backend/app/core/profiles.py`, replace the class docstring, fields and `__post_init__` of `EdgeGeometry` with (keep `__len__` and the properties as they are):
```python
@dataclass(frozen=True, eq=False)
class EdgeGeometry:
    """Geometry and terrain of m directed edges u -> v (signed: uphill and downhill differ).

    d_m: horizontal distance (> 0). dz_m = elev[v] - elev[u]. roughness_m optional (at v).
    terrain_slope_deg optional: the larger map slope (ReliefData.slope_deg) of the two end cells.
    dune / rsl optional (bool): either end cell lies in a dune field / within an RSL site's buffer.
    """

    d_m: np.ndarray
    dz_m: np.ndarray
    roughness_m: np.ndarray | None = None
    terrain_slope_deg: np.ndarray | None = None
    dune: np.ndarray | None = None
    rsl: np.ndarray | None = None

    def __post_init__(self):
        d = np.asarray(self.d_m, dtype=np.float64)
        dz = np.asarray(self.dz_m, dtype=np.float64)
        if d.ndim != 1 or d.shape != dz.shape:
            raise ValueError("d_m and dz_m must be 1-D arrays of the same length")
        if not (np.isfinite(d).all() and (d > 0).all()):
            raise ValueError("d_m must be finite and > 0")
        if not np.isfinite(dz).all():
            raise ValueError("dz_m must be finite (drop edges that touch nodata cells)")
        rough = None
        if self.roughness_m is not None:
            rough = np.asarray(self.roughness_m, dtype=np.float64)
            if rough.shape != d.shape:
                raise ValueError("roughness_m must have the same length as d_m")
        terrain = None
        if self.terrain_slope_deg is not None:
            terrain = np.asarray(self.terrain_slope_deg, dtype=np.float64)
            if terrain.shape != d.shape:
                raise ValueError("terrain_slope_deg must have the same length as d_m")
            if not np.isfinite(terrain).all() or (terrain < 0).any() or (terrain > 90).any():
                raise ValueError("terrain_slope_deg must be finite and within 0..90")
        flags = {}
        for name in ("dune", "rsl"):
            value = getattr(self, name)
            if value is not None:
                value = np.asarray(value, dtype=bool)
                if value.shape != d.shape:
                    raise ValueError(f"{name} must have the same length as d_m")
            flags[name] = value
        object.__setattr__(self, "d_m", d)
        object.__setattr__(self, "dz_m", dz)
        object.__setattr__(self, "roughness_m", rough)
        object.__setattr__(self, "terrain_slope_deg", terrain)
        object.__setattr__(self, "dune", flags["dune"])
        object.__setattr__(self, "rsl", flags["rsl"])
```

- [ ] **Step 4: Extend `edge_geometry`**

Replace the whole function in `backend/app/graph/geometry.py` and add this line to the module docstring: `Optional terrain: the larger map slope of the two end cells, and a dune / RSL flag when either end cell has one.`
```python
def edge_geometry(grid: GridSpec, elev_m: np.ndarray, src: np.ndarray, dst: np.ndarray,
                  roughness_m: np.ndarray | None = None, slope_deg: np.ndarray | None = None,
                  dune: np.ndarray | None = None, rsl: np.ndarray | None = None) -> EdgeGeometry:
    """Geometry of the edges (src[i] -> dst[i]). Edges touching nodata must be dropped first
    (enumerate_edges does this from the valid mask); a NaN elevation raises ValueError."""
    for name, arr in (("elev_m", elev_m), ("roughness_m", roughness_m), ("slope_deg", slope_deg),
                      ("dune", dune), ("rsl", rsl)):
        if arr is not None and arr.shape != grid.shape:
            raise ValueError(f"{name} shape {arr.shape} != grid shape {grid.shape}")
    src, dst = np.asarray(src), np.asarray(dst)
    if src.shape != dst.shape or src.ndim != 1:
        raise ValueError("src and dst must be 1-D arrays of the same length")

    elev = elev_m.astype(np.float64).ravel()  # row-major ravel == node-id order
    z_src, z_dst = elev[src], elev[dst]
    if np.isnan(z_src).any() or np.isnan(z_dst).any():
        raise ValueError("an edge touches a nodata cell; drop such edges before computing geometry")

    row_s, col_s = grid.rc(src)
    row_d, col_d = grid.rc(dst)
    lat_c, lon_c = grid.lat_centers(), grid.lon_centers()
    lat_s, lat_d = np.radians(lat_c[row_s]), np.radians(lat_c[row_d])
    dlon = np.radians(lon_c[col_d] - lon_c[col_s])
    dlat = lat_d - lat_s
    d_m = grid.radius_m * np.hypot(dlat, np.cos((lat_s + lat_d) / 2.0) * dlon)

    rough = None if roughness_m is None else roughness_m.astype(np.float64).ravel()[dst]
    terrain = None
    if slope_deg is not None:
        s = slope_deg.astype(np.float64).ravel()
        terrain = np.maximum(s[src], s[dst])
    either = lambda mask: None if mask is None else (mask.ravel()[src] | mask.ravel()[dst])  # noqa: E731
    return EdgeGeometry(d_m=d_m, dz_m=z_dst - z_src, roughness_m=rough, terrain_slope_deg=terrain,
                        dune=either(dune), rsl=either(rsl))
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/bin/python -m pytest tests/core tests/graph -v`
Expected: PASS. Existing geometry tests may match the old message `"roughness_m shape"`, which this code keeps.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/profiles.py backend/app/graph/geometry.py backend/tests/core/test_profiles.py backend/tests/graph/test_geometry.py
git commit -m "feat(graph): carry map slope and hazard flags on each edge"
```

---

### Task 4: Terrain parameters per profile (code, config file, loader)

**Files:**
- Modify: `backend/app/routing/profiles/params.py`
- Modify: `backend/app/core/config.py` (`Settings`), `backend/app/core/configfile/loader.py`, `config/mars.yaml`
- Test: `backend/tests/core/configfile/test_loader.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/core/configfile/test_loader.py`:
```python
def test_hazards_section_sets_the_rsl_buffer(tmp_path, shipped):
    shipped["hazards"] = {"rsl_buffer_m": 750}
    assert load_settings(write(tmp_path, shipped)).rsl_buffer_m == 750.0
    assert load_settings().rsl_buffer_m == 500.0  # the shipped value


def test_negative_rsl_buffer_is_rejected(tmp_path, shipped):
    shipped["hazards"] = {"rsl_buffer_m": -1}
    with pytest.raises(ConfigError, match="hazards.rsl_buffer_m"):
        load_settings(write(tmp_path, shipped))


def test_terrain_parameters_reach_the_profile_models(tmp_path, shipped):
    shipped["profiles"]["car"]["dune_blocked"] = False
    shipped["profiles"]["astronaut"]["roughness_weight"] = 0.0
    astronaut, car = models_from_settings(load_settings(write(tmp_path, shipped)))
    assert car.params.dune_blocked is False and astronaut.params.roughness_weight == 0.0


@pytest.mark.parametrize("bad", [{"roughness_weight": -1}, {"roughness_ref_m": 0}, {"dune_penalty": 0.5},
                                 {"rsl_blocked": "yes"}])
def test_invalid_terrain_parameters_are_rejected(bad):
    with pytest.raises(ValueError):
        AstronautParams(**bad)
    with pytest.raises(ValueError):
        CarParams(**bad)
```

Also add `"hazards"` to the expected sets in the two existing tests `test_the_shipped_file_starts_unconfirmed_so_the_placeholders_are_visible` and `test_a_section_without_a_confirmation_entry_counts_as_unconfirmed`:
```python
{"slope_classes", "profiles.astronaut", "profiles.car", "capacities", "weather.risk_bins", "hazards"}
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/core/configfile/test_loader.py -v`
Expected: FAIL (`unknown key(s) ['hazards']`, `unexpected keyword argument 'roughness_weight'`).

- [ ] **Step 3: Add the parameters**

In `backend/app/routing/profiles/params.py` add after `_check_weights`:
```python
def _check_terrain(p) -> None:
    if p.roughness_weight < 0:
        raise ValueError("roughness_weight must be >= 0")
    if p.roughness_ref_m <= 0:
        raise ValueError("roughness_ref_m must be > 0")
    if p.dune_penalty < 1:
        raise ValueError("dune_penalty must be >= 1 (it multiplies the cost)")
    for name in ("dune_blocked", "rsl_blocked"):
        if not isinstance(getattr(p, name), bool):
            raise ValueError(f"{name} must be true or false")
```
Add to `AstronautParams`, after `o2_kj_per_l`:
```python
    # Terrain and hazards (edge-cost-model.md section 4a). Placeholders.
    roughness_weight: float = 0.5  # cost x (1 + weight * min(roughness / ref, 3))
    roughness_ref_m: float = 3.0   # ~90th percentile of DEM roughness in the demo area
    dune_blocked: bool = False     # walking on sand is slow but possible
    dune_penalty: float = 1.5      # cost factor on dune-field edges when they are not blocked
    rsl_blocked: bool = True       # RSL sites: candidate Special Regions (planetary protection)
```
and call `_check_terrain(self)` at the end of `AstronautParams.__post_init__`.
Add to `CarParams`, after `crew_water_g_per_s`:
```python
    # Terrain and hazards (edge-cost-model.md section 4a). Placeholders.
    roughness_weight: float = 1.0  # rough ground hurts a wheeled vehicle more than a walker
    roughness_ref_m: float = 3.0
    dune_blocked: bool = True      # loose sand: the rover may bog down
    dune_penalty: float = 1.0
    rsl_blocked: bool = True
```
and call `_check_terrain(self)` at the end of `CarParams.__post_init__`.

- [ ] **Step 4: Add `rsl_buffer_m` to `Settings`**

In `backend/app/core/config.py`, inside `Settings` after `max_snap_distance_m`:
```python
    # Cells within this distance of an RSL site are impassable for profiles with rsl_blocked (hazards section of
    # config/mars.yaml). Part of the graph fingerprint: changing it rebuilds the graph.
    rsl_buffer_m: float = 500.0
```

- [ ] **Step 5: Teach the loader the `hazards` section**

In `backend/app/core/configfile/loader.py`:
```python
SECTIONS = ("grid", "routing", "hazards", "poi", "weather", "capacities", "slope_classes", "profiles", "confirmation")
KNOWN_CONFIRMATIONS = ("slope_classes", "profiles.astronaut", "profiles.car", "capacities", "weather.risk_bins",
                       "hazards")
```
and in `load_settings`, right after the routing time-limit check (before `poi = _mapping(...)`):
```python
    hazards = _mapping(doc.get("hazards"), f"{where}: hazards", ("rsl_buffer_m",))
    if "rsl_buffer_m" in hazards:
        kwargs["rsl_buffer_m"] = _number(hazards["rsl_buffer_m"], f"{where}: hazards.rsl_buffer_m", 0)
```

- [ ] **Step 6: Update `config/mars.yaml`**

After the `routing:` section add:
```yaml
hazards:
  # RSL sites (recurring slope lineae, points in the POI layer) are candidate Special Regions (planetary
  # protection): every cell within this distance is impassable for profiles with rsl_blocked: true.
  # Dune fields (polygons) are handled per profile below (dune_blocked / dune_penalty).
  # Part of the graph fingerprint: changing it rebuilds the graph.
  rsl_buffer_m: 500
```
At the end of `profiles.astronaut`:
```yaml
    roughness_weight: 0.5        # cost x (1 + weight * min(roughness / roughness_ref_m, 3))
    roughness_ref_m: 3.0         # ~90th percentile of DEM roughness in the demo area (m)
    dune_blocked: false          # walking on sand is slow but possible
    dune_penalty: 1.5            # cost factor on dune-field edges when not blocked
    rsl_blocked: true
```
At the end of `profiles.car`:
```yaml
    roughness_weight: 1.0
    roughness_ref_m: 3.0
    dune_blocked: true           # loose sand: the rover may bog down
    dune_penalty: 1.0
    rsl_blocked: true
```
In `confirmation:` add:
```yaml
  hazards:            {status: placeholder, source: "RSL buffer and dune rules: engineering guesses (decided with the team 2026-11-15)."}
```
Extend the header comment of `profiles:` with: `Terrain terms: cost x roughness factor x dune factor; impassable where the map slope of either end cell exceeds hard_limit_deg, or on blocked hazards (edge-cost-model.md section 4a).`

- [ ] **Step 7: Run the tests to see them pass**

Run: `.venv/bin/python -m pytest tests/core tests/routing/profiles -v`
Expected: PASS, including `test_the_shipped_file_loads_and_lists_every_model_parameter` (every new field is in the YAML) and `test_the_shipped_values_equal_the_built_in_defaults_when_nothing_was_changed` (YAML values equal the defaults).

- [ ] **Step 8: Commit**

```bash
git add backend/app/routing/profiles/params.py backend/app/core/config.py backend/app/core/configfile/loader.py config/mars.yaml backend/tests/core/configfile/test_loader.py
git commit -m "feat(config): roughness and hazard parameters per profile, RSL buffer"
```

---

### Task 5: Terrain terms in both cost formulas

**Files:**
- Create: `backend/app/routing/profiles/terrain.py`
- Modify: `backend/app/routing/profiles/astronaut.py`, `backend/app/routing/profiles/car.py`
- Test: `backend/tests/routing/profiles/test_terrain.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/routing/profiles/test_terrain.py`:
```python
import numpy as np
import pytest

from app.core.profiles import EdgeGeometry
from app.routing.profiles import AstronautModel, CarModel, CarParams
from app.routing.profiles.terrain import (ROUGHNESS_CAP, dune_factor, effective_slope_rad, hazard_blocked,
                                          roughness_factor)

MODELS = [AstronautModel(), CarModel()]
IDS = ["astronaut", "car"]


def flat(n=1, d=400.0, **extra):
    return EdgeGeometry(d_m=np.full(n, d), dz_m=np.zeros(n), **extra)


def test_effective_slope_is_the_steeper_of_travel_gradient_and_map_slope():
    g = EdgeGeometry(d_m=np.array([400.0, 400.0]), dz_m=np.array([0.0, 400.0 * np.tan(np.radians(30))]),
                     terrain_slope_deg=np.array([22.0, 10.0]))
    assert np.degrees(effective_slope_rad(g)) == pytest.approx([22.0, 30.0])


def test_without_map_slope_the_travel_gradient_is_used():
    g = EdgeGeometry(d_m=np.array([400.0]), dz_m=np.array([400.0 * np.tan(np.radians(12))]))
    assert np.degrees(effective_slope_rad(g)) == pytest.approx([12.0])


def test_roughness_factor_is_linear_then_capped():
    g = flat(3, roughness_m=np.array([0.0, 3.0, 300.0]))
    assert roughness_factor(g, 0.5, 3.0) == pytest.approx([1.0, 1.5, 1.0 + 0.5 * ROUGHNESS_CAP])
    assert roughness_factor(flat(2), 0.5, 3.0) == pytest.approx([1.0, 1.0])  # no roughness data


def test_dune_factor_and_hazard_blocking():
    g = flat(3, dune=np.array([True, False, False]), rsl=np.array([False, True, False]))
    assert dune_factor(g, 1.5) == pytest.approx([1.5, 1.0, 1.0])
    assert hazard_blocked(g, dune_blocked=True, rsl_blocked=True).tolist() == [True, True, False]
    assert hazard_blocked(g, dune_blocked=False, rsl_blocked=False).tolist() == [False, False, False]
    assert hazard_blocked(flat(), True, True).tolist() == [False]


@pytest.mark.parametrize("terrain, walk_ok, drive_ok", [(10.0, True, True), (22.0, False, True), (30.0, False, False)])
def test_moving_along_a_steep_hillside_is_blocked_as_the_map_shows(terrain, walk_ok, drive_ok):
    g = flat(terrain_slope_deg=np.array([terrain]))  # dz = 0: along the contour line
    assert bool(np.isfinite(AstronautModel().compute_edge_attrs(g)["cost"][0])) == walk_ok
    assert bool(np.isfinite(CarModel().compute_edge_attrs(g)["cost"][0])) == drive_ok


@pytest.mark.parametrize("model", MODELS, ids=IDS)
def test_cross_slope_costs_more_than_flat_ground(model):
    on_flat = model.compute_edge_attrs(flat(terrain_slope_deg=np.array([0.0])))["cost"][0]
    on_hillside = model.compute_edge_attrs(flat(terrain_slope_deg=np.array([15.0])))["cost"][0]
    assert on_hillside > on_flat


def test_dunes_slow_walking_and_block_the_car():
    walk = AstronautModel().compute_edge_attrs(flat(dune=np.array([True])))
    plain = AstronautModel().compute_edge_attrs(flat())
    assert walk["cost"][0] == pytest.approx(1.5 * plain["cost"][0])
    assert walk["time_s"][0] == pytest.approx(plain["time_s"][0])  # terrain terms never change resources
    assert all(np.isinf(v[0]) for v in CarModel().compute_edge_attrs(flat(dune=np.array([True]))).values())
    assert np.isfinite(CarModel(CarParams(dune_blocked=False)).compute_edge_attrs(flat(dune=np.array([True])))["cost"][0])


@pytest.mark.parametrize("model", MODELS, ids=IDS)
def test_rsl_buffer_blocks_both_profiles(model):
    assert all(np.isinf(v[0]) for v in model.compute_edge_attrs(flat(rsl=np.array([True]))).values())


def test_rough_ground_costs_more_for_the_car_than_for_walking():
    g = flat(roughness_m=np.array([3.0]))
    ratio = lambda m: m.compute_edge_attrs(g)["cost"][0] / m.compute_edge_attrs(flat())["cost"][0]  # noqa: E731
    assert ratio(AstronautModel()) == pytest.approx(1.5) and ratio(CarModel()) == pytest.approx(2.0)


def test_formula_versions_are_bumped():
    assert AstronautModel().formula_version.startswith("astronaut-tobler-minetti-2-")
    assert CarModel().formula_version.startswith("car-traction-2-")
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/routing/profiles/test_terrain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routing.profiles.terrain'`.

- [ ] **Step 3: Implement `terrain.py`**

```python
"""Terrain and hazard terms shared by both profile formulas (edge-cost-model.md section 4a).

They change only `cost` and passability, never the resources (time, O2, energy): there is no calibrated data
for how roughness or sand change consumption.
"""
from __future__ import annotations

import numpy as np

from app.core.profiles import EdgeGeometry

ROUGHNESS_CAP = 3.0  # roughness beyond 3x the reference adds no further cost


def effective_slope_rad(geom: EdgeGeometry) -> np.ndarray:
    """Steepness for the slope margin and the hard limit: the larger of the travel gradient and the map slope of
    the end cells, so walking along a steep hillside counts as steep. Without map slope: the travel gradient."""
    theta = np.abs(geom.theta_rad)
    if geom.terrain_slope_deg is None:
        return theta
    return np.maximum(theta, np.radians(geom.terrain_slope_deg))


def roughness_factor(geom: EdgeGeometry, weight: float, ref_m: float) -> np.ndarray:
    if geom.roughness_m is None or weight == 0:
        return np.ones(len(geom))
    r = np.nan_to_num(geom.roughness_m, nan=0.0)
    return 1.0 + weight * np.minimum(r / ref_m, ROUGHNESS_CAP)


def dune_factor(geom: EdgeGeometry, penalty: float) -> np.ndarray:
    if geom.dune is None:
        return np.ones(len(geom))
    return np.where(geom.dune, penalty, 1.0)


def hazard_blocked(geom: EdgeGeometry, dune_blocked: bool, rsl_blocked: bool) -> np.ndarray:
    blocked = np.zeros(len(geom), dtype=bool)
    if dune_blocked and geom.dune is not None:
        blocked |= geom.dune
    if rsl_blocked and geom.rsl is not None:
        blocked |= geom.rsl
    return blocked
```

- [ ] **Step 4: Use it in the astronaut model**

In `backend/app/routing/profiles/astronaut.py`: set `FORMULA_VERSION = "astronaut-tobler-minetti-2-placeholder"`, add `from app.routing.profiles.terrain import dune_factor, effective_slope_rad, hazard_blocked, roughness_factor`, and replace `compute_edge_attrs` with:
```python
    def compute_edge_attrs(self, geom: EdgeGeometry):
        q = self.params
        length, i = geom.length_m, geom.gradient
        theta_max = np.radians(q.hard_limit_deg)
        slope = effective_slope_rad(geom)  # travel gradient or the map slope across it, whichever is steeper

        v = tobler_speed_ms(i, q.speed_factor)
        v_flat = tobler_speed_ms(np.zeros(1), q.speed_factor)[0]
        c = minetti_cost(i)
        c_flat = minetti_cost(np.zeros(1))[0]
        # Mass, efficiency, suit penalty and gravity factors cancel in e(i) / e_flat, so the cost (and the
        # route) is the same for every astronaut.
        margin = 1.0 + (slope / theta_max) ** q.p
        terrain = roughness_factor(geom, q.roughness_weight, q.roughness_ref_m) * dune_factor(geom, q.dune_penalty)
        cost = length * margin * terrain * (q.alpha * (v_flat / v) + q.beta * (c / c_flat))

        attrs = {"cost": cost, **self.resources(geom)}
        blocked = (slope > theta_max) | hazard_blocked(geom, q.dune_blocked, q.rsl_blocked)
        return {k: np.where(blocked, np.inf, v_) for k, v_ in attrs.items()}
```

- [ ] **Step 5: Use it in the car model**

In `backend/app/routing/profiles/car.py`: set `FORMULA_VERSION = "car-traction-2-placeholder"`, add the same import, and replace `compute_edge_attrs` with:
```python
    def compute_edge_attrs(self, geom: EdgeGeometry):
        q = self.params
        length, theta = geom.length_m, geom.theta_rad
        theta_max = np.radians(q.hard_limit_deg)
        slope = effective_slope_rad(geom)

        v = self.speed_ms(theta)
        t = length / v
        force = q.mass_kg * MARS_G * (q.c_rr * np.cos(theta) + np.sin(theta))  # signed: downhill helps
        e_trac = np.maximum(0.0, force * length / q.eta_drive)  # J; no regeneration credit in the MVP
        e_per_m = e_trac / length
        e_flat = q.mass_kg * MARS_G * q.c_rr / q.eta_drive
        margin = 1.0 + (slope / theta_max) ** q.p
        terrain = roughness_factor(geom, q.roughness_weight, q.roughness_ref_m) * dune_factor(geom, q.dune_penalty)
        cost = length * margin * terrain * (q.alpha * (q.v_max_ms / v) + q.beta * (e_per_m / e_flat))

        attrs = {
            "cost": cost,
            "time_s": t,
            "o2_g": q.crew_n * q.crew_o2_g_per_s * t,
            "co2_g": q.crew_n * q.crew_co2_g_per_s * t,
            "water_g": q.crew_n * q.crew_water_g_per_s * t,
            "energy_wh": (e_trac + q.p_aux_w * t) / 3600.0,
        }
        blocked = (slope > theta_max) | hazard_blocked(geom, q.dune_blocked, q.rsl_blocked)
        return {k: np.where(blocked, np.inf, v_) for k, v_ in attrs.items()}
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `.venv/bin/python -m pytest tests/routing/profiles tests/graph tests/core -v`
Expected: PASS. Old model tests use geometry without terrain fields, so their factors are 1 and results are unchanged.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routing/profiles backend/tests/routing/profiles/test_terrain.py
git commit -m "feat(routing): map slope, roughness and hazards in both cost formulas"
```

---

### Task 6: Wire terrain into the graph build

**Files:**
- Modify: `backend/app/graph/build.py`, `backend/app/graph/startup/prepare.py`, `backend/app/graph/cli.py`
- Test: `backend/tests/graph/test_nodes_build.py`, `backend/tests/integration/test_graph_integration.py`

- [ ] **Step 1: Write the failing tests**

In `backend/tests/graph/test_nodes_build.py` change the two existing `build_params` assertions to:
```python
    assert g.build_params == {"neighbours": 8, "rsl_buffer_m": 500.0} and g.source_hashes == {}
```
```python
    assert g4.n_edges < g8.n_edges and g4.build_params == {"neighbours": 4, "rsl_buffer_m": 500.0}
```
and append (add `from app.core.resources import PROFILES`, `from app.layers.contracts import PoiData, PoiFeature, PoiKind`, `from app.routing.profiles import default_models` at the top if missing):
```python
def test_build_graph_blocks_every_edge_touching_an_rsl_buffer():
    g = fake_grid(8, 10)
    lon, lat = float(g.lon_centers()[5]), float(g.lat_centers()[4])
    rsl = PoiFeature(id="t:0:0", kind=PoiKind.RSL, geometry={"type": "Point", "coordinates": [lon, lat]}, source="t/0")
    inputs = dataclasses.replace(fake_inputs(g, relief_kind="flat"), poi=PoiData(features=(rsl,)))
    data = build_graph(inputs, default_models(), BuildConfig(rsl_buffer_m=10.0))
    node = int(g.node_id(4, 5))
    touching = (data.src == node) | (data.dst == node)
    for p in PROFILES:
        assert np.isinf(data.cost(p)[touching]).all() and np.isfinite(data.cost(p)[~touching]).all()
    assert data.build_params["rsl_buffer_m"] == 10.0


def test_the_rsl_buffer_is_part_of_the_fingerprint():
    inputs = small_inputs()
    assert expected_fingerprint(inputs, stub_models(), BuildConfig(rsl_buffer_m=100.0)) != \
           expected_fingerprint(inputs, stub_models(), BuildConfig())
```

Append to `backend/tests/integration/test_graph_integration.py`:
```python
def test_cli_records_the_configured_rsl_buffer(synthetic_settings, tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("hazards:\n  rsl_buffer_m: 750\n")
    out = tmp_path / "g.npz"
    assert graph_cli(["--data-dir", str(synthetic_settings.data_dir), "--config", str(cfg), "--out", str(out)]) == 0
    assert GraphData.read_meta(out)["build_params"]["rsl_buffer_m"] == 750.0
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/graph/test_nodes_build.py tests/integration/test_graph_integration.py -v`
Expected: FAIL (`unexpected keyword argument 'rsl_buffer_m'`, build_params mismatch).

- [ ] **Step 3: Update `build.py`**

Add `from app.graph.hazards import hazard_masks`. Replace `BuildConfig`:
```python
@dataclass(frozen=True)
class BuildConfig:
    neighbours: int = 8  # 4 or 8
    repo_root: Path = REPO_ROOT  # `source_files` of the layers are relative to this
    rsl_buffer_m: float = 500.0  # hazards.rsl_buffer_m in config/mars.yaml

    def params(self) -> dict:
        return {"neighbours": self.neighbours, "rsl_buffer_m": float(self.rsl_buffer_m)}
```
In `build_graph`, replace the `geom = ...` line with:
```python
    masks = hazard_masks(grid, inputs.poi, config.rsl_buffer_m)
    geom = edge_geometry(grid, relief.elev_m, src, dst, relief.roughness_m, relief.slope_deg, masks.dune, masks.rsl)
```
Update the module docstring pipeline line to: `inputs (GraphInputs) -> validate -> edges -> hazard masks -> geometry (+ map slope, roughness, hazards) -> per-profile cost/resources -> node table`.

- [ ] **Step 4: Pass the setting at startup and in the CLI**

`backend/app/graph/startup/prepare.py`: replace `BuildConfig()` with `BuildConfig(rsl_buffer_m=settings.rsl_buffer_m)`.

`backend/app/graph/cli.py`: in the `--fake` branch add `config = BuildConfig(neighbours=args.neighbours)`; in the real branch, after `models = ...`, add `config = BuildConfig(neighbours=args.neighbours, rsl_buffer_m=settings.rsl_buffer_m)`; change the call to `ensure_graph(out, inputs, models, config, force=args.force)`.

- [ ] **Step 5: Run the whole graph and integration suites**

Run: `.venv/bin/python -m pytest tests/graph tests/integration tests/routing -v`
Expected: PASS. The real-data parts skip when `data/raw` is missing, and otherwise rebuild the native graph (about a minute). If a real-data route assertion fails because terrain blocking now drops a stop or rejects a snap, print the offending point's `slope_deg` from the built graph. A point on a cell above the limit is the new, intended behaviour: move the test point onto the canyon floor and say so in the commit message. Don't loosen the rule.

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph backend/tests/graph backend/tests/integration/test_graph_integration.py
git commit -m "feat(graph): build edges with map slope, roughness and POI hazards"
```

---

### Task 7: Snap to nodes the profile can use

**Files:**
- Modify: `backend/app/graph/loader.py` (`RoutingContext`, `build_routing_context`)
- Modify: `backend/app/routing/snap.py`
- Test: `backend/tests/routing/test_snap.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/routing/test_snap.py` (add `from tests.routing.helpers import INF` to the existing helpers import):
```python
# Node 2 has no usable outgoing edge for the car (e.g. a dune cell): the car must snap past it.
CAR_DATA = make_graph_data(4, [*both(0, 1, 1.0), *both(1, 2, 1.0), *both(2, 3, 1.0)],
                           car_edges={(2, 1): INF, (2, 3): INF})


def test_each_profile_snaps_to_a_node_it_can_leave():
    c = build_routing_context(CAR_DATA)
    lon, lat = float(c.graph.lon[2]) + 0.01, float(c.graph.lat[2])  # nudged towards node 3
    assert snap(c, lon, lat, "start", 100_000, "astronaut").node == 2
    assert snap(c, lon, lat, "start", 100_000, "car").node == 3
    with pytest.raises(SnapError, match="passable for the car profile"):
        snap(c, float(c.graph.lon[2]), float(c.graph.lat[2]), "start", 10, "car")


def test_a_profile_with_no_passable_node_cannot_snap():
    data = make_graph_data(2, both(0, 1, 1.0), car_edges={(0, 1): INF, (1, 0): INF})
    c = build_routing_context(data)
    with pytest.raises(SnapError, match="No part of the routing area is passable for the car"):
        snap(c, float(c.graph.lon[0]), float(c.graph.lat[0]), "start", 100_000, "car")
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/routing/test_snap.py -v`
Expected: FAIL with `TypeError: snap() takes 5 positional arguments but 6 were given`.

- [ ] **Step 3: Per-profile KD-trees in the loader**

In `backend/app/graph/loader.py`: add `from dataclasses import dataclass, field`, `from typing import Mapping`, `from app.core.resources import PROFILES, ProfileId`. Add a field at the end of `RoutingContext`:
```python
    # per profile: KD-tree over the valid nodes that have at least one finite outgoing edge, and its node ids
    passable: Mapping[ProfileId, tuple[cKDTree, np.ndarray]] = field(default_factory=dict)
```
Replace `build_routing_context`:
```python
def build_routing_context(data: GraphData) -> RoutingContext:
    valid = np.asarray(data.node["valid"], dtype=bool)
    valid_ids = np.flatnonzero(valid)
    if valid_ids.size == 0:
        raise LayerUnavailable("The routing graph has no valid nodes.", "Rebuild the master graph.")
    lon_all, lat_all = np.asarray(data.node["lon"]), np.asarray(data.node["lat"])
    lat0 = float(lat_all[valid_ids].mean())
    tree = cKDTree(project(lon_all[valid_ids], lat_all[valid_ids], lat0, data.grid.radius_m))
    graph = RoutingGraph.from_graph_data(data)
    passable = {}
    for profile in PROFILES:
        ids = np.unique(graph.src[np.isfinite(graph.cost[profile])]).astype(np.int64)
        ids = ids[valid[ids]]
        if ids.size:
            passable[profile] = (cKDTree(project(lon_all[ids], lat_all[ids], lat0, data.grid.radius_m)), ids)
    return RoutingContext(graph, data.grid, data.formula_version, tree, valid_ids, lat0, passable)
```

- [ ] **Step 4: Profile-aware `snap`**

Replace `snap` in `backend/app/routing/snap.py` (add `from app.core.resources import ProfileId`):
```python
def snap(ctx: RoutingContext, lon: float, lat: float, label: str, max_distance_m: float,
         profile: ProfileId | str | None = None) -> SnappedNode:
    """Nearest valid node; with `profile`, the nearest node that profile can leave (not on a slope or hazard it
    cannot cross), so a click on a cliff or a dune snaps to usable ground nearby."""
    if not bool(ctx.grid.contains(lon, lat)):
        g = ctx.grid
        raise SnapError(f"{label} ({lon:.4f}, {lat:.4f}) is outside the routing area "
                        f"(lon {g.west}..{g.east}, lat {g.south}..{g.north}).")
    if profile is None:
        tree, ids, what = ctx.tree, ctx.valid_ids, "passable-data node"
    else:
        profile = ProfileId(profile)
        if profile not in ctx.passable:
            raise SnapError(f"No part of the routing area is passable for the {profile.value} profile.")
        (tree, ids), what = ctx.passable[profile], f"node passable for the {profile.value} profile"
    dist, idx = tree.query(ctx.project(lon, lat)[0])
    if dist > max_distance_m:
        raise SnapError(f"{label} ({lon:.4f}, {lat:.4f}) is {dist:.0f} m from the nearest {what} "
                        f"(maximum {max_distance_m:.0f} m); it may lie on a nodata area, a slope too steep "
                        f"for this profile or a blocked hazard zone.")
    node = int(ids[idx])
    return SnappedNode(node, float(ctx.graph.lon[node]), float(ctx.graph.lat[node]), float(dist))
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/bin/python -m pytest tests/routing tests/graph/test_loader.py -v`
Expected: PASS. The old snap tests call it without `profile`, so their messages are unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/loader.py backend/app/routing/snap.py backend/tests/routing/test_snap.py
git commit -m "feat(routing): snap points to nodes the chosen profile can use"
```

---

### Task 8: Point-to-point routes (start + end only)

**Files:**
- Modify: `backend/app/routing/contracts.py` (`RouteQuery.__post_init__`)
- Modify: `backend/app/routing/service.py`
- Modify: `backend/app/schemas/route.py` (`RouteRequest`)
- Test: `backend/tests/routing/test_contracts.py`, `backend/tests/routing/test_service.py`, `backend/tests/schemas/test_route_schema.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/routing/test_contracts.py` (add `from app.routing.contracts import EndMode, RouteQuery` and `import pytest` if missing):
```python
def test_no_destinations_needs_a_fixed_end():
    with pytest.raises(ValueError, match="at least one destination is required"):
        RouteQuery(profile="car", start_node=0, destination_nodes=())
    q = RouteQuery(profile="car", start_node=0, destination_nodes=(), end_mode=EndMode.FIXED, end_node=1)
    assert q.point_nodes == (0, 1)
```

Append to `backend/tests/routing/test_service.py`:
```python
def p2p(end_node, profile="astronaut"):
    return RouteQuery(profile=profile, start_node=0, destination_nodes=(), end_mode=EndMode.FIXED,
                      end_node=end_node, time_limit_s=1)


def test_point_to_point_route_needs_no_destinations():
    route = plan_route(CLIFF_GRAPH, p2p(3))
    assert route.nodes == (0, 1, 2, 3) and route.total_cost == 3.0 and route.stop_order == ()
    assert [(leg.from_point, leg.to_point) for leg in route.legs] == [(0, 1)]


def test_point_to_point_without_a_path_raises():
    with pytest.raises(NoFeasibleRoute, match="astronaut"):
        plan_route(CLIFF_GRAPH, p2p(4))
    assert plan_route(CLIFF_GRAPH, p2p(4, "car")).nodes[-1] == 4
```

Append to `backend/tests/schemas/test_route_schema.py` (add `from app.routing.contracts import EndMode` if missing):
```python
def test_start_and_end_alone_make_a_point_to_point_request():
    r = RouteRequest(start=BASE["start"], end={"lon": -70.0, "lat": -11.6})
    assert r.end_mode == EndMode.FIXED and r.destinations == [] and r.profile == "auto"


def test_without_end_mode_destinations_make_a_round_trip():
    assert RouteRequest(start=BASE["start"], destinations=BASE["destinations"]).end_mode == EndMode.ROUND_TRIP


def test_auto_and_named_profiles_are_accepted():
    for profile in ("auto", "astronaut", "car"):
        assert RouteRequest(**{**BASE, "profile": profile}).profile == profile
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/routing/test_contracts.py tests/routing/test_service.py tests/schemas/test_route_schema.py -v`
Expected: FAIL (`at least one destination is required` raised for the fixed case; schema rejects missing destinations / `auto`).

- [ ] **Step 3: Relax `RouteQuery`**

In `backend/app/routing/contracts.py`, `RouteQuery.__post_init__`, replace the first check with:
```python
        if not self.destination_nodes and self.end_mode != EndMode.FIXED:
            raise ValueError("at least one destination is required unless the end is fixed (point-to-point)")
```

- [ ] **Step 4: Skip the solver when there is nothing to order**

Replace `plan_route` in `backend/app/routing/service.py` (add `from app.routing.contracts import RoutePlan, RouteQuery, SolverResult` and `from app.routing.solver import NoFeasibleRoute, solve`):
```python
def plan_route(
    routing_graph: RoutingGraph,
    query: RouteQuery,
    capacities: Mapping[str, float] | None = None,
    reserve_margin: float = 0.0,
    path_resources: Callable[[object, Sequence[int]], Mapping[str, float]] | None = None,
) -> RoutePlan:
    """Raises solver.NoFeasibleRoute when no route exists at all (e.g. unreachable fixed end)."""
    cost_matrix = build_cost_matrix(routing_graph, query.profile, query.point_nodes)
    if query.destination_nodes:
        solution = solve(cost_matrix, query.end_mode, query.time_limit_s)
    else:  # point-to-point: one shortest path, nothing to order
        if not cost_matrix.reachable(0, 1):
            raise NoFeasibleRoute(f"no route exists for the {ProfileId(query.profile).value} profile "
                                  "between the start and the end")
        solution = SolverResult(order=())
    return assemble(
        routing_graph, query, cost_matrix, solution, capacities, reserve_margin, path_resources
    )
```
Also add `from app.core.resources import ProfileId` (tests pass the profile as a plain string, so wrap it).

- [ ] **Step 5: Relax the request schema**

In `backend/app/schemas/route.py`, change these `RouteRequest` fields and the validator:
```python
class RouteRequest(BaseModel):
    # "auto" (default): the backend routes with every profile and picks one (response `mode` says why).
    profile: Literal["auto", "astronaut", "car"] = "auto"
    start: LonLat
    # Stops to visit in the best order. Empty is allowed with an `end`: a point-to-point route. The maximum comes
    # from the configuration and is checked per request.
    destinations: list[LonLat] = Field(default_factory=list)
    end_mode: EndMode | None = None  # default: "fixed" when `end` is given, else "round_trip"
    end: LonLat | None = None
    time_limit_s: float | None = None  # solver time budget in s; None = the configured default, clamped to the configured range
    season: Literal["autumn", "winter", "spring", "summer"] | None = None  # same keys as /api/get-layer-four

    @model_validator(mode="after")
    def _end_matches_mode(self):
        if self.end_mode is None:
            self.end_mode = EndMode.FIXED if self.end is not None else EndMode.ROUND_TRIP
        if (self.end_mode == EndMode.FIXED) != (self.end is not None):
            raise ValueError("end is required if and only if end_mode is 'fixed'")
        if not self.destinations and self.end_mode != EndMode.FIXED:
            raise ValueError("give at least one destination, or an `end` for a point-to-point route")
        return self
```
`request.py` still calls `ProfileId(req.profile)`. Until Task 9, `"auto"` would fail there. Every existing test passes a named profile, so nothing breaks in between.

- [ ] **Step 6: Run the tests to see them pass**

Run: `.venv/bin/python -m pytest tests/routing tests/schemas tests/api -v`
Expected: PASS. The existing `{"destinations": []}` invalid case still fails validation (no `end`), and the API test asserting 422 for empty destinations still passes.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routing/contracts.py backend/app/routing/service.py backend/app/schemas/route.py backend/tests/routing backend/tests/schemas
git commit -m "feat(routing): point-to-point requests with start and end only"
```

---

### Task 9: Auto mode (walk or drive) with a user override

**Files:**
- Create: `backend/app/routing/modes/__init__.py`, `backend/app/routing/modes/select.py`
- Modify: `backend/app/schemas/route.py` (add `ProfileOption`, `ModeSelection`, `RouteResponse.mode`)
- Modify: `backend/app/routing/request.py`
- Test: `backend/tests/routing/modes/__init__.py` (empty), `backend/tests/routing/modes/test_select.py`, `backend/tests/routing/test_request.py`, `backend/tests/schemas/test_route_schema.py`, `backend/tests/api/routes/test_route.py`

- [ ] **Step 1: Write the failing selection tests**

`backend/tests/routing/modes/test_select.py`:
```python
import pytest

from app.core.resources import ProfileId
from app.routing.modes import NoProfileCanRoute, ProfileOutcome, choose
from app.routing.solver import NoFeasibleRoute

A, C = ProfileId.ASTRONAUT, ProfileId.CAR


def ok(profile, reached=2, o2=100.0, t=600.0):
    return ProfileOutcome(profile, reached=reached, requested=2, o2_g=o2, time_s=t)


def bad(profile, why="too steep"):
    return ProfileOutcome(profile, requested=2, error=why)


def test_least_oxygen_per_person_wins_when_both_reach_every_destination():
    best, reason = choose([ok(A, o2=80), ok(C, o2=120)])
    assert best.profile == A and "walking uses less oxygen per person (80 g vs 120 g)" in reason
    assert choose([ok(A, o2=150), ok(C, o2=120)])[0].profile == C


def test_reaching_more_destinations_beats_using_less_oxygen():
    best, reason = choose([ok(A, reached=1, o2=10), ok(C, reached=2, o2=500)])
    assert best.profile == C and "The vehicle reaches 2 of 2 destinations, walking only 1" in reason


def test_a_mode_that_cannot_route_is_never_chosen_and_says_why():
    best, reason = choose([bad(A, "start is on a 30 deg slope"), ok(C)])
    assert best.profile == C and "Walking cannot do this route (start is on a 30 deg slope)" in reason


def test_equal_oxygen_falls_back_to_time():
    best, reason = choose([ok(A, o2=100, t=900), ok(C, o2=100, t=300)])
    assert best.profile == C and "same oxygen use" in reason


def test_no_feasible_mode_raises_a_no_feasible_route_error():
    with pytest.raises(NoProfileCanRoute, match="walking: a; the vehicle: b") as e:
        choose([bad(A, "a"), bad(C, "b")])
    assert isinstance(e.value, NoFeasibleRoute)
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/routing/modes -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routing.modes'`.

- [ ] **Step 3: Implement the selection rule**

`backend/app/routing/modes/__init__.py`:
```python
"""Walking or driving: the `profile: "auto"` rule of POST /api/route."""
from app.routing.modes.select import AUTO, LABELS, NoProfileCanRoute, ProfileOutcome, choose, explain

__all__ = ["AUTO", "LABELS", "NoProfileCanRoute", "ProfileOutcome", "choose", "explain"]
```

`backend/app/routing/modes/select.py`:
```python
"""Choose walking or driving for a request (`profile: "auto"`). Decided with the team 2026-11-15:

1. reach as many destinations as possible;
2. then use the least oxygen per person (the astronaut's o2_g for the requesting user's body mass; the rover's
   o2_g divided by its crew size);
3. then the shorter time; then the order of PROFILES.
A profile that cannot route at all (snap or no-route error) is never chosen, and the reason says why.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from app.core.resources import PROFILES, ProfileId
from app.routing.solver import NoFeasibleRoute

AUTO = "auto"
LABELS = {ProfileId.ASTRONAUT: "walking", ProfileId.CAR: "the vehicle"}


class NoProfileCanRoute(NoFeasibleRoute):
    """No profile can route the request; the message gives each profile's reason (HTTP 422)."""


@dataclass(frozen=True)
class ProfileOutcome:
    profile: ProfileId
    reached: int = 0  # destinations visited
    requested: int = 0  # destinations asked for
    o2_g: float = math.inf  # oxygen per person over the whole route
    time_s: float = math.inf
    error: str | None = None  # set when the profile cannot route at all

    @property
    def feasible(self) -> bool:
        return self.error is None


def choose(outcomes: Sequence[ProfileOutcome]) -> tuple[ProfileOutcome, str]:
    feasible = [o for o in outcomes if o.feasible]
    if not feasible:
        raise NoProfileCanRoute("No mode can route this request: "
                                + "; ".join(f"{LABELS[ProfileId(o.profile)]}: {o.error}" for o in outcomes))
    rank = {p: i for i, p in enumerate(PROFILES)}
    best = min(feasible, key=lambda o: (-o.reached, o.o2_g, o.time_s, rank[ProfileId(o.profile)]))
    return best, explain(best, outcomes)


def explain(best: ProfileOutcome, outcomes: Sequence[ProfileOutcome]) -> str:
    name = LABELS[ProfileId(best.profile)]
    parts = []
    for o in outcomes:
        if o.profile == best.profile:
            continue
        other = LABELS[ProfileId(o.profile)]
        if not o.feasible:
            parts.append(f"{other.capitalize()} cannot do this route ({o.error})")
        elif o.reached < best.reached:
            parts.append(f"{name.capitalize()} reaches {best.reached} of {best.requested} destinations, "
                         f"{other} only {o.reached}")
        elif best.o2_g < o.o2_g:
            parts.append(f"Both modes reach the same points; {name} uses less oxygen per person "
                         f"({best.o2_g:.0f} g vs {o.o2_g:.0f} g)")
        else:
            parts.append(f"Both modes reach the same points with the same oxygen use; {name} takes "
                         f"{best.time_s / 60:.0f} min vs {o.time_s / 60:.0f} min")
    return f"Chose {name}: " + "; ".join(parts) + "."
```

- [ ] **Step 4: Run the selection tests to see them pass**

Run: `.venv/bin/python -m pytest tests/routing/modes -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Write the failing request, schema and API tests**

Append to `backend/tests/schemas/test_route_schema.py` (extend the `app.schemas.route` import with `ModeSelection, ProfileOption`):
```python
def test_mode_selection_serialises_options():
    m = ModeSelection(requested="auto", chosen="car", reason="r",
                      options=[ProfileOption(profile="car", feasible=True, reached=1, o2_g=1.0, time_s=2.0),
                               ProfileOption(profile="astronaut", feasible=False, reason="x")])
    assert m.model_dump()["options"][1] == {"profile": "astronaut", "feasible": False, "reached": 0,
                                            "o2_g": None, "time_s": None, "reason": "x"}
```

In `backend/tests/routing/test_request.py`, replace `test_unreachable_fixed_end_raises` with the two tests below. Node 5 is isolated, so it is no longer a snapping target; node 4 is reachable for the car only. Then append the auto-mode tests (add `from app.routing.solver import NoFeasibleRoute` if missing):
```python
def test_unreachable_fixed_end_raises():
    with pytest.raises(NoFeasibleRoute):
        run(profile="astronaut", dests=(2,), end_mode="fixed", end=pt(4))


def test_a_point_nowhere_near_a_usable_node_is_a_snap_error():
    with pytest.raises(SnapError, match="passable for the car profile"):
        run(dests=(2,), end_mode="fixed", end=pt(5))


# The car pays 5 on 0 <-> 1 (o2 = 2 x cost, shared by a crew of 2), so walking uses less oxygen per person there.
AUTO_CTX = build_routing_context(make_graph_data(6, EDGES, car_edges={(3, 4): 5.0, (0, 1): 5.0, (1, 0): 5.0}))


def run_auto(dests, **extra):
    req = RouteRequest(**{"profile": "auto", "start": pt(0), "destinations": [pt(n) for n in dests],
                          "time_limit_s": 2, **extra})
    return handle_route_request(AUTO_CTX, req, Settings())


def test_auto_walks_when_both_reach_everything_and_walking_uses_less_oxygen_per_person():
    d = run_auto((2,))
    assert d.profile == "astronaut" and d.mode.requested == "auto" and d.mode.chosen == "astronaut"
    assert "less oxygen per person (8 g vs 12 g)" in d.mode.reason
    assert {o.profile for o in d.mode.options} == {"astronaut", "car"} and all(o.feasible for o in d.mode.options)


def test_auto_drives_when_only_the_car_reaches_the_destination():
    d = run_auto((4,))
    assert d.profile == "car" and d.stop_order == [0] and "reaches 1 of 1" in d.mode.reason


def test_auto_explains_a_mode_that_cannot_route_at_all():
    d = run_auto((), end=pt(4))
    walking = next(o for o in d.mode.options if o.profile == "astronaut")
    assert d.profile == "car" and not walking.feasible and walking.reason and walking.o2_g is None
    assert "Walking cannot do this route" in d.mode.reason


def test_auto_with_no_feasible_mode_is_an_error():
    with pytest.raises(NoFeasibleRoute, match="No mode can route"):
        run_auto((2,), end_mode="fixed", end=pt(5))


def test_a_named_profile_is_the_users_choice():
    d = run(profile="car", dests=(1,))
    assert (d.mode.requested, d.mode.chosen, d.mode.reason) == ("car", "car", "Chosen by the user.")
    assert len(d.mode.options) == 1 and d.mode.options[0].feasible


def test_point_to_point_request():
    d = run(dests=(), end=pt(3))
    assert [(leg.from_, leg.to) for leg in d.legs] == [("start", "end")] and d.stop_order == []
```
How the numbers work out: on `AUTO_CTX` the round trip 0→2→0 costs 4 for walking (o2 = 2 × 4 = 8 g, 1 person) and 5+1+1+5 = 12 for the car (o2 = 24 g, crew 2, so 12 g per person).

Append to `backend/tests/api/routes/test_route.py`:
```python
def test_auto_is_the_default_profile_and_reports_the_choice(client):
    b = body(dests=(1,))
    b.pop("profile", None)
    d = client.post("/api/route", json=b).json()
    assert d["mode"]["requested"] == "auto" and d["profile"] == d["mode"]["chosen"]
    assert {o["profile"] for o in d["mode"]["options"]} == {"astronaut", "car"}
```

- [ ] **Step 6: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/routing/test_request.py tests/schemas/test_route_schema.py tests/api/routes/test_route.py -v`
Expected: FAIL (`ModeSelection` missing, `d.mode` missing, `ProfileId('auto')` ValueError).

- [ ] **Step 7: Add the response models**

In `backend/app/schemas/route.py`, before `RouteResponse`:
```python
class ProfileOption(BaseModel):
    profile: ProfileId
    feasible: bool
    reached: int = 0  # destinations visited
    o2_g: float | None = None  # oxygen per person over the route (g): what "auto" compares
    time_s: float | None = None
    reason: str | None = None  # why this profile cannot route (only when feasible is false)


class ModeSelection(BaseModel):
    requested: Literal["auto", "astronaut", "car"]
    chosen: ProfileId
    reason: str  # human-readable, render verbatim
    options: list[ProfileOption]  # every profile that was tried
```
and add to `RouteResponse`, after `body_mass_kg`:
```python
    # How the profile was chosen: by the user, or by "auto" (then every profile's outcome is listed).
    mode: ModeSelection | None = None
```

- [ ] **Step 8: Rewrite the request handler**

In `backend/app/routing/request.py`:
- Module docstring: add the line `profile "auto" routes with every profile and keeps the one app.routing.modes.choose picks (NoProfileCanRoute, a NoFeasibleRoute, when none can).`
- Imports: add `import math`; `from app.core.resources import PROFILES, ProfileId`; `from app.routing.modes import AUTO, ProfileOutcome, choose`; `from app.routing.profiles.params import CarParams`; `from app.routing.snap import SnappedNode, SnapError, snap`; `from app.routing.solver import NoFeasibleRoute`; add `ModeSelection, ProfileOption` to the `app.schemas.route` import.
- Add constants under `MASS_UNAVAILABLE`: `USER_CHOICE = "Chosen by the user."`; and after `RouteRequestError`: `ROUTE_ERRORS = (SnapError, RouteRequestError, NoFeasibleRoute)`.
- Keep `_snapped`, `_label`, `weather_warnings`, `mass_resources`, `to_response` unchanged.
- Replace `handle_route_request` with:
```python
def crew_size(settings, profile: ProfileId) -> int:
    """People whose oxygen a profile's o2_g covers: one walker, or the rover's crew."""
    if profile != ProfileId.CAR:
        return 1
    return max(1, CarParams(**(settings.profiles or {}).get("car", {})).crew_n)


def _outcome(response: RouteResponse, requested: int, crew: int) -> ProfileOutcome:
    return ProfileOutcome(response.profile, reached=len(response.stop_order), requested=requested,
                          o2_g=response.resources.get("o2_g", 0.0) / crew, time_s=response.resources.get("time_s", 0.0))


def _option(o: ProfileOutcome) -> ProfileOption:
    finite = lambda v: v if math.isfinite(v) else None  # noqa: E731
    return ProfileOption(profile=o.profile, feasible=o.feasible, reached=o.reached, o2_g=finite(o.o2_g),
                         time_s=finite(o.time_s), reason=o.error)


def handle_route_request(ctx: RoutingContext, req: RouteRequest, settings, weather=None,
                         body_mass_kg: float | None = None) -> RouteResponse:
    limits = settings.route_limits
    if len(req.destinations) > limits.max_destinations:
        raise RouteRequestError(f"At most {limits.max_destinations} destinations are allowed per request "
                                f"(got {len(req.destinations)}).")
    n, time_limit = len(req.destinations), limits.clamp_time_limit(req.time_limit_s)
    if req.profile != AUTO:
        profile = ProfileId(req.profile)
        response = route_for_profile(ctx, req, profile, settings, weather, body_mass_kg, time_limit)
        mode = ModeSelection(requested=req.profile, chosen=profile, reason=USER_CHOICE,
                             options=[_option(_outcome(response, n, crew_size(settings, profile)))])
        return response.model_copy(update={"mode": mode})
    # Each profile gets an equal share of the solver budget, so "auto" takes about as long as one profile.
    share = max(limits.min_time_limit_s, time_limit / len(PROFILES))
    responses: dict[ProfileId, RouteResponse] = {}
    outcomes: list[ProfileOutcome] = []
    for profile in PROFILES:
        try:
            responses[profile] = route_for_profile(ctx, req, profile, settings, weather, body_mass_kg, share)
        except ROUTE_ERRORS as ex:
            outcomes.append(ProfileOutcome(profile, requested=n, error=str(ex)))
        else:
            outcomes.append(_outcome(responses[profile], n, crew_size(settings, profile)))
    best, reason = choose(outcomes)  # NoProfileCanRoute (HTTP 422) when no profile can route
    mode = ModeSelection(requested=AUTO, chosen=best.profile, reason=reason, options=[_option(o) for o in outcomes])
    return responses[ProfileId(best.profile)].model_copy(update={"mode": mode})


def route_for_profile(ctx: RoutingContext, req: RouteRequest, profile: ProfileId, settings, weather,
                      body_mass_kg: float | None, time_limit_s: float) -> RouteResponse:
    """One profile: snap every point to a node that profile can use, reject duplicates, plan, convert."""
    limit = settings.max_snap_distance_m
    start = snap(ctx, req.start.lon, req.start.lat, "start", limit, profile)
    dests = [snap(ctx, d.lon, d.lat, f"destination {i}", limit, profile) for i, d in enumerate(req.destinations)]
    end = snap(ctx, req.end.lon, req.end.lat, "end", limit, profile) if req.end else None

    labelled = [("start", start), *((f"destination {i}", s) for i, s in enumerate(dests))]
    if end:
        labelled.append(("end", end))
    seen: dict[int, list[str]] = {}
    for name, s in labelled:
        seen.setdefault(s.node, []).append(name)
    dup = [names for names in seen.values() if len(names) > 1]
    if dup:
        raise RouteRequestError("Points snap to the same graph node and must be distinct: "
                                + "; ".join(" = ".join(n) for n in dup) + ".")

    query = RouteQuery(profile=profile, start_node=start.node, destination_nodes=tuple(s.node for s in dests),
                       end_mode=req.end_mode, end_node=end.node if end else None, time_limit_s=time_limit_s,
                       season=req.season)
    resources_of, mass_used, mass_warning = mass_resources(ctx, profile, body_mass_kg, settings)
    plan = plan_route(ctx.graph, query, (settings.capacities or {}).get(profile.value),
                      settings.reserve_margin, resources_of)
    visited = [(start.lon, start.lat), *((dests[i].lon, dests[i].lat) for i in plan.stop_order)]
    if end:
        visited.append((end.lon, end.lat))
    warnings = [*plan.warnings, *weather_warnings(weather, req.season, visited),
                *([mass_warning] if mass_warning else [])]
    return to_response(ctx, plan, req, start, dests, end, warnings, mass_used)
```
`app/api/routes/route.py` needs no change: it already maps `SnapError`, `RouteRequestError` and `NoFeasibleRoute` (which `NoProfileCanRoute` extends) to HTTP 422. Update its module docstring to mention `profile` may be `"auto"`.

- [ ] **Step 9: Run the routing, schema and API suites**

Run: `.venv/bin/python -m pytest tests/routing tests/schemas tests/api -v`
Expected: PASS. If `test_auto_is_the_default_profile...` fails because `body()` in that file builds the request differently, read `body()` and remove the `profile` key the way it is built. The assertion stays as written.

- [ ] **Step 10: Commit**

```bash
git add backend/app/routing/modes backend/app/routing/request.py backend/app/schemas/route.py backend/app/api/routes/route.py backend/tests/routing backend/tests/schemas backend/tests/api
git commit -m "feat(routing): auto mode picks walking or driving by reach, then oxygen per person"
```

---

### Task 10: End-to-end terrain routing tests

**Files:**
- Create: `backend/tests/integration/test_terrain_routing.py`

- [ ] **Step 1: Write the tests**

```python
"""Terrain-aware routing end to end: fake layers -> graph (map slope, hazards) -> request with profile "auto"."""
from app.core.config import Settings
from app.graph.build import build_graph
from app.graph.loader import build_routing_context
from app.layers.contracts import GraphInputs, PoiData, PoiFeature, PoiKind
from app.layers.fakes import fake_grid, fake_relief, fake_weather
from app.routing.profiles import default_models
from app.routing.request import handle_route_request
from app.schemas.route import RouteRequest

GRID = fake_grid(24, 30)


def context(relief_kind="flat", poi=(), **relief_kw):
    inputs = GraphInputs(grid=GRID, relief=fake_relief(GRID, relief_kind, **relief_kw), weather=fake_weather(GRID),
                         poi=PoiData(features=tuple(poi)))
    return build_routing_context(build_graph(inputs, default_models()))


def point(row, col):
    return {"lon": float(GRID.lon_centers()[col]), "lat": float(GRID.lat_centers()[row])}


def route(ctx, start, end):
    return handle_route_request(ctx, RouteRequest(start=start, end=end, time_limit_s=1), Settings())


def test_a_hillside_too_steep_to_walk_is_driven_even_along_the_contour():
    ctx = context("ramp", slope_deg_=22.0)  # rises to the east: a north-south move is level but crosses 22 deg
    d = route(ctx, point(3, 10), point(20, 10))
    walking = next(o for o in d.mode.options if o.profile == "astronaut")
    assert d.profile == "car" and not walking.feasible and "passable for the astronaut" in walking.reason


def test_a_dune_band_blocks_the_car_so_auto_walks():
    w = float(GRID.lon_centers()[14] - GRID.dlon / 2)
    e = float(GRID.lon_centers()[15] + GRID.dlon / 2)
    s, n = GRID.south - 1, GRID.north + 1
    band = PoiFeature(id="t:0:0", kind=PoiKind.DUNE_FIELD, source="t/0",
                      geometry={"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]})
    d = route(context(poi=[band]), point(12, 5), point(12, 25))
    car = next(o for o in d.mode.options if o.profile == "car")
    assert d.profile == "astronaut" and not car.feasible


def test_on_open_flat_ground_auto_picks_the_mode_with_less_oxygen_per_person():
    d = route(context(), point(12, 5), point(12, 9))
    assert all(o.feasible for o in d.mode.options)
    assert d.mode.chosen == min(d.mode.options, key=lambda o: o.o2_g).profile
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/integration/test_terrain_routing.py -v`
Expected: PASS (3 tests). These exercise Tasks 1–9 together, so a failure points at an integration bug. Debug it with superpowers:systematic-debugging; don't edit the assertions.

- [ ] **Step 3: Run the full backend suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (421 before this work plus the new ones), with real-data tests run or skipped depending on `data/raw`.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_terrain_routing.py
git commit -m "test: end-to-end terrain routing with auto mode"
```

---

### Task 11: Documentation of the changed contracts and formulas

**Files:**
- Modify: `context/skills/mars-mvp-data/references/edge-cost-model.md`, `context/skills/mars-mvp-data/SKILL.md`, `context/skills/mars-mvp-data/references/layer-ingestion.md`, `AGENTS.md`, `README.md`

- [ ] **Step 1: `edge-cost-model.md`**: add a section after section 4 ("Cost function"):
```markdown
## 4a. Terrain and hazard terms (both profiles, formula version 2)

    cost = length * (1 + (s_eff / hard_limit)^p) * R * D * [alpha * time_ratio + beta * energy_ratio]

- `s_eff = max(|travel gradient angle|, map slope)`, where map slope is the larger `ReliefData.slope_deg` of the
  edge's two end cells (the array the walkability overlay shows). Walking along a steep hillside therefore counts
  as steep, as the Artemis limit ("up/down/across a slope") requires.
- `R = 1 + roughness_weight * min(roughness_m / roughness_ref_m, 3)`, roughness at the edge's end cell
  (`app/layers/relief/roughness.py`: deviation from the plane through the 4 neighbours; 0 on any plane).
- `D = dune_penalty` on edges touching a dune-field cell, else 1.
- Impassable (every attribute inf) when `s_eff > hard_limit`, or the edge touches a dune cell and
  `dune_blocked`, or a cell within `hazards.rsl_buffer_m` of an RSL site and `rsl_blocked`.
- Masks: `app/graph/hazards/masks.py` (dune polygons by cell centre; RSL points with a metric buffer).
- Resources (time, O2, CO2, water, energy) are NOT changed by `R`, `D` or the cross-slope term: there is no
  calibrated data for that. Defaults: astronaut R weight 0.5, dunes x1.5, RSL blocked; car R weight 1.0, dunes
  blocked, RSL blocked; `roughness_ref_m` 3 m; RSL buffer 500 m. All placeholders (`confirmation.hazards`).
```
Add rows to the section 10 constraint table: `| Cross-slope | map slope of the end cells | in the cost and the hard limit, section 4a |`, `| Dune fields, RSL sites | POI layer | section 4a |`, `| Roughness | DEM | cost only, section 4a |`.

- [ ] **Step 2: `SKILL.md` section 10**
  - Under "Profiles", add: ``Requests may also say `"profile": "auto"` (the default): the backend routes with both profiles and returns the one that reaches the most destinations, then the one with less oxygen per person (the rover's o2_g divided by its crew), then the faster one (`app/routing/modes/select.py`). `"auto"` is a request value, never a profile id in the graph.``
  - In Step 3, update the request example: `"profile": "auto"` with comment `// "auto" (default) | "astronaut" | "car"`, `"destinations"` comment `// may be empty when "end" is given: point-to-point`, `"end_mode"` comment `// default: "fixed" when end is given, else "round_trip"`. Add the bullet: `**Snap per profile:** each point snaps to the nearest node that profile can leave (at least one finite outgoing edge), so a click on a cliff or a dune moves to usable ground; the response's snapped distance shows how far.`
  - In Step 6, add to the response example: `"mode": {"requested": "auto", "chosen": "car", "reason": "Chose the vehicle: Walking cannot do this route (...)." , "options": [{"profile": "astronaut", "feasible": false, "reached": 0, "o2_g": null, "time_s": null, "reason": "..."}, {"profile": "car", "feasible": true, "reached": 2, "o2_g": 41.2, "time_s": 5400, "reason": null}]}` with the note `// o2_g in options is per person; render reason verbatim`.
  - In the Step 1 bullet list, note that edges also use the map slope, roughness and POI hazards (edge-cost-model.md section 4a) and that `rsl_buffer_m` is a build parameter in the fingerprint.
  - Section 12 "Not implemented" line: remove `ReliefData.roughness_m`.

- [ ] **Step 3: `layer-ingestion.md`**: where `ReliefData.roughness_m` is listed as optional, state it is now produced by `ingest_relief` (`app/layers/relief/roughness.py`); add that POI dune polygons and RSL points become graph hazard masks inside the graph builder (`app/graph/hazards/`), with no change to `PoiData`.

- [ ] **Step 4: `AGENTS.md`**: in the "Structure" paragraph after the routing engine sentence, add: ``Routing is terrain-aware: edges are impassable where the map slope of either end cell exceeds the profile limit, roughness raises the cost, dune fields block the car and slow walking, RSL sites are blocked within `hazards.rsl_buffer_m` (edge-cost-model.md section 4a). `POST /api/route` defaults to `"profile": "auto"` (picks walking or driving: reach, then oxygen per person, then time; `app/routing/modes/`) and accepts start + end without destinations (point-to-point).``

- [ ] **Step 5: `README.md`**: after the "Layer endpoints" paragraph add: ``Route: `POST /api/route` (login required). Minimal body `{"start": {"lon": .., "lat": ..}, "end": {"lon": .., "lat": ..}}`; `profile` is `auto` (default), `astronaut` or `car`; add `destinations` for a multi-stop route. The response's `mode` says which profile was chosen and why.``

- [ ] **Step 6: Commit**

```bash
git add context AGENTS.md README.md
git commit -m "docs: terrain-aware routing, auto mode and point-to-point requests"
```

---

### Task 12: Verify on the real data

- [ ] **Step 1: Rebuild the real graph** (about 1 minute, ~4 GB peak):

```bash
cd /Users/sielprar/PycharmProjects/NASA/NASA-space-apps-mars-map/backend && .venv/bin/python -m app.graph --force
```
Expected: `built: …/data/graph/graph.npz nodes=1,287,600 edges=10,287,166 formula=astronaut=astronaut-tobler-minetti-2-placeholder+…;car=car-traction-2-placeholder+…`

- [ ] **Step 2: Smoke-test real routes and check the slope rule.** Save this as a scratch script, not in the repo:

```python
import numpy as np
from app.core.configfile import load_settings
from app.graph.contracts import GraphData
from app.graph.loader import load_routing_context
from app.routing.request import handle_route_request
from app.schemas.route import RouteRequest

s = load_settings()
ctx = load_routing_context(s)
slope = GraphData.load(s.graph_file).node["slope_deg"]
limits = {"astronaut": 20.0, "car": 25.0}
for profile in ("auto", "astronaut", "car"):
    for start, end in [((-70.6, -11.95), (-70.2, -12.05)), ((-69.4, -12.6), (-68.9, -12.4))]:
        req = RouteRequest(profile=profile, start={"lon": start[0], "lat": start[1]}, end={"lon": end[0], "lat": end[1]})
        try:
            r = handle_route_request(ctx, req, s)
        except Exception as ex:  # noqa: BLE001 - a smoke test: print and continue
            print(profile, start, end, type(ex).__name__, ex)
            continue
        lon, lat = np.array(r.path["coordinates"]).T
        rows, cols = ctx.grid.lonlat_to_rc(lon, lat)
        worst = float(slope[ctx.grid.node_id(rows, cols)].max())
        print(profile, "->", r.profile, f"max map slope {worst:.1f} (limit {limits[r.profile]})",
              f"time {r.resources['time_s'] / 3600:.1f} h", r.mode.reason)
        assert worst <= limits[r.profile] + 1e-3
```
Run: `cd backend && .venv/bin/python /path/to/scratch_script.py`
Expected: every route prints a max map slope at or below its profile's limit, and `auto` lines print a reason. A 422 snap error means a point sits on steep or nodata ground. Move it a little and re-run.

- [ ] **Step 3: Report.** Tell the user what passed, what was skipped (real-data tests skip without `data/raw`), and the open product questions: the hazard and roughness numbers are placeholders (`confirmation.hazards`), and with the current profile parameters `auto` will choose the car whenever it can reach the points.

---

## Self-review (done while writing)

- **Spec coverage:** slope fix (Tasks 3, 5, 6, 7), more layers (roughness Task 1; dunes and RSL Tasks 2, 5, 6), auto with override (Task 9), start→end (Task 8), per-person O2 rule (Task 9), backend only, docs (Task 11), real-data check (Task 12).
- **Type consistency:** `EdgeGeometry(terrain_slope_deg, dune, rsl)` is used in Tasks 3, 5 and 6. `edge_geometry(..., roughness_m, slope_deg, dune, rsl)` is called that way in Task 6. `BuildConfig(rsl_buffer_m)` / `Settings.rsl_buffer_m` / `hazards.rsl_buffer_m` agree. `snap(ctx, lon, lat, label, max_m, profile)` in Task 7 matches its use in Task 9. `ProfileOutcome`, `choose`, `NoProfileCanRoute`, `AUTO` match between Task 9's module and tests. `ModeSelection` / `ProfileOption` fields match the schema test.
- **Existing tests touched on purpose:** `test_nodes_build` build_params (Task 6), two loader `unconfirmed` sets (Task 4), `test_unreachable_fixed_end_raises` in `test_request.py` (Task 9: isolated node 5 is now a snap error, so the test uses node 4).
