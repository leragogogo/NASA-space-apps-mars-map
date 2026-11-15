# Layer Getters Implementation Plan

> **Status: done.** This is the execution record. After it ran, files were moved to follow the team's development rules
> (SKILL.md section 11): tests now mirror the code in `backend/tests/<module>/test_<file>.py` (real-data checks in
> `backend/tests/integration/`), the weather script is `scripts/build_weather/build_weather.py` with its test in
> `scripts/build_weather/tests/`, and `pytest`/`httpx` moved into `backend/requirements.txt` (no `requirements-dev.txt`).
> Paths below are the original ones.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One getter per map layer that loads the local datasets once at startup, plus the `/api/get-layer-one … four` endpoints (and tile, walkability-PNG and point-lookup routes) that serve them to the frontend.

**Architecture:** FastAPI app factory (`create_app`) whose lifespan builds a `Registry` of four getter objects (base imagery, relief, POI, weather) and one shared `TileStore`. Getters read only local files under `data/`; a getter whose data is missing is stored as a `LayerUnavailable` and its endpoints answer 503 with a fix hint. Endpoints are thin wrappers around `getter.describe()`; `getter.sample()` / `relief.grid()` are the hooks for the future master graph.

**Tech Stack:** Python 3.14, FastAPI, numpy, tifffile, Pillow, shapely, pytest + httpx (TestClient). `scripts/build_weather.py` uses pandas + scipy.

**Spec:** `docs/superpowers/specs/2026-11-14-layer-getters-design.md`

**Git:** the user asked for **no commits and no push**. Every task ends with a test run instead of a commit. Leave all changes uncommitted.

**Conventions for every task**
- Work from the repo root `/Users/sielprar/PycharmProjects/NASA/NASA-space-apps-mars-map` unless a step says `cd backend`.
- Run tests with `cd backend && .venv/bin/pytest <file> -v`.
- Never call NASA/Harvard or any network service from backend code.

---

## File map

| File | Responsibility |
|---|---|
| `backend/requirements.txt` | runtime deps (+ numpy, tifffile, pillow, shapely) |
| `backend/requirements-dev.txt` | pytest, httpx, and `scripts/requirements.txt` (for the weather build test) |
| `backend/pytest.ini` | makes `backend/` importable in tests |
| `backend/main.py` | `create_app(settings)`: lifespan → registry, CORS, 503 handler, routers |
| `backend/app/core/config.py` | `Settings`, AOI, `SlopeClass` table, tile-source table, risk colours |
| `backend/app/layers/base.py` | `LayerUnavailable`, `LayerGetter` protocol |
| `backend/app/tiles/store.py` | `TileStore`: which tile sources exist on disk, tile path lookup |
| `backend/app/layers/base_imagery/getter.py` | `BaseImageryGetter` (Layer 1) |
| `backend/app/layers/relief/slope.py` | pixel size, slope, slope classes |
| `backend/app/layers/relief/render.py` | walkability PNG |
| `backend/app/layers/relief/getter.py` | `ReliefGetter` (Layer 2) |
| `backend/app/layers/poi/normalize.py` | per-dataset mapping to the common feature format |
| `backend/app/layers/poi/getter.py` | `PoiGetter` (Layer 3) |
| `backend/app/layers/weather/getter.py` | `WeatherGetter` (Layer 4), `display_risk`, `display_style` |
| `backend/app/layers/registry.py` | `Registry`, `build_registry(settings)` |
| `backend/app/schemas/layers.py` | pydantic models for layer one, layer two, point |
| `backend/app/api/routes/layers.py` | `/api/get-layer-*` routes |
| `backend/app/api/routes/tiles.py` | `/api/tiles/{source}/{z}/{row}/{col}` |
| `backend/tests/conftest.py` | builds a tiny fixture data dir; `client`, `empty_client` fixtures |
| `backend/tests/test_*.py` | unit, API and real-data tests |
| `scripts/build_weather.py` | MDAD → `data/derived/weather/*` (port of skill scripts 06+07) |
| `scripts/requirements.txt` | + pandas, scipy |
| `README.md`, `AGENTS.md` | document `build_weather.py` and backend tests |

---

### Task 1: Environment, package skeleton, test fixtures, weather reference copy

**Files:**
- Modify: `backend/requirements.txt`, `scripts/requirements.txt`
- Create: `backend/requirements-dev.txt`, `backend/pytest.ini`, `backend/tests/conftest.py`
- Create (empty): `backend/app/__init__.py`, `backend/app/api/__init__.py`, `backend/app/api/routes/__init__.py`, `backend/app/core/__init__.py`, `backend/app/layers/__init__.py`, `backend/app/layers/base_imagery/__init__.py`, `backend/app/layers/relief/__init__.py`, `backend/app/layers/poi/__init__.py`, `backend/app/layers/weather/__init__.py`, `backend/app/schemas/__init__.py`, `backend/app/tiles/__init__.py`. Do **not** create `backend/tests/__init__.py`: without it pytest puts `tests/` on `sys.path`, so tests can `from conftest import DEM_SHAPE`.

- [ ] **Step 1: Write `backend/requirements.txt`**

```
fastapi
uvicorn[standard]
numpy
tifffile
pillow
shapely
```

- [ ] **Step 2: Write `backend/requirements-dev.txt`**

```
-r ../scripts/requirements.txt
pytest
httpx
```

- [ ] **Step 3: Write `scripts/requirements.txt`**

```
requests
tifffile
numpy
pillow
pandas
scipy
```

- [ ] **Step 4: Write `backend/pytest.ini`**

```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 5: Create the empty `__init__.py` files**

Run:
```bash
cd backend && for d in app app/api app/api/routes app/core app/layers app/layers/base_imagery app/layers/relief app/layers/poi app/layers/weather app/schemas app/tiles; do touch "$d/__init__.py"; done && find app -name __init__.py | wc -l
```
Expected: `11`

- [ ] **Step 6: Write `backend/tests/conftest.py`**

Imports of `app.*` stay inside functions so this file loads before any app module exists.

```python
"""Shared test fixtures: a tiny, fully synthetic data/ folder that mimics the real layout."""
import json
import math
from pathlib import Path

import numpy as np
import pytest
import tifffile
from fastapi.testclient import TestClient
from PIL import Image

FIXTURE_SLOPE_DEG = 10.0  # the fixture DEM is a plane rising to the east at this slope
DEM_SHAPE = (6, 8)        # rows, cols
SEASON_NAMES = {
    "autumn": "S. Autumn (Ls 0-90)",
    "winter": "S. Winter (Ls 90-180)",
    "spring": "S. Spring (Ls 180-270, perihelion)",
    "summer": "S. Summer (Ls 270-360)",
}


def _tile(path: Path, size: int = 256, fmt: str = "PNG"):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (size, size), (120, 80, 60)).save(path, format=fmt)


def _point(lon, lat, **props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


def _poly(w, s, e, n, **props):
    ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": props}


def _fc(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def _cell(lon, lat, season_name, **overrides):
    props = {"observed_years": 8.0, "storm_days": 0, "storms": 0, "reasons": [], "rate": 0.0,
             "rate_ci95": [0.0, 0.46], "storms_per_year": 0.0, "risk": "Low", "confidence": "reliable",
             "typical_year_rate": None, "typical_year_risk": None, "extreme_year": None,
             "neighbour_estimate": None, "season": season_name,
             "message": f"Low dust-storm risk in {season_name.split(' (')[0]}: fixture."}
    props.update(overrides)
    return _poly(lon - 0.5, lat - 0.5, lon + 0.5, lat + 0.5, **props)


def build_fixture_data(root: Path) -> Path:
    from app.core.config import AOI
    from app.layers.relief.slope import pixel_size_m

    raw = root / "raw"
    # --- tiles: two base sources, one relief source (jpg), one poi source
    _tile(raw / "tiles/Coprates_EMelas_Chasm_CTX_BlockAdj_dd/5/2/3.png")
    _tile(raw / "tiles/Coprates_EMelas_Chasm_CTX_BlockAdj_dd/6/5/6.png")
    _tile(raw / "tiles/HiRISE_Global/5/1/1.png", size=512)
    _tile(raw / "tiles/Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw/5/2/3.jpg", fmt="JPEG")
    _tile(raw / "tiles/MC18_PolySulfate_Mineral_IndicatorV2_SP/5/2/3.png")

    # --- DEM: plane rising to the east with a constant slope
    dx, _ = pixel_size_m(DEM_SHAPE, AOI)
    row = np.arange(DEM_SHAPE[1]) * dx * math.tan(math.radians(FIXTURE_SLOPE_DEG)) - 3000.0
    dem = np.tile(row, (DEM_SHAPE[0], 1)).astype("float32")
    (raw / "dem").mkdir(parents=True)
    tifffile.imwrite(raw / "dem/dem_blend200m_aoi.tif", dem)

    # --- POI vectors (one unknown file that must be skipped)
    feats = raw / "features"
    feats.mkdir(parents=True)
    files = {
        "Aquieous_Mineral_Distribution_Options_clon0__0": _fc(
            _point(-70.0, -12.0, FID=0, Class="sulfate"),
            _point(290.0, -11.0, FID=1, Class="silica")),  # 0-360 longitude -> -70.0
        "Hydrous_Mineral_Detections_OMEGA_CRISM_clon0__0": _fc(
            _point(-68.5, -11.0, FID=0, Type="Hydrous Mineral Detection", Instrument="CRISM")),
        "RSLs_Gullies_New_IcyCraters_clon0__0": _fc(
            _point(-69.0, -10.5, FID=0, Type="confirmed recurring slope lineae (RSL)", Ref="McEwen et al. (2014)")),
        "EZMars__3": _fc(_poly(-70.5, -12.5, -70.0, -12.0, FID=0, name="1007.03", ez_name="Melas Chasma")),
        "SIM3292_Global_Geology__0": _fc(_poly(-75.0, -15.0, -70.0, -11.0, FID=0, Unit="Aa",
                                               UnitDesc="Amazonian apron unit")),
        "combinedNom__0": _fc(_point(-69.69, -11.52, FID=0, name="Garni", type="Crater, craters",
                                     origin="Village in Armenia.")),
        "unknown_dataset__0": _fc(_point(-70.0, -12.0, FID=0)),
    }
    for stem, fc in files.items():
        (feats / f"{stem}.geojson").write_text(json.dumps(fc))

    # --- weather: 3 cells x 4 seasons; winter has one cell per confidence level
    weather = root / "derived/weather"
    weather.mkdir(parents=True)
    cells = []
    for key, name in SEASON_NAMES.items():
        if key == "winter":
            cells += [
                _cell(-69.5, -11.5, name, risk="High", rate=6.56, storms=33, storm_days=54,
                      message="High dust-storm risk in S. Winter: fixture."),
                _cell(-70.5, -11.5, name, risk="High", confidence="approximate", typical_year_rate=0.3,
                      typical_year_risk="Low", extreme_year={"my": 25, "storm_days": 37, "risk": "High"},
                      reasons=["37 of 39 storm-days come from a single Mars year (MY25)"],
                      message="APPROXIMATE: not enough data to reliably calculate the risk: fixture."),
                _cell(-71.5, -11.5, name, risk=None, rate=None, confidence="insufficient_data",
                      neighbour_estimate={"rate": 2.0, "risk": "Moderate", "n_frames": 4},
                      message="NOT ENOUGH DATA: dust-storm risk cannot be reliably calculated: fixture."),
            ]
        else:
            cells += [_cell(lon, -11.5, name) for lon in (-69.5, -70.5, -71.5)]
    (weather / "context_weather_frames.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "caveat": "Fixture caveat.", "features": cells}))
    (weather / "aoi_weather_frames.json").write_text(json.dumps(
        {"aoi": list(AOI), "caveat": "Fixture caveat.",
         "frames": [{"season": n, "risk": "Low", "confidence": "reliable", "message": f"AOI {k} fixture."}
                    for k, n in SEASON_NAMES.items()]}))
    return root


@pytest.fixture(scope="session")
def fixture_data(tmp_path_factory) -> Path:
    return build_fixture_data(tmp_path_factory.mktemp("data"))


@pytest.fixture(scope="session")
def fixture_settings(fixture_data):
    from app.core.config import Settings
    return Settings(data_dir=fixture_data)


@pytest.fixture(scope="session")
def client(fixture_settings):
    from main import create_app
    with TestClient(create_app(fixture_settings)) as c:
        yield c


@pytest.fixture
def empty_client(tmp_path):
    from app.core.config import Settings
    from main import create_app
    with TestClient(create_app(Settings(data_dir=tmp_path))) as c:
        yield c
```

- [ ] **Step 7: Create the venv and install**

Run:
```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt && .venv/bin/python -c "import fastapi, numpy, tifffile, PIL, shapely, pandas, scipy, pytest, httpx; print('ok')"
```
Expected: `ok`

- [ ] **Step 8: Keep a reference copy of the current weather output (built by the skill's own scripts)**

Run:
```bash
cp -R data/derived/weather data/derived/weather_skill_reference && ls data/derived/weather_skill_reference/context_weather_frames.geojson data/derived/weather_skill_reference/aoi_weather_frames.json
```
Expected: both paths listed. (`data/` is gitignored.)

- [ ] **Step 9: Check pytest collects nothing yet without errors**

Run: `cd backend && .venv/bin/pytest -q`
Expected: `no tests ran` (exit code 5), no import errors.

---

### Task 2: Settings and the shared layer contract

**Files:**
- Create: `backend/app/core/config.py`, `backend/app/layers/base.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from app.core.config import AOI, REPO_ROOT, SLOPE_CLASSES, TILE_SOURCES, Settings
from app.layers.base import LayerUnavailable


def test_default_data_dir_is_repo_data(monkeypatch):
    monkeypatch.delenv("MARS_DATA_DIR", raising=False)
    assert Settings().data_dir == REPO_ROOT / "data"
    assert (REPO_ROOT / "backend").is_dir()


def test_env_overrides_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("MARS_DATA_DIR", str(tmp_path))
    s = Settings()
    assert s.data_dir == tmp_path
    assert s.raw_dir == tmp_path / "raw"
    assert s.derived_dir == tmp_path / "derived"


def test_slope_classes_are_contiguous():
    assert SLOPE_CLASSES[0].min_deg == 0
    for a, b in zip(SLOPE_CLASSES, SLOPE_CLASSES[1:]):
        assert a.max_deg == b.min_deg
    assert [c.id for c in SLOPE_CLASSES] == ["easy_walk", "walkable", "vehicle_only", "vehicle_limit", "impassable"]


def test_tile_sources_cover_three_layers():
    assert {d.layer for d in TILE_SOURCES.values()} == {"base_imagery", "relief", "poi"}
    assert AOI == (-71.8, -13.4, -68.0, -10.0)


def test_layer_unavailable_carries_fix():
    ex = LayerUnavailable("missing", "python scripts/download_data.py")
    assert ex.detail == "missing" and ex.fix == "python scripts/download_data.py"
    assert isinstance(ex, Exception)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && .venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.config'`

- [ ] **Step 3: Write `backend/app/core/config.py`**

```python
"""Backend settings. Everything that may change after review (paths, thresholds, colours) lives here."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# Demo area (west, south, east, north), longitude -180..180. Same box as scripts/download_data.py.
AOI = (-71.8, -13.4, -68.0, -10.0)


@dataclass(frozen=True)
class SlopeClass:
    id: str
    label: str
    min_deg: float
    max_deg: float
    color: str  # hex; used by the walkability PNG and the legend
    walkable: bool
    vehicle: bool


# Thresholds are unconfirmed by the product owner (SKILL.md section 5): keep them configurable.
SLOPE_CLASSES = (
    SlopeClass("easy_walk", "Easy walk", 0, 5, "#1a9850", True, True),
    SlopeClass("walkable", "Walkable", 5, 15, "#91cf60", True, True),
    SlopeClass("vehicle_only", "Vehicle only", 15, 25, "#fee08b", False, True),
    SlopeClass("vehicle_limit", "Hard / vehicle limit", 25, 35, "#fc8d59", False, True),
    SlopeClass("impassable", "Impassable", 35, 90, "#d73027", False, False),
)


@dataclass(frozen=True)
class TileSourceDef:
    folder: str        # folder under data/raw/tiles (the Trek layer label)
    title: str
    layer: str         # base_imagery | relief | poi
    coverage_note: str


# Short public id -> tile folder. Only these sources are ever served.
TILE_SOURCES = {
    "ctx_coprates": TileSourceDef("Coprates_EMelas_Chasm_CTX_BlockAdj_dd", "CTX mosaic, Coprates / East Melas",
                                  "base_imagery", "98 % of the demo area"),
    "ctx_global": TileSourceDef("CTX_beta01_uncontrolled_5m_Caltech", "CTX global mosaic (fallback)", "base_imagery",
                                "~92 % of the demo area; gaps in the south-east where Trek stores truncated tiles"),
    "hirise": TileSourceDef("HiRISE_Global", "HiRISE (zoom-in detail)", "base_imagery",
                            "~17 % of the demo area, scattered footprints"),
    "hillshade_color": TileSourceDef("Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw",
                                     "MOLA + HRSC colour shaded relief", "relief", "~98 % of the demo area"),
    "hillshade_ctx": TileSourceDef("CTX_Shade_East_Melas", "CTX shaded relief, East Melas", "relief",
                                   "~48 % of the demo area, in strips"),
    "crism_sulfate": TileSourceDef("MC18_PolySulfate_Mineral_IndicatorV2_SP", "CRISM polyhydrated sulfate indicator",
                                   "poi", "~70 % of the demo area"),
}

RISK_COLORS = {"Low": "#2e7d32", "Moderate": "#f9a825", "High": "#c62828"}


def _default_data_dir() -> Path:
    return Path(os.environ.get("MARS_DATA_DIR", REPO_ROOT / "data"))


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=_default_data_dir)
    aoi: tuple = AOI
    slope_classes: tuple = SLOPE_CLASSES
    tile_sources: dict = field(default_factory=lambda: dict(TILE_SOURCES))
    risk_colors: dict = field(default_factory=lambda: dict(RISK_COLORS))
    poi_sample_radius_km: float = 2.0

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def derived_dir(self) -> Path:
        return self.data_dir / "derived"
```

- [ ] **Step 4: Write `backend/app/layers/base.py`**

```python
"""What every layer getter has in common."""
from __future__ import annotations

from typing import Protocol


class LayerUnavailable(Exception):
    """A layer's data is missing or unreadable. The API answers 503 with `detail` and `fix`."""

    def __init__(self, detail: str, fix: str):
        super().__init__(detail)
        self.detail = detail
        self.fix = fix


class LayerGetter(Protocol):
    name: str

    def describe(self, *args, **kwargs) -> dict:
        """Summary returned by the layer's /api/get-layer-* endpoint."""

    def sample(self, lon: float, lat: float, season: str | None = None):
        """What this layer knows about one point (input for the master graph)."""
```

- [ ] **Step 5: Run the test**

Run: `cd backend && .venv/bin/pytest tests/test_config.py -v`
Expected: 5 passed

---

### Task 3: TileStore

**Files:**
- Create: `backend/app/tiles/store.py`
- Test: `backend/tests/test_tile_store.py`

- [ ] **Step 1: Write the failing test**

```python
from app.tiles.store import TileStore


def make_store(fixture_settings):
    s = fixture_settings
    return TileStore(s.raw_dir / "tiles", s.tile_sources, s.aoi)


def test_detects_sources_on_disk(fixture_settings):
    store = make_store(fixture_settings)
    assert [i["id"] for i in store.available("base_imagery")] == ["ctx_coprates", "hirise"]
    assert [i["id"] for i in store.available("relief")] == ["hillshade_color"]
    assert [i["id"] for i in store.available("poi")] == ["crism_sulfate"]


def test_info_reads_zoom_size_format(fixture_settings):
    store = make_store(fixture_settings)
    ctx = store.info("ctx_coprates")
    assert (ctx["min_zoom"], ctx["max_zoom"], ctx["tile_size"], ctx["format"]) == (5, 6, 256, "png")
    assert ctx["tile_url"] == "/api/tiles/ctx_coprates/{z}/{y}/{x}"
    assert ctx["bounds"] == [[-13.4, -71.8], [-10.0, -68.0]]
    assert store.info("hirise")["tile_size"] == 512
    assert store.info("hillshade_color")["format"] == "jpg"
    assert store.info("ctx_global") is None  # not on disk in the fixture


def test_path_lookup(fixture_settings):
    store = make_store(fixture_settings)
    path, media = store.path("ctx_coprates", 5, 2, 3)
    assert path.is_file() and media == "image/png"
    assert store.path("hillshade_color", 5, 2, 3)[1] == "image/jpeg"
    assert store.path("ctx_coprates", 5, 2, 99) is None       # missing tile
    assert store.path("ctx_global", 5, 2, 3) is None          # source not on disk
    assert store.path("../../etc", 5, 2, 3) is None            # not a configured source
    assert store.path("ctx_coprates", -1, 2, 3) is None        # negative index


def test_empty_dir_has_no_sources(tmp_path, fixture_settings):
    store = TileStore(tmp_path / "tiles", fixture_settings.tile_sources, fixture_settings.aoi)
    assert store.available("base_imagery") == []
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && .venv/bin/pytest tests/test_tile_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tiles.store'`

- [ ] **Step 3: Write `backend/app/tiles/store.py`**

```python
"""Finds tile files on disk. Only sources listed in the config tile-source table are ever served."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg"}


class TileStore:
    def __init__(self, tiles_dir: Path, sources: dict, aoi: tuple):
        self._dir = tiles_dir
        self._defs = sources
        w, s, e, n = aoi
        bounds = [[s, w], [n, e]]  # Leaflet order: [[south, west], [north, east]]
        self._info: dict[str, dict] = {}
        for sid, d in sources.items():
            folder = tiles_dir / d.folder
            if not folder.is_dir():
                continue
            zooms = sorted(int(p.name) for p in folder.iterdir() if p.is_dir() and p.name.isdigit())
            first = next((f for f in sorted(folder.rglob("*")) if f.suffix in (".png", ".jpg")), None)
            if not zooms or first is None:
                continue
            with Image.open(first) as im:
                size = im.size[0]
            self._info[sid] = {
                "id": sid, "title": d.title, "tile_url": f"/api/tiles/{sid}/{{z}}/{{y}}/{{x}}",
                "format": first.suffix[1:], "tile_size": size, "min_zoom": zooms[0], "max_zoom": zooms[-1],
                "bounds": [list(b) for b in bounds], "coverage_note": d.coverage_note,
            }

    def available(self, layer: str) -> list[dict]:
        """Tile sources of one layer that exist on disk, in config order."""
        return [info for sid, info in self._info.items() if self._defs[sid].layer == layer]

    def info(self, source_id: str) -> dict | None:
        return self._info.get(source_id)

    def path(self, source_id: str, z: int, row: int, col: int) -> tuple[Path, str] | None:
        """(file, media type) of one tile, or None if the source is unknown or the tile does not exist."""
        info = self._info.get(source_id)
        if info is None or min(z, row, col) < 0:
            return None
        p = self._dir / self._defs[source_id].folder / str(z) / str(row) / f"{col}.{info['format']}"
        return (p, MEDIA_TYPES[info["format"]]) if p.is_file() else None
```

- [ ] **Step 4: Run the test**

Run: `cd backend && .venv/bin/pytest tests/test_tile_store.py -v`
Expected: 4 passed

---

### Task 4: Base imagery getter (Layer 1)

**Files:**
- Create: `backend/app/layers/base_imagery/getter.py`
- Test: `backend/tests/test_base_imagery.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from app.layers.base import LayerUnavailable
from app.layers.base_imagery.getter import BaseImageryGetter
from app.tiles.store import TileStore


def store_for(settings, tiles_dir=None):
    return TileStore(tiles_dir or settings.raw_dir / "tiles", settings.tile_sources, settings.aoi)


def test_describe(fixture_settings):
    g = BaseImageryGetter(store_for(fixture_settings))
    d = g.describe()
    assert d["layer"] == "base_imagery"
    assert d["default_source"] == "ctx_coprates"
    assert [s["id"] for s in d["sources"]] == ["ctx_coprates", "hirise"]


def test_tile_path_and_sample(fixture_settings):
    g = BaseImageryGetter(store_for(fixture_settings))
    assert g.tile_path("ctx_coprates", 5, 2, 3) is not None
    assert g.sample(-70.0, -12.0) is None  # routing does not use imagery


def test_unavailable_without_base_tiles(fixture_settings, tmp_path):
    with pytest.raises(LayerUnavailable) as ex:
        BaseImageryGetter(store_for(fixture_settings, tmp_path / "tiles"))
    assert "download_data.py --only tiles" in ex.value.fix
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && .venv/bin/pytest tests/test_base_imagery.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.layers.base_imagery.getter'`

- [ ] **Step 3: Write `backend/app/layers/base_imagery/getter.py`**

```python
"""Layer 1: base imagery. Lists the imagery tile sources on disk; tiles are served by /api/tiles."""
from __future__ import annotations

from app.layers.base import LayerUnavailable
from app.tiles.store import TileStore

DEFAULT_SOURCE = "ctx_coprates"


class BaseImageryGetter:
    name = "base_imagery"

    def __init__(self, store: TileStore):
        self._store = store
        self._sources = store.available("base_imagery")
        if not self._sources:
            raise LayerUnavailable("No base imagery tiles found under data/raw/tiles.",
                                   "python scripts/download_data.py --only tiles")

    def sources(self) -> list[dict]:
        return self._sources

    def describe(self) -> dict:
        ids = [s["id"] for s in self._sources]
        return {"layer": self.name, "default_source": DEFAULT_SOURCE if DEFAULT_SOURCE in ids else ids[0],
                "sources": self._sources}

    def tile_path(self, source_id: str, z: int, row: int, col: int):
        return self._store.path(source_id, z, row, col)

    def sample(self, lon: float, lat: float, season: str | None = None):
        return None
```

- [ ] **Step 4: Run the test**

Run: `cd backend && .venv/bin/pytest tests/test_base_imagery.py -v`
Expected: 3 passed

---

### Task 5: Slope maths and walkability PNG

**Files:**
- Create: `backend/app/layers/relief/slope.py`, `backend/app/layers/relief/render.py`
- Test: `backend/tests/test_relief_slope.py`

- [ ] **Step 1: Write the failing test**

```python
import io
import math

import numpy as np
from PIL import Image

from app.core.config import AOI, SLOPE_CLASSES
from app.layers.relief.render import walkability_png
from app.layers.relief.slope import M_PER_DEG, classify, pixel_size_m, slope_degrees


def test_pixel_size_matches_real_grid():
    dx, dy = pixel_size_m((1073, 1200), AOI)
    assert round(dx) == 184 and round(dy) == 188
    assert M_PER_DEG == 2 * math.pi * 3_396_190 / 360


def test_slope_of_tilted_plane():
    shape = (5, 7)
    dx, _ = pixel_size_m(shape, AOI)
    plane = np.tile(np.arange(shape[1]) * dx * math.tan(math.radians(20)), (shape[0], 1))
    assert np.allclose(slope_degrees(plane, AOI), 20.0)


def test_classify_edges_and_nodata():
    s = np.array([0, 4.99, 5, 14.9, 15, 24.9, 25, 35, 60, np.nan])
    assert classify(s, SLOPE_CLASSES).tolist() == [0, 0, 1, 1, 2, 2, 3, 4, 4, -1]


def test_walkability_png_colours_and_transparency():
    cls = np.array([[0, 4], [-1, 2]], dtype=np.int8)
    img = Image.open(io.BytesIO(walkability_png(cls, SLOPE_CLASSES)))
    assert img.mode == "RGBA" and img.size == (2, 2)
    assert img.getpixel((0, 0))[:3] == (0x1a, 0x98, 0x50)   # easy_walk
    assert img.getpixel((1, 0))[:3] == (0xd7, 0x30, 0x27)   # impassable
    assert img.getpixel((0, 1))[3] == 0                      # no data -> transparent
    assert img.getpixel((1, 1))[3] > 0
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && .venv/bin/pytest tests/test_relief_slope.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.layers.relief.slope'`

- [ ] **Step 3: Write `backend/app/layers/relief/slope.py`**

```python
"""Slope from the elevation grid. The same arrays feed the map overlay and (later) the router."""
from __future__ import annotations

import math

import numpy as np

MARS_RADIUS_M = 3_396_190.0  # Mars 2000 sphere, as used by Trek
M_PER_DEG = 2 * math.pi * MARS_RADIUS_M / 360


def pixel_size_m(shape: tuple[int, int], aoi: tuple) -> tuple[float, float]:
    """(east-west, north-south) pixel size in metres for a grid covering `aoi`."""
    ny, nx = shape
    w, s, e, n = aoi
    lat_c = math.radians((s + n) / 2)
    return (e - w) / nx * M_PER_DEG * math.cos(lat_c), (n - s) / ny * M_PER_DEG


def slope_degrees(elev: np.ndarray, aoi: tuple) -> np.ndarray:
    dx, dy = pixel_size_m(elev.shape, aoi)
    gy, gx = np.gradient(elev, dy, dx)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def classify(slope: np.ndarray, classes) -> np.ndarray:
    """Index into `classes` per cell (lower edge inclusive); -1 where slope is NaN."""
    edges = [c.max_deg for c in classes[:-1]]
    out = np.digitize(slope, edges).astype(np.int8)
    out[np.isnan(slope)] = -1
    return out
```

- [ ] **Step 4: Write `backend/app/layers/relief/render.py`**

```python
"""Walkability overlay: one RGBA pixel per grid cell, coloured by slope class."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

ALPHA = 170  # semi-transparent so the imagery stays visible underneath


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def walkability_png(slope_class: np.ndarray, classes) -> bytes:
    lut = np.zeros((len(classes) + 1, 4), np.uint8)  # last row = no data, fully transparent
    for i, c in enumerate(classes):
        lut[i] = (*_rgb(c.color), ALPHA)
    idx = np.where(slope_class < 0, len(classes), slope_class)
    buf = io.BytesIO()
    Image.fromarray(lut[idx]).save(buf, format="PNG")  # (h, w, 4) uint8 -> RGBA
    return buf.getvalue()
```

- [ ] **Step 5: Run the test**

Run: `cd backend && .venv/bin/pytest tests/test_relief_slope.py -v`
Expected: 4 passed

---

### Task 6: Relief getter (Layer 2)

**Files:**
- Create: `backend/app/layers/relief/getter.py`
- Test: `backend/tests/test_relief_getter.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
import pytest
from conftest import DEM_SHAPE, FIXTURE_SLOPE_DEG

from app.core.config import Settings
from app.layers.base import LayerUnavailable
from app.layers.relief.getter import ReliefGetter
from app.tiles.store import TileStore


@pytest.fixture(scope="module")
def relief(fixture_settings):
    s = fixture_settings
    return ReliefGetter(s, TileStore(s.raw_dir / "tiles", s.tile_sources, s.aoi))


def test_grid_is_single_source_of_truth(relief):
    g = relief.grid()
    assert g["elevation_m"].shape == g["slope_deg"].shape == g["slope_class"].shape == DEM_SHAPE
    assert np.allclose(g["slope_deg"], FIXTURE_SLOPE_DEG, atol=1e-3)
    assert (g["slope_class"] == 1).all()  # 10 deg -> walkable


def test_describe(relief):
    d = relief.describe()
    assert d["layer"] == "relief"
    assert d["bounds"] == [[-13.4, -71.8], [-10.0, -68.0]]
    assert len(d["slope_classes"]) == 5 and d["slope_classes"][1]["id"] == "walkable"
    assert d["overlay"]["url"] == "/api/get-layer-two/walkability.png"
    assert [h["id"] for h in d["hillshade_sources"]] == ["hillshade_color"]
    assert isinstance(d["resolution_m"], int) and d["caveats"]


def test_point_inside_and_outside(relief):
    p = relief.point(-70.0, -12.0)
    assert p["slope_class"] == "walkable" and p["walkable"] and p["vehicle"] and p["approximate"]
    assert p["slope_deg"] == pytest.approx(FIXTURE_SLOPE_DEG, abs=0.01)
    assert relief.point(-60.0, -12.0) is None
    assert relief.sample(-70.0, -12.0) == p


def test_point_on_east_and_north_edges(relief):
    assert relief.point(-68.0, -10.0) is not None  # edges are inside


def test_walkability_png_bytes(relief):
    assert relief.walkability_png()[:8] == b"\x89PNG\r\n\x1a\n"


def test_missing_dem(tmp_path):
    s = Settings(data_dir=tmp_path)
    with pytest.raises(LayerUnavailable) as ex:
        ReliefGetter(s, TileStore(s.raw_dir / "tiles", s.tile_sources, s.aoi))
    assert "--only dem" in ex.value.fix
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && .venv/bin/pytest tests/test_relief_getter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.layers.relief.getter'`

- [ ] **Step 3: Write `backend/app/layers/relief/getter.py`**

```python
"""Layer 2: relief. Elevation grid -> slope -> slope classes, walkability overlay and point lookup."""
from __future__ import annotations

from dataclasses import asdict

import numpy as np
import tifffile

from app.layers.base import LayerUnavailable
from app.layers.relief.render import walkability_png
from app.layers.relief.slope import classify, pixel_size_m, slope_degrees
from app.tiles.store import TileStore

NODATA_BELOW = -32000  # Trek exports noData as -32767
CAVEATS = [
    "The 200 m elevation grid underestimates local slope: all slope values are approximate, and short steep "
    "features such as cliffs and crater rims are smoothed out.",
    "Slope class thresholds are provisional and not yet confirmed for walking or vehicle limits.",
]


class ReliefGetter:
    name = "relief"

    def __init__(self, settings, store: TileStore):
        path = settings.raw_dir / "dem" / "dem_blend200m_aoi.tif"
        if not path.is_file():
            raise LayerUnavailable(f"Elevation grid not found: {path}", "python scripts/download_data.py --only dem")
        try:
            elev = tifffile.imread(path).astype("float64")
        except Exception as ex:  # noqa: BLE001
            raise LayerUnavailable(f"Elevation grid unreadable: {ex}",
                                   "python scripts/download_data.py --only dem --force") from ex
        elev[elev <= NODATA_BELOW] = np.nan
        self._aoi = settings.aoi
        self._classes = settings.slope_classes
        self._store = store
        self._elev = elev
        self._slope = slope_degrees(elev, self._aoi)
        self._class = classify(self._slope, self._classes)
        self._png = walkability_png(self._class, self._classes)
        dx, dy = pixel_size_m(elev.shape, self._aoi)
        self._resolution_m = int(round((dx + dy) / 2))

    def grid(self) -> dict:
        """The arrays the map overlay uses; the master graph must use these too."""
        return {"elevation_m": self._elev, "slope_deg": self._slope, "slope_class": self._class, "aoi": self._aoi}

    def walkability_png(self) -> bytes:
        return self._png

    def _index(self, lon: float, lat: float) -> tuple[int, int] | None:
        w, s, e, n = self._aoi
        if not (w <= lon <= e and s <= lat <= n):
            return None
        ny, nx = self._elev.shape
        col = min(int((lon - w) / (e - w) * nx), nx - 1)
        row = min(int((n - lat) / (n - s) * ny), ny - 1)
        return row, col

    def point(self, lon: float, lat: float) -> dict | None:
        idx = self._index(lon, lat)
        if idx is None:
            return None
        k = int(self._class[idx])
        base = {"lon": lon, "lat": lat, "approximate": True}
        if k < 0:
            return {**base, "elevation_m": None, "slope_deg": None, "slope_class": None,
                    "walkable": False, "vehicle": False}
        c = self._classes[k]
        return {**base, "elevation_m": round(float(self._elev[idx]), 1), "slope_deg": round(float(self._slope[idx]), 2),
                "slope_class": c.id, "walkable": c.walkable, "vehicle": c.vehicle}

    def describe(self) -> dict:
        w, s, e, n = self._aoi
        bounds = [[s, w], [n, e]]
        return {
            "layer": self.name,
            "bounds": bounds,
            "resolution_m": self._resolution_m,
            "elevation_range_m": [int(round(float(np.nanmin(self._elev)))), int(round(float(np.nanmax(self._elev))))],
            "slope_classes": [asdict(c) for c in self._classes],
            "overlay": {"url": "/api/get-layer-two/walkability.png", "bounds": bounds},
            "hillshade_sources": self._store.available("relief"),
            "caveats": CAVEATS,
        }

    def sample(self, lon: float, lat: float, season: str | None = None) -> dict | None:
        return self.point(lon, lat)
```

- [ ] **Step 4: Run the test**

Run: `cd backend && .venv/bin/pytest tests/test_relief_getter.py -v`
Expected: 6 passed

---

### Task 7: POI normalisation

**Files:**
- Create: `backend/app/layers/poi/normalize.py`
- Test: `backend/tests/test_poi_normalize.py`

- [ ] **Step 1: Write the failing test**

```python
from app.layers.poi.normalize import CATEGORIES, DATASETS, normalize_feature, normalize_lon


def feat(lon, lat, **props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


def test_categories():
    assert CATEGORIES == ("mineral", "water_activity", "exploration_zone", "dunes", "geology", "place_name",
                          "observation")
    assert len(DATASETS) == 10


def test_normalize_lon_nested():
    assert normalize_lon([290.0, -11.0]) == [-70.0, -11.0]
    assert normalize_lon([[[-70.0, -12.0], [300.0, -12.0]]]) == [[[-70.0, -12.0], [-60.0, -12.0]]]


def test_mineral_mapping_and_id():
    f = normalize_feature("Aquieous_Mineral_Distribution_Options_clon0__0", 5, feat(-70, -12, FID=3, Class="sulfate"))
    p = f["properties"]
    assert (p["id"], p["category"], p["name"]) == ("Aquieous_Mineral_Distribution_Options_clon0__0:3", "mineral",
                                                   "Sulfate detection")
    assert p["raw"]["Class"] == "sulfate" and p["source"]


def test_id_falls_back_to_index():
    f = normalize_feature("Dune_Field__0", 7, feat(-70, -12, Dune_ID="2886-131", Dune_Type="Bd, L"))
    assert f["properties"]["id"] == "Dune_Field__0:7"
    assert f["properties"]["name"] == "Dune field 2886-131"


def test_other_mappings():
    cases = {
        "RSLs_Gullies_New_IcyCraters_clon0__0": ({"Type": "confirmed recurring slope lineae (RSL)"},
                                                 "water_activity", "Confirmed recurring slope lineae (RSL)"),
        "Hydrous_Mineral_Detections_OMEGA_CRISM_clon0__0": ({"Instrument": "CRISM"}, "mineral",
                                                            "Hydrous mineral detection"),
        "EZMars__0": ({"name": "Melas Chasma"}, "exploration_zone", "Melas Chasma exploration zone (centre)"),
        "EZMars__3": ({"name": "1007.03", "ez_name": "Melas Chasma"}, "exploration_zone", "Melas Chasma ROI 1007.03"),
        "EZMars__4": ({"name": "Coprates Chasma"}, "exploration_zone", "Coprates Chasma exploration zone boundary"),
        "SIM3292_Global_Geology__0": ({"Unit": "Aa", "UnitDesc": "Amazonian apron unit"}, "geology",
                                      "Amazonian apron unit (Aa)"),
        "combinedNom__0": ({"name": "Garni", "type": "Crater, craters"}, "place_name", "Garni"),
        "mars_mro_crism_mtrdr_c0a_humex_frt_sites__0": ({"ProductId": "FRT0000B64A_07_IF164J_MTR3",
                                                         "UTCstart": "2008-07-06T21:31:41.032"}, "observation",
                                                        "CRISM observation FRT0000B64A_07_IF164J_MTR3"),
    }
    for stem, (props, cat, name) in cases.items():
        p = normalize_feature(stem, 0, feat(-70, -12, **props))["properties"]
        assert (p["category"], p["name"]) == (cat, name), stem
        assert p["description"], stem


def test_null_geometry_kept():
    f = normalize_feature("combinedNom__0", 0, {"type": "Feature", "geometry": None, "properties": {"name": "X"}})
    assert f["geometry"] is None
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && .venv/bin/pytest tests/test_poi_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.layers.poi.normalize'`

- [ ] **Step 3: Write `backend/app/layers/poi/normalize.py`**

```python
"""Maps each downloaded Trek vector dataset to one common feature format.

Every output feature has properties: id, category, name, description, source, raw (original fields).
"""
from __future__ import annotations

CATEGORIES = ("mineral", "water_activity", "exploration_zone", "dunes", "geology", "place_name", "observation")
EZ_NOTE = "Candidate human exploration zone (NASA Exploration Zones workshop, 2015)."


def _s(value) -> str:
    return "" if value is None else str(value).strip()


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _links(p) -> str:
    links = [x for x in (_s(p.get("abstract_l")), _s(p.get("presentati"))) if x]
    return EZ_NOTE + (" Details: " + ", ".join(links) if links else "")


def _aqueous(p):
    cls = _s(p.get("Class")) or "aqueous mineral"
    return "mineral", f"{_cap(cls)} detection", f"Orbital detection of {cls} (aqueous mineral distribution map)."


def _hydrous(p):
    inst = _s(p.get("Instrument")) or "OMEGA/CRISM"
    return "mineral", "Hydrous mineral detection", f"Hydrous mineral detection by {inst}."


def _rsl(p):
    kind = _s(p.get("Type")) or "recurring slope lineae"
    ref = _s(p.get("Ref"))
    desc = "Seasonal dark streaks on slopes, possibly linked to briny water." + (f" Reference: {ref}." if ref else "")
    return "water_activity", _cap(kind), desc


def _ez_centre(p):
    return "exploration_zone", f"{_s(p.get('name'))} exploration zone (centre)", _links(p)


def _ez_roi(p):
    return ("exploration_zone", f"{_s(p.get('ez_name'))} ROI {_s(p.get('name'))}",
            "Region of interest inside a candidate human exploration zone (NASA workshop, 2015).")


def _ez_boundary(p):
    return "exploration_zone", f"{_s(p.get('name'))} exploration zone boundary", _links(p)


def _dunes(p):
    kind = _s(p.get("Dune_Type")) or "unknown"
    return "dunes", f"Dune field {_s(p.get('Dune_ID'))}", f"Dune field (type codes: {kind}); a sign of active wind."


def _geology(p):
    return "geology", f"{_s(p.get('UnitDesc'))} ({_s(p.get('Unit'))})", "Geologic map unit (USGS SIM 3292)."


def _place(p):
    parts = [x for x in (_s(p.get("type")), _s(p.get("origin"))) if x]
    return "place_name", _s(p.get("name")), ". ".join(x.rstrip(".") for x in parts) + "." if parts else "IAU name."


def _crism(p):
    date = _s(p.get("UTCstart"))[:10]
    return ("observation", f"CRISM observation {_s(p.get('ProductId'))}",
            "CRISM targeted observation footprint" + (f", acquired {date}." if date else "."))


# file stem -> (source title, mapper(properties) -> (category, name, description))
DATASETS = {
    "Aquieous_Mineral_Distribution_Options_clon0__0": ("Aqueous Mineral Distribution (NASA Trek)", _aqueous),
    "Hydrous_Mineral_Detections_OMEGA_CRISM_clon0__0": ("Hydrous Mineral Detections, OMEGA/CRISM (NASA Trek)", _hydrous),
    "RSLs_Gullies_New_IcyCraters_clon0__0": ("RSLs, Fresh Gullies, New and Icy Craters (NASA Trek)", _rsl),
    "EZMars__0": ("NASA Human Exploration Zones: zones (NASA Trek)", _ez_centre),
    "EZMars__3": ("NASA Human Exploration Zones: regions of interest (NASA Trek)", _ez_roi),
    "EZMars__4": ("NASA Human Exploration Zones: zone boundaries (NASA Trek)", _ez_boundary),
    "Dune_Field__0": ("Mars Global Digital Dune Database (NASA Trek)", _dunes),
    "SIM3292_Global_Geology__0": ("Geologic Map of Mars, USGS SIM 3292 (NASA Trek)", _geology),
    "combinedNom__0": ("IAU Mars nomenclature (NASA Trek)", _place),
    "mars_mro_crism_mtrdr_c0a_humex_frt_sites__0": ("CRISM targeted observations (NASA Trek)", _crism),
}
CLIP_TO_AOI = {"SIM3292_Global_Geology__0"}


def normalize_lon(coords):
    """Recursively convert 0..360 east longitudes to -180..180."""
    if coords and isinstance(coords[0], (int, float)):
        x = coords[0] - 360 if coords[0] > 180 else coords[0]
        return [x, *coords[1:]]
    return [normalize_lon(c) for c in coords]


def normalize_feature(stem: str, index: int, feature: dict) -> dict:
    title, mapper = DATASETS[stem]
    props = feature.get("properties") or {}
    category, name, description = mapper(props)
    geom = feature.get("geometry")
    if geom:
        geom = {**geom, "coordinates": normalize_lon(geom["coordinates"])}
    return {"type": "Feature", "geometry": geom,
            "properties": {"id": f"{stem}:{props.get('FID', index)}", "category": category, "name": name,
                           "description": description, "source": title, "raw": props}}
```

- [ ] **Step 4: Run the test**

Run: `cd backend && .venv/bin/pytest tests/test_poi_normalize.py -v`
Expected: 6 passed

---

### Task 8: POI getter (Layer 3)

**Files:**
- Create: `backend/app/layers/poi/getter.py`
- Test: `backend/tests/test_poi_getter.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from shapely.geometry import shape

from app.core.config import Settings
from app.layers.base import LayerUnavailable
from app.layers.poi.getter import PoiGetter
from app.tiles.store import TileStore


def make(settings):
    return PoiGetter(settings, TileStore(settings.raw_dir / "tiles", settings.tile_sources, settings.aoi))


@pytest.fixture(scope="module")
def poi(fixture_settings):
    return make(fixture_settings)


def test_loads_known_files_only(poi):
    feats = poi.features()
    assert len(feats) == 7  # unknown_dataset__0 is skipped
    assert all(f["properties"]["category"] for f in feats)


def test_describe_counts_and_overlay(poi):
    d = poi.describe()
    assert d["type"] == "FeatureCollection" and d["layer"] == "poi"
    assert d["categories"] == {"mineral": 3, "water_activity": 1, "exploration_zone": 1, "dunes": 0,
                               "geology": 1, "place_name": 1, "observation": 0}
    assert [o["id"] for o in d["overlays"]] == ["crism_sulfate"]


def test_category_filter(poi):
    d = poi.describe({"mineral"})
    assert len(d["features"]) == 3
    assert d["categories"]["geology"] == 1  # counts always describe the full set


def test_longitude_normalised(poi):
    silica = next(f for f in poi.features() if f["properties"]["name"] == "Silica detection")
    assert silica["geometry"]["coordinates"] == [-70.0, -11.0]


def test_geology_clipped_to_aoi(poi):
    geo = next(f for f in poi.features() if f["properties"]["category"] == "geology")
    w, s, e, n = shape(geo["geometry"]).bounds
    assert (w, s, e, n) == pytest.approx((-71.8, -13.4, -70.0, -11.0))


def test_sample_radius(poi):
    near = poi.sample(-70.0, -12.0)
    ids = [x["id"] for x in near]
    assert "Aquieous_Mineral_Distribution_Options_clon0__0:0" in ids
    assert "EZMars__3:0" in ids                     # polygon corner touches the point
    assert "combinedNom__0:0" not in ids            # Garni is ~34 km away
    assert near == sorted(near, key=lambda x: x["distance_km"])


def test_missing_features_dir(tmp_path):
    with pytest.raises(LayerUnavailable) as ex:
        make(Settings(data_dir=tmp_path))
    assert "--only pois" in ex.value.fix
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && .venv/bin/pytest tests/test_poi_getter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.layers.poi.getter'`

- [ ] **Step 3: Write `backend/app/layers/poi/getter.py`**

```python
"""Layer 3: points of interest. All Trek vector files in one normalised FeatureCollection."""
from __future__ import annotations

import json
import logging
import math

import numpy as np
import shapely
from shapely.geometry import Point, box, mapping, shape

from app.layers.base import LayerUnavailable
from app.layers.poi.normalize import CATEGORIES, CLIP_TO_AOI, DATASETS, normalize_feature
from app.layers.relief.slope import M_PER_DEG
from app.tiles.store import TileStore

log = logging.getLogger(__name__)


class PoiGetter:
    name = "poi"

    def __init__(self, settings, store: TileStore):
        folder = settings.raw_dir / "features"
        files = sorted(folder.glob("*.geojson")) if folder.is_dir() else []
        if not files:
            raise LayerUnavailable(f"No point-of-interest files found in {folder}",
                                   "python scripts/download_data.py --only pois")
        w, s, e, n = settings.aoi
        aoi_box = box(w, s, e, n)
        features = []
        for f in files:
            if f.stem not in DATASETS:
                log.warning("Skipping unknown POI dataset %s", f.name)
                continue
            for i, raw in enumerate(json.loads(f.read_text()).get("features", [])):
                feat = normalize_feature(f.stem, i, raw)
                if f.stem in CLIP_TO_AOI and feat["geometry"]:
                    clipped = shape(feat["geometry"]).intersection(aoi_box)
                    if clipped.is_empty:
                        continue
                    feat["geometry"] = json.loads(json.dumps(mapping(clipped)))  # tuples -> lists
                features.append(feat)
        self._features = features
        self._store = store
        self._radius_km = settings.poi_sample_radius_km
        # Local flat projection in km (good enough over the ~4 deg demo area) for distance checks.
        self._k = np.array([M_PER_DEG / 1000 * math.cos(math.radians((s + n) / 2)), M_PER_DEG / 1000])
        self._geoms_km = [shapely.transform(shape(f["geometry"]), lambda c: c * self._k) if f["geometry"] else None
                          for f in features]

    def features(self, categories: set[str] | None = None) -> list[dict]:
        if not categories:
            return list(self._features)
        return [f for f in self._features if f["properties"]["category"] in categories]

    def describe(self, categories: set[str] | None = None) -> dict:
        counts = {c: 0 for c in CATEGORIES}
        for f in self._features:
            counts[f["properties"]["category"]] += 1
        return {"type": "FeatureCollection", "layer": self.name, "categories": counts,
                "overlays": self._store.available("poi"), "features": self.features(categories)}

    def sample(self, lon: float, lat: float, season: str | None = None) -> list[dict]:
        """Features within poi_sample_radius_km of the point, nearest first."""
        p = Point(lon * self._k[0], lat * self._k[1])
        near = []
        for f, g in zip(self._features, self._geoms_km):
            if g is None:
                continue
            d = g.distance(p)
            if d <= self._radius_km:
                pr = f["properties"]
                near.append({"id": pr["id"], "category": pr["category"], "name": pr["name"],
                             "distance_km": round(d, 2)})
        return sorted(near, key=lambda x: x["distance_km"])
```

- [ ] **Step 4: Run the test**

Run: `cd backend && .venv/bin/pytest tests/test_poi_getter.py -v`
Expected: 7 passed

---

### Task 9: Weather build script

**Files:**
- Create: `scripts/build_weather.py`
- Test: `backend/tests/test_build_weather.py`

- [ ] **Step 1: Write the failing test**

```python
"""build_weather.py must reproduce the files made by the skill's own scripts 06 + 07 exactly."""
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "data/raw/mdad/MDAD_original"
REF = REPO / "data/derived/weather_skill_reference"

pytestmark = pytest.mark.skipif(not SRC.is_file() or not REF.is_dir(),
                                reason="needs data/raw/mdad and data/derived/weather_skill_reference")


def load_script():
    spec = importlib.util.spec_from_file_location("build_weather", REPO / "scripts/build_weather.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_matches_skill_output(tmp_path):
    info = load_script().build(SRC, tmp_path)
    assert info == {"cells": 6400, "aoi_frames": 4}
    for name in ("context_weather_frames.geojson", "aoi_weather_frames.json"):
        assert json.loads((tmp_path / name).read_text()) == json.loads((REF / name).read_text()), name
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && .venv/bin/pytest tests/test_build_weather.py -v`
Expected: FAIL — `FileNotFoundError` for `scripts/build_weather.py`

- [ ] **Step 3: Write `scripts/build_weather.py`**

Functions below are copied from `context/skills/mars-mvp-data/scripts/06_mdad_weather.py` and `07_weather_confidence.py` with only the I/O changed (no CSV round-trip — checked: it changes no float values — no figures, no global run).

```python
#!/usr/bin/env python3
"""Build the Layer 4 weather files from the downloaded Mars Dust Activity Database (MDAD).

Input : data/raw/mdad/MDAD_original                         (fetched by scripts/download_data.py)
Output: data/derived/weather/context_weather_frames.geojson  1 deg cells x 4 seasons, Valles Marineris (served by the API)
        data/derived/weather/aoi_weather_frames.json         East Melas demo area x 4 seasons

Port of context/skills/mars-mvp-data/scripts/06_mdad_weather.py and 07_weather_confidence.py: same constants, rules
and messages. It is a copy because importing those scripts creates outputs/ and data/ folders inside the skill
directory. If the confidence rules change, change them in both places.

Usage (from repo root):
  pip install -r scripts/requirements.txt
  python scripts/build_weather.py [--src PATH] [--out DIR]
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "data" / "raw" / "mdad" / "MDAD_original"
DEFAULT_OUT = ROOT / "data" / "derived" / "weather"

AOI = (-71.8, -13.4, -68.0, -10.0)          # East Melas demo area (west, south, east, north)
CONTEXT = (-90.0, -30.0, -50.0, 10.0)       # Valles Marineris grid
R = 3389.5  # km, Mars mean radius
KM_PER_DEG = 2 * math.pi * R / 360

# Ls quarters. The AOI is at ~12 S, so seasons are named for the SOUTHERN hemisphere.
SEASONS = [(0, 90, "S. Autumn (Ls 0-90)"), (90, 180, "S. Winter (Ls 90-180)"),
           (180, 270, "S. Spring (Ls 180-270, perihelion)"), (270, 360, "S. Summer (Ls 270-360)")]

# ---------------- thresholds (keep in sync with skill script 07)
MIN_YEARS_RELIABLE = 6.0
MIN_YEARS_ANY = 3.0
MIN_STORMS_RELIABLE = 5
MAX_SINGLE_YEAR_SHARE = 0.5
MAX_MISSING_SHARE = 0.5
NEIGHBOUR_RADIUS_DEG = 3.0
RISK_BINS = [(1.0, "Low"), (4.0, "Moderate"), (np.inf, "High")]  # storm-days per Mars year
GLOBAL_CAVEAT = ("Source: MDAD, MY24-32 (1999-2015). Dust storms smaller than ~100,000 km² are not reliably "
                 "catalogued, and storm footprints are ellipse approximations (no outlines in the source). "
                 "Values are historical frequencies, not forecasts.")


# ---------------- from skill script 06
def season_of(ls):
    for a, b, n in SEASONS:
        if a <= ls < b:
            return n
    return SEASONS[-1][2]


def load(src):
    d = pd.read_csv(src)
    d.columns = [c.strip() for c in d.columns]
    for c in d.columns:
        if d[c].dtype == object or str(d[c].dtype) == "str":
            d[c] = d[c].astype(str).str.strip()
    d = d.rename(columns={"Mars Year": "my", "Mission subphase": "subphase", "Sol": "sol", "Ls": "ls",
                          "Centroid longitude": "lon", "Centroid latitude": "lat", "Area (square km)": "area_km2",
                          "Member ID": "member", "Sequence ID": "sequence", "Maximum latitude": "lat_max",
                          "Minimum latitude": "lat_min", "Confidence interval": "conf", "Missing data": "missing"})
    d["storm_id"] = d.subphase + "_" + d.member  # member ids restart per subphase
    d["season"] = d.ls.apply(season_of)
    b_km = np.maximum((d.lat_max - d.lat_min) / 2 * KM_PER_DEG, 1.0)
    a_km = d.area_km2 / (math.pi * b_km)
    d["semi_lat_deg"] = b_km / KM_PER_DEG
    d["semi_lon_deg"] = a_km / (KM_PER_DEG * np.maximum(np.cos(np.radians(d.lat)), 0.05))
    d["lat_c"] = (d.lat_max + d.lat_min) / 2
    return d


def inside(d, lon, lat):
    dlon = (lon - d.lon + 180) % 360 - 180
    return (dlon / d.semi_lon_deg) ** 2 + ((lat - d.lat_c) / d.semi_lat_deg) ** 2 <= 1


def hits_box(d, box, step=0.25):
    w, s, e, n = box
    pts = [(x, y) for x in np.arange(w, e + 1e-9, step) for y in np.arange(s, n + 1e-9, step)]
    mask = np.zeros(len(d), bool)
    frac = np.zeros(len(d))
    for x, y in pts:
        m = inside(d, x, y).to_numpy()
        mask |= m
        frac += m
    out = d[mask].copy()
    out["aoi_cover_frac"] = (frac[mask] / len(pts)).round(2)
    return out


# ---------------- from skill script 07
def risk_of(rate):
    for edge, name in RISK_BINS:
        if rate < edge:
            return name


def observation_gaps(d, min_gap_deg=10):
    gaps = []
    for my, g in d.groupby("my"):
        have = set((g.ls // 5).astype(int))
        lo = 30 if my == 24 else 0
        hi = 34 if my == 32 else 72
        run = []
        for k in list(range(lo, hi)) + [None]:
            if k is not None and k not in have:
                run.append(k)
                continue
            if len(run) * 5 >= min_gap_deg:
                gaps.append(dict(my=my, ls_from=run[0] * 5, ls_to=run[-1] * 5 + 5))
            run = []
    return pd.DataFrame(gaps)


def observed_years(gaps, lat):
    out = {}
    for a, b, name in SEASONS:
        yrs = 0.0
        for my in range(24, 33):
            if abs(lat) > 60 and my < 28:
                continue
            lo = max(a, 150) if my == 24 else a
            hi = min(b, 171) if my == 32 else b
            span = max(0.0, hi - lo)
            for _, gp in gaps[gaps.my == my].iterrows():
                span -= max(0.0, min(hi, gp.ls_to) - max(lo, gp.ls_from))
            yrs += max(0.0, span) / (b - a)
        out[name] = round(yrs, 2)
    return out


def poisson_ci(k, t):
    lo = 0.0 if k == 0 else chi2.ppf(0.025, 2 * k) / 2
    hi = chi2.ppf(0.975, 2 * k + 2) / 2
    return lo / t, hi / t


def evaluate(h, years):
    n_days, n_storms = len(h), h.storm_id.nunique() if len(h) else 0
    f = dict(observed_years=years, storm_days=n_days, storms=n_storms, reasons=[])
    if years < MIN_YEARS_ANY:
        f.update(confidence="insufficient_data", rate=None, risk=None)
        f["reasons"].append(f"only {years:.1f} Mars years of imaging cover this frame and season "
                            f"(need ≥{MIN_YEARS_ANY:.0f})")
        return f
    rate = n_days / years
    s_lo, s_hi = poisson_ci(n_storms, years)
    days_per_storm = n_days / n_storms if n_storms else 1.0
    f.update(rate=round(rate, 2), rate_ci95=[round(s_lo * days_per_storm, 2), round(s_hi * days_per_storm, 2)],
             storms_per_year=round(n_storms / years, 2), risk=risk_of(rate))
    if years < MIN_YEARS_RELIABLE:
        f["reasons"].append(f"only {years:.1f} Mars years observed (need ≥{MIN_YEARS_RELIABLE:.0f})")
    if 0 < n_storms < MIN_STORMS_RELIABLE:
        f["reasons"].append(f"only {n_storms} storm(s) recorded; too few for a stable frequency")
    if n_days:
        by_year = h.groupby("my").size()
        share = by_year.max() / n_days
        if share > MAX_SINGLE_YEAR_SHARE and n_days >= 3:
            top = int(by_year.idxmax())
            typical = (n_days - by_year.max()) / max(years - 1, 1)
            f["reasons"].append(f"{by_year.max()} of {n_days} storm-days come from a single Mars year (MY{top})")
            f.update(typical_year_rate=round(typical, 2), typical_year_risk=risk_of(typical),
                     extreme_year=dict(my=top, storm_days=int(by_year.max()), risk=risk_of(by_year.max())))
        miss = (h.missing == "yes").mean()
        if miss > MAX_MISSING_SHARE:
            f["reasons"].append(f"{miss:.0%} of storm records come from images with missing data")
    f["confidence"] = "approximate" if f["reasons"] else "reliable"
    if f["confidence"] == "reliable" and n_storms == 0:
        f["reasons"].append(f"no storms in {years:.1f} observed Mars years; upper 95 % bound "
                            f"{s_hi:.2f} storms/yr")
    return f


def message(f, season, where):
    s = season.split(" (")[0]
    if f["confidence"] == "reliable":
        return (f"{f['risk']} dust-storm risk in {s}: ~{f['rate']} storm-days per Mars year "
                f"({f['storms']} storms over {f['observed_years']} observed Mars years).")
    if f["confidence"] == "approximate":
        main = f.get("typical_year_risk") or f["risk"]
        val = f.get("typical_year_rate", f["rate"])
        txt = (f"APPROXIMATE: not enough data to reliably calculate the risk for {where} in {s}. "
               f"Best estimate: {main} (~{val} storm-days per Mars year")
        txt += ", typical year)" if "typical_year_rate" in f else f"; 95 % range {f['rate_ci95'][0]}–{f['rate_ci95'][1]})"
        if "extreme_year" in f:
            e = f["extreme_year"]
            txt += f". Extreme year MY{e['my']}: {e['storm_days']} storm-days ({e['risk']})"
        return txt + ". Why: " + "; ".join(f["reasons"]) + "."
    est = f.get("neighbour_estimate")
    base = f"NOT ENOUGH DATA: dust-storm risk cannot be reliably calculated for {where} in {s} ({f['reasons'][0]})."
    if est:
        return base + (f" Approximate estimate from {est['n_frames']} neighbouring frames: {est['risk']} "
                       f"(~{est['rate']} storm-days per Mars year). Indicative only.")
    return base + " No approximate estimate is possible (no usable neighbouring frames)."


def grid_frames(d, gaps, box, cell):
    w, s, e, n = box
    sub = d[(d.lat_c - d.semi_lat_deg <= n) & (d.lat_c + d.semi_lat_deg >= s)]
    frames = []
    for lat in np.arange(s + cell / 2, n, cell):
        yrs = observed_years(gaps, lat)
        for lon in np.arange(w + cell / 2, e, cell):
            hit = sub[inside(sub, lon, lat)]
            for *_, sn in SEASONS:
                f = evaluate(hit[hit.season == sn], yrs[sn])
                frames.append(dict(lon=round(lon, 3), lat=round(lat, 3), season=sn, **f))
    df = pd.DataFrame(frames)
    usable = df[df.confidence != "insufficient_data"]
    for i in df.index[df.confidence == "insufficient_data"]:
        r = df.loc[i]
        nb = usable[(usable.season == r.season) & ((usable.lon - r.lon).abs() <= NEIGHBOUR_RADIUS_DEG)
                    & ((usable.lat - r.lat).abs() <= NEIGHBOUR_RADIUS_DEG)]
        if len(nb):
            m = float(nb.rate.mean())
            df.at[i, "neighbour_estimate"] = {"rate": round(m, 2), "risk": risk_of(m), "n_frames": len(nb)}
    if "neighbour_estimate" not in df:
        df["neighbour_estimate"] = None
    df = df.astype(object).where(df.notna(), None)
    clean = [{k: v for k, v in r.items() if v is not None} for r in df.to_dict("records")]
    df["message"] = [message(r, r["season"], "this area") for r in clean]
    return df


# ---------------- build
def build(src: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = load(src)
    gaps = observation_gaps(d)

    aoi_lat = (AOI[1] + AOI[3]) / 2
    yrs = observed_years(gaps, aoi_lat)
    h = hits_box(d, AOI)
    aoi = []
    for *_, sn in SEASONS:
        f = evaluate(h[h.season == sn], yrs[sn])
        f["season"] = sn
        f["message"] = message(f, sn, "East Melas")
        aoi.append(f)
    (out / "aoi_weather_frames.json").write_text(json.dumps(
        {"aoi": AOI, "caveat": GLOBAL_CAVEAT, "frames": aoi}, indent=1, default=float))

    ctx = grid_frames(d, gaps, CONTEXT, 1.0)
    feats = [{"type": "Feature",
              "geometry": {"type": "Polygon", "coordinates": [[[r["lon"] - .5, r["lat"] - .5], [r["lon"] + .5, r["lat"] - .5],
                                                              [r["lon"] + .5, r["lat"] + .5], [r["lon"] - .5, r["lat"] + .5],
                                                              [r["lon"] - .5, r["lat"] - .5]]]},
              "properties": {k: v for k, v in r.items() if k not in ("lon", "lat")}}
             for r in ctx.to_dict("records")]
    (out / "context_weather_frames.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "caveat": GLOBAL_CAVEAT, "features": feats}, default=float))
    return {"cells": len(feats), "aoi_frames": len(aoi)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC, help="MDAD CSV (default: data/raw/mdad/MDAD_original)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output folder (default: data/derived/weather)")
    args = ap.parse_args()
    if not args.src.is_file():
        raise SystemExit(f"{args.src} not found. Run: python scripts/download_data.py --only mdad")
    info = build(args.src, args.out)
    print(f"wrote {info['cells']} weather cells and {info['aoi_frames']} demo-area frames to {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test**

Run: `cd backend && .venv/bin/pytest tests/test_build_weather.py -v`
Expected: 1 passed (takes ~5–10 s). If it fails on a value difference, diff one mismatching cell against the skill scripts before changing anything; do not loosen the test.

- [ ] **Step 5: Rebuild the real weather files with the new script**

Run: `backend/.venv/bin/python scripts/build_weather.py`
Expected: `wrote 6400 weather cells and 4 demo-area frames to …/data/derived/weather`

---

### Task 10: Weather getter (Layer 4)

**Files:**
- Create: `backend/app/layers/weather/getter.py`
- Test: `backend/tests/test_weather_getter.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from app.core.config import Settings
from app.layers.base import LayerUnavailable
from app.layers.weather.getter import SEASONS, WeatherGetter, display_risk, display_style


def test_display_risk_is_null_safe():
    assert display_risk({"typical_year_risk": None, "risk": "High"}) == "High"
    assert display_risk({"typical_year_risk": "Low", "risk": "High"}) == "Low"
    assert display_risk({"typical_year_risk": None, "risk": None,
                         "neighbour_estimate": {"risk": "Moderate"}}) == "Moderate"
    assert display_risk({"typical_year_risk": None, "risk": None, "neighbour_estimate": None}) is None


def test_display_style():
    assert display_style({"confidence": "reliable"}) == "solid"
    assert display_style({"confidence": "approximate"}) == "hatched"
    assert display_style({"confidence": "insufficient_data"}) == "grey"


@pytest.fixture(scope="module")
def weather(fixture_settings):
    return WeatherGetter(fixture_settings)


def test_seasons():
    assert list(SEASONS) == ["autumn", "winter", "spring", "summer"]


def test_describe_winter(weather):
    d = weather.describe("winter")
    assert d["type"] == "FeatureCollection" and d["season"] == "winter"
    assert d["season_name"] == "S. Winter (Ls 90-180)"
    assert d["caveat"] == "Fixture caveat."
    assert d["aoi_summary"]["message"] == "AOI winter fixture."
    assert set(d["legend"]) == {"Low", "Moderate", "High"}
    by_lon = {f["geometry"]["coordinates"][0][0][0]: f["properties"] for f in d["features"]}
    assert (by_lon[-70.0]["display_risk"], by_lon[-70.0]["display_style"]) == ("High", "solid")
    assert (by_lon[-71.0]["display_risk"], by_lon[-71.0]["display_style"]) == ("Low", "hatched")
    assert (by_lon[-72.0]["display_risk"], by_lon[-72.0]["display_style"]) == ("Moderate", "grey")
    assert by_lon[-71.0]["message"].startswith("APPROXIMATE:")  # verbatim


def test_cells_per_season(weather):
    assert all(len(weather.cells(k)) == 3 for k in SEASONS)


def test_sample_all_seasons(weather):
    s = weather.sample(-69.2, -11.9)
    assert set(s) == set(SEASONS)
    assert s["winter"]["risk"] == "High" and s["winter"]["confidence"] == "reliable"
    assert weather.sample(0.0, 0.0) is None


def test_missing_files(tmp_path):
    with pytest.raises(LayerUnavailable) as ex:
        WeatherGetter(Settings(data_dir=tmp_path))
    assert ex.value.fix == "python scripts/build_weather.py"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && .venv/bin/pytest tests/test_weather_getter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.layers.weather.getter'`

- [ ] **Step 3: Write `backend/app/layers/weather/getter.py`**

```python
"""Layer 4: seasonal dust-storm risk on the 1 deg Valles Marineris grid (built by scripts/build_weather.py)."""
from __future__ import annotations

import json
import math

from app.layers.base import LayerUnavailable

SEASONS = {
    "autumn": "S. Autumn (Ls 0-90)",
    "winter": "S. Winter (Ls 90-180)",
    "spring": "S. Spring (Ls 180-270, perihelion)",
    "summer": "S. Summer (Ls 270-360)",
}
STYLE = {"reliable": "solid", "approximate": "hatched", "insufficient_data": "grey"}


def display_risk(p: dict) -> str | None:
    """Skill rule: typical-year risk if set, else risk, else the neighbour estimate. Null counts as absent."""
    if p.get("typical_year_risk"):
        return p["typical_year_risk"]
    if p.get("risk"):
        return p["risk"]
    return (p.get("neighbour_estimate") or {}).get("risk")


def display_style(p: dict) -> str:
    return STYLE.get(p.get("confidence"), "grey")


def _cell_key(lon: float, lat: float) -> tuple[float, float]:
    """Centre of the 1 deg cell containing the point."""
    return round(math.floor(lon) + 0.5, 3), round(math.floor(lat) + 0.5, 3)


class WeatherGetter:
    name = "weather"

    def __init__(self, settings):
        folder = settings.derived_dir / "weather"
        grid_file, aoi_file = folder / "context_weather_frames.geojson", folder / "aoi_weather_frames.json"
        missing = [f.name for f in (grid_file, aoi_file) if not f.is_file()]
        if missing:
            raise LayerUnavailable(f"Weather files not found in {folder}: {', '.join(missing)}",
                                   "python scripts/build_weather.py")
        grid = json.loads(grid_file.read_text())
        aoi = json.loads(aoi_file.read_text())
        key_of = {v: k for k, v in SEASONS.items()}
        self._caveat = grid.get("caveat", "")
        self._legend = dict(settings.risk_colors)
        self._cells = {k: [] for k in SEASONS}
        self._by_cell: dict[tuple[float, float], dict] = {}
        for f in grid["features"]:
            key = key_of.get(f["properties"].get("season"))
            if key is None:
                continue
            p = {**f["properties"]}
            p["display_risk"] = display_risk(p)
            p["display_style"] = display_style(p)
            self._cells[key].append({"type": "Feature", "geometry": f["geometry"], "properties": p})
            ring = f["geometry"]["coordinates"][0][:4]
            centre = (round(sum(x for x, _ in ring) / 4, 3), round(sum(y for _, y in ring) / 4, 3))
            self._by_cell.setdefault(centre, {})[key] = {
                "risk": p["display_risk"], "confidence": p.get("confidence"), "message": p.get("message")}
        self._aoi = {key_of[fr["season"]]: fr for fr in aoi.get("frames", []) if fr.get("season") in key_of}

    def cells(self, season: str) -> list[dict]:
        return self._cells[season]

    def aoi_frame(self, season: str) -> dict | None:
        return self._aoi.get(season)

    def describe(self, season: str) -> dict:
        return {"type": "FeatureCollection", "layer": self.name, "season": season, "season_name": SEASONS[season],
                "caveat": self._caveat, "legend": self._legend, "aoi_summary": self.aoi_frame(season),
                "features": self._cells[season]}

    def sample(self, lon: float, lat: float, season: str | None = None) -> dict | None:
        """Risk, confidence and message of the cell containing the point, for all four seasons."""
        return self._by_cell.get(_cell_key(lon, lat))
```

- [ ] **Step 4: Run the test**

Run: `cd backend && .venv/bin/pytest tests/test_weather_getter.py -v`
Expected: 7 passed

---

### Task 11: Registry, app factory and HTTP routes

**Files:**
- Create: `backend/app/layers/registry.py`, `backend/app/schemas/layers.py`, `backend/app/api/routes/layers.py`, `backend/app/api/routes/tiles.py`
- Modify: `backend/main.py` (full replacement below)
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write the failing test**

```python
import io

from conftest import DEM_SHAPE
from PIL import Image


def test_hello_still_works(client):
    assert client.get("/api/hello").json() == {"message": "Hello from FastAPI"}


# ---- Layer 1 + tiles
def test_layer_one(client):
    d = client.get("/api/get-layer-one").json()
    assert d["default_source"] == "ctx_coprates"
    assert [s["id"] for s in d["sources"]] == ["ctx_coprates", "hirise"]


def test_tiles(client):
    r = client.get("/api/tiles/ctx_coprates/5/2/3")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get("/api/tiles/hillshade_color/5/2/3").headers["content-type"] == "image/jpeg"
    assert client.get("/api/tiles/ctx_coprates/5/2/99").status_code == 404
    assert client.get("/api/tiles/nope/5/2/3").status_code == 404
    assert client.get("/api/tiles/..%2F..%2Fetc/5/2/3").status_code == 404
    assert client.get("/api/tiles/ctx_coprates/5/2/abc").status_code == 422


# ---- Layer 2
def test_layer_two(client):
    d = client.get("/api/get-layer-two").json()
    assert len(d["slope_classes"]) == 5 and d["overlay"]["url"] == "/api/get-layer-two/walkability.png"
    assert [h["id"] for h in d["hillshade_sources"]] == ["hillshade_color"]


def test_walkability_png(client):
    r = client.get("/api/get-layer-two/walkability.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).size == (DEM_SHAPE[1], DEM_SHAPE[0])


def test_point(client):
    p = client.get("/api/get-layer-two/point", params={"lon": -70.0, "lat": -12.0}).json()
    assert p["slope_class"] == "walkable" and p["approximate"] is True
    out = client.get("/api/get-layer-two/point", params={"lon": -60.0, "lat": -12.0})
    assert out.status_code == 404 and "outside" in out.json()["detail"]
    assert client.get("/api/get-layer-two/point", params={"lon": -70.0}).status_code == 422


# ---- Layer 3
def test_layer_three(client):
    d = client.get("/api/get-layer-three").json()
    assert d["type"] == "FeatureCollection" and len(d["features"]) == 7
    assert d["overlays"][0]["id"] == "crism_sulfate"
    only = client.get("/api/get-layer-three", params={"category": "mineral, water_activity"}).json()
    assert {f["properties"]["category"] for f in only["features"]} == {"mineral", "water_activity"}
    bad = client.get("/api/get-layer-three", params={"category": "mineral,unicorns"})
    assert bad.status_code == 422 and "unicorns" in bad.json()["detail"]


# ---- Layer 4
def test_layer_four(client):
    d = client.get("/api/get-layer-four", params={"season": "winter"}).json()
    assert d["season"] == "winter" and len(d["features"]) == 3 and d["caveat"] == "Fixture caveat."
    styles = sorted(f["properties"]["display_style"] for f in d["features"])
    assert styles == ["grey", "hatched", "solid"]
    assert client.get("/api/get-layer-four").status_code == 422
    assert client.get("/api/get-layer-four", params={"season": "monsoon"}).status_code == 422


# ---- Missing data: every layer 503, server still up
def test_missing_data_gives_503(empty_client):
    expected_fix = {
        "/api/get-layer-one": "download_data.py --only tiles",
        "/api/get-layer-two": "download_data.py --only dem",
        "/api/get-layer-two/walkability.png": "download_data.py --only dem",
        "/api/get-layer-two/point?lon=-70&lat=-12": "download_data.py --only dem",
        "/api/get-layer-three": "download_data.py --only pois",
        "/api/get-layer-four?season=winter": "build_weather.py",
    }
    for url, fix in expected_fix.items():
        r = empty_client.get(url)
        assert r.status_code == 503, url
        assert fix in r.json()["fix"] and r.json()["detail"], url
    assert empty_client.get("/api/tiles/ctx_coprates/5/2/3").status_code == 404
    assert empty_client.get("/api/hello").status_code == 200
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -v`
Expected: FAIL — `ImportError: cannot import name 'create_app' from 'main'`

- [ ] **Step 3: Write `backend/app/layers/registry.py`**

```python
"""Builds the four layer getters once at startup and hands them to the API (and later the master graph)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.layers.base import LayerUnavailable
from app.layers.base_imagery.getter import BaseImageryGetter
from app.layers.poi.getter import PoiGetter
from app.layers.relief.getter import ReliefGetter
from app.layers.weather.getter import WeatherGetter
from app.tiles.store import TileStore

log = logging.getLogger(__name__)


@dataclass
class Registry:
    tiles: TileStore
    layers: dict  # name -> getter, or the LayerUnavailable raised while building it

    def get(self, name: str):
        """The getter for `name`; raises LayerUnavailable (-> HTTP 503) if its data is missing."""
        layer = self.layers[name]
        if isinstance(layer, LayerUnavailable):
            raise layer
        return layer

    def status(self) -> dict:
        return {n: "ok" if not isinstance(g, LayerUnavailable) else g.detail for n, g in self.layers.items()}


def _try(name, factory):
    try:
        return factory()
    except LayerUnavailable as ex:
        log.warning("Layer %s unavailable: %s (fix: %s)", name, ex.detail, ex.fix)
        return ex


def build_registry(settings) -> Registry:
    store = TileStore(settings.raw_dir / "tiles", settings.tile_sources, settings.aoi)
    return Registry(store, {
        "base_imagery": _try("base_imagery", lambda: BaseImageryGetter(store)),
        "relief": _try("relief", lambda: ReliefGetter(settings, store)),
        "poi": _try("poi", lambda: PoiGetter(settings, store)),
        "weather": _try("weather", lambda: WeatherGetter(settings)),
    })
```

- [ ] **Step 4: Write `backend/app/schemas/layers.py`**

```python
"""Response models shown in /docs. Layers 3 and 4 are GeoJSON FeatureCollections and are returned as-is."""
from pydantic import BaseModel


class TileSource(BaseModel):
    id: str
    title: str
    tile_url: str
    format: str
    tile_size: int
    min_zoom: int
    max_zoom: int
    bounds: list[list[float]]
    coverage_note: str


class LayerOneResponse(BaseModel):
    layer: str
    default_source: str
    sources: list[TileSource]


class SlopeClassOut(BaseModel):
    id: str
    label: str
    min_deg: float
    max_deg: float
    color: str
    walkable: bool
    vehicle: bool


class Overlay(BaseModel):
    url: str
    bounds: list[list[float]]


class LayerTwoResponse(BaseModel):
    layer: str
    bounds: list[list[float]]
    resolution_m: int
    elevation_range_m: list[int]
    slope_classes: list[SlopeClassOut]
    overlay: Overlay
    hillshade_sources: list[TileSource]
    caveats: list[str]


class PointResponse(BaseModel):
    lon: float
    lat: float
    elevation_m: float | None
    slope_deg: float | None
    slope_class: str | None
    walkable: bool
    vehicle: bool
    approximate: bool
```

- [ ] **Step 5: Write `backend/app/api/routes/layers.py`**

```python
"""/api/get-layer-one … four: thin wrappers around the layer getters."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from app.layers.poi.normalize import CATEGORIES
from app.layers.registry import Registry
from app.schemas.layers import LayerOneResponse, LayerTwoResponse, PointResponse

router = APIRouter(prefix="/api", tags=["layers"])
GEOJSON = {200: {"description": "GeoJSON FeatureCollection", "content": {"application/json": {}}}}


def _registry(request: Request) -> Registry:
    return request.app.state.layers


@router.get("/get-layer-one", response_model=LayerOneResponse, summary="Layer 1: base imagery sources")
def get_layer_one(request: Request):
    return _registry(request).get("base_imagery").describe()


@router.get("/get-layer-two", response_model=LayerTwoResponse, summary="Layer 2: relief and walkability")
def get_layer_two(request: Request):
    return _registry(request).get("relief").describe()


@router.get("/get-layer-two/walkability.png", response_class=Response, summary="Layer 2: walkability overlay",
            responses={200: {"content": {"image/png": {}}}})
def get_walkability_png(request: Request):
    return Response(_registry(request).get("relief").walkability_png(), media_type="image/png")


@router.get("/get-layer-two/point", response_model=PointResponse, summary="Layer 2: elevation and slope at a point")
def get_relief_point(request: Request, lon: float = Query(..., ge=-180, le=180),
                     lat: float = Query(..., ge=-90, le=90)):
    result = _registry(request).get("relief").point(lon, lat)
    if result is None:
        raise HTTPException(404, "Point is outside the area covered by the elevation data (East Melas demo area).")
    return result


@router.get("/get-layer-three", summary="Layer 3: points of interest", responses=GEOJSON)
def get_layer_three(request: Request, category: str | None = Query(
        None, description=f"Comma-separated filter. One or more of: {', '.join(CATEGORIES)}")):
    cats = None
    if category:
        cats = {c.strip() for c in category.split(",") if c.strip()}
        unknown = cats - set(CATEGORIES)
        if unknown:
            raise HTTPException(422, f"Unknown category: {', '.join(sorted(unknown))}. "
                                     f"Use one or more of: {', '.join(CATEGORIES)}")
    getter = _registry(request).get("poi")
    return JSONResponse(getter.describe(cats))


@router.get("/get-layer-four", summary="Layer 4: seasonal dust-storm risk", responses=GEOJSON)
def get_layer_four(request: Request, season: Literal["autumn", "winter", "spring", "summer"] = Query(...)):
    return JSONResponse(_registry(request).get("weather").describe(season))
```

- [ ] **Step 6: Write `backend/app/api/routes/tiles.py`**

```python
"""/api/tiles/{source}/{z}/{row}/{col}: map tiles straight from data/raw/tiles (no upstream calls)."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api", tags=["tiles"])


@router.get("/tiles/{source}/{z}/{row}/{col}", response_class=FileResponse, summary="One map tile")
def get_tile(request: Request, source: str, z: int, row: int, col: int):
    hit = request.app.state.layers.tiles.path(source, z, row, col)
    if hit is None:
        raise HTTPException(404, "Tile not available")
    path, media_type = hit
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})
```

- [ ] **Step 7: Replace `backend/main.py`**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import layers, tiles
from app.core.config import Settings
from app.layers.base import LayerUnavailable
from app.layers.registry import build_registry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.layers = build_registry(settings)  # loads every layer once
        yield

    app = FastAPI(title="Mars Map API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(LayerUnavailable)
    async def layer_unavailable(request: Request, exc: LayerUnavailable):
        return JSONResponse(status_code=503, content={"detail": exc.detail, "fix": exc.fix})

    @app.get("/api/hello")
    def hello():
        return {"message": "Hello from FastAPI"}

    app.include_router(layers.router)
    app.include_router(tiles.router)
    return app


app = create_app()
```

- [ ] **Step 8: Run the test**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -v`
Expected: 9 passed

- [ ] **Step 9: Run the whole suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all tests pass (the real-data weather build test included if `data/` is present).

---

### Task 12: Tests against the real downloaded data

**Files:**
- Test: `backend/tests/test_real_data.py`

- [ ] **Step 1: Write the test**

```python
"""Checks against the real downloaded data. Skipped automatically when data/ is not there."""
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

REPO_DATA = Path(__file__).resolve().parents[2] / "data"
pytestmark = pytest.mark.skipif(
    not (REPO_DATA / "raw/dem/dem_blend200m_aoi.tif").is_file()
    or not (REPO_DATA / "derived/weather/context_weather_frames.geojson").is_file(),
    reason="real data not downloaded / weather not built")


@pytest.fixture(scope="module")
def real():
    from app.core.config import Settings
    from main import create_app
    app = create_app(Settings(data_dir=REPO_DATA))
    with TestClient(app) as c:
        yield c, app.state.layers


def test_all_layers_loaded(real):
    _, reg = real
    assert reg.status() == {"base_imagery": "ok", "relief": "ok", "poi": "ok", "weather": "ok"}


def test_layer_one_sources(real):
    c, _ = real
    d = c.get("/api/get-layer-one").json()
    src = {s["id"]: s for s in d["sources"]}
    assert list(src) == ["ctx_coprates", "ctx_global", "hirise"]
    assert (src["ctx_coprates"]["min_zoom"], src["ctx_coprates"]["max_zoom"]) == (5, 9)
    assert src["hirise"]["tile_size"] == 512


def test_real_tile_served(real):
    c, _ = real
    tile = next((REPO_DATA / "raw/tiles/Coprates_EMelas_Chasm_CTX_BlockAdj_dd/9").rglob("*.png"))
    z, row, col = tile.parts[-3], tile.parts[-2], tile.stem
    r = c.get(f"/api/tiles/ctx_coprates/{z}/{row}/{col}")
    assert r.status_code == 200 and r.content == tile.read_bytes()


def test_slope_class_shares(real):
    _, reg = real
    cls = reg.get("relief").grid()["slope_class"]
    shares = [100 * float(np.mean(cls == k)) for k in range(5)]
    assert shares == pytest.approx([52.8, 32.7, 10.7, 3.5, 0.4], abs=0.1)


def test_point_matches_grid(real):
    c, reg = real
    lon, lat = -69.9, -11.7
    elev = reg.get("relief").grid()["elevation_m"]
    ny, nx = elev.shape
    row, col = int((-10.0 - lat) / 3.4 * ny), int((lon + 71.8) / 3.8 * nx)
    p = c.get("/api/get-layer-two/point", params={"lon": lon, "lat": lat}).json()
    assert p["elevation_m"] == pytest.approx(float(elev[row, col]), abs=0.1)


def test_poi_counts(real):
    c, _ = real
    d = c.get("/api/get-layer-three").json()
    assert len(d["features"]) == 50
    assert d["categories"] == {"mineral": 9, "water_activity": 3, "exploration_zone": 21, "dunes": 5,
                               "geology": 8, "place_name": 2, "observation": 2}


def _cell(features, lon, lat):
    for f in features:
        ring = f["geometry"]["coordinates"][0][:4]
        if (sum(x for x, _ in ring) / 4, sum(y for _, y in ring) / 4) == pytest.approx((lon, lat)):
            return f["properties"]
    raise AssertionError("cell not found")


def test_weather_demo_cell(real):
    c, _ = real
    winter = c.get("/api/get-layer-four", params={"season": "winter"}).json()
    assert len(winter["features"]) == 1600
    w = _cell(winter["features"], -69.5, -11.5)
    assert (w["display_risk"], w["display_style"]) == ("High", "solid")
    spring = c.get("/api/get-layer-four", params={"season": "spring"}).json()
    s = _cell(spring["features"], -69.5, -11.5)
    assert (s["display_risk"], s["display_style"]) == ("Low", "hatched")
    assert spring["aoi_summary"]["confidence"] == "approximate"
```

- [ ] **Step 2: Run it**

Run: `cd backend && .venv/bin/pytest tests/test_real_data.py -v`
Expected: 7 passed. If `test_poi_counts` differs, print `d["categories"]` and compare against the files in `data/raw/features/` before changing the expectation.

---

### Task 13: Docs, full run, live check

**Files:**
- Modify: `README.md`, `AGENTS.md`
- Delete: `.gitkeep` files in folders that now contain code

- [ ] **Step 1: Update `README.md`**

In the `## Data` section replace the code block with:

```bash
pip install -r scripts/requirements.txt
python scripts/download_data.py        # DEM, map tiles, POI vectors and MDAD storm data -> data/raw/
python scripts/build_weather.py        # Layer 4 dust-storm grid -> data/derived/weather/
```

In the `## Backend` section, after the `uvicorn` block, add:

~~~markdown
Layer endpoints: `/api/get-layer-one` (imagery sources), `/api/get-layer-two` (relief; `/point?lon=&lat=`, `/walkability.png`),
`/api/get-layer-three` (points of interest, `?category=`), `/api/get-layer-four?season=winter` (dust-storm risk),
`/api/tiles/{source}/{z}/{row}/{col}`. A layer whose data is missing answers 503 with the script to run.

Tests:

```bash
pip install -r requirements-dev.txt
pytest
```
~~~

- [ ] **Step 2: Update `AGENTS.md`**

Replace the `- Data:` line under `## Commands` with:

```markdown
- Data: `pip install -r scripts/requirements.txt && python scripts/download_data.py && python scripts/build_weather.py` (`download_data.py`: `--only dem|tiles|pois|mdad`, `--max-zoom N`, `--force`).
- Backend tests: `cd backend && pip install -r requirements-dev.txt && pytest`.
```

- [ ] **Step 3: Remove placeholders where code now lives**

Run:
```bash
rm -f backend/app/api/routes/.gitkeep backend/app/core/.gitkeep backend/app/layers/base_imagery/.gitkeep backend/app/layers/relief/.gitkeep backend/app/layers/poi/.gitkeep backend/app/layers/weather/.gitkeep backend/app/schemas/.gitkeep backend/app/tiles/.gitkeep backend/tests/.gitkeep
```
(`backend/app/graph/.gitkeep` and `backend/app/routing/.gitkeep` stay.)

- [ ] **Step 4: Full test run**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all passed, 0 skipped (real data present).

- [ ] **Step 5: Live check**

Run (background): `cd backend && .venv/bin/uvicorn main:app --port 8000`
Then, from the repo root:
```bash
curl -s localhost:8000/api/get-layer-one | head -c 300; echo
curl -s "localhost:8000/api/get-layer-two/point?lon=-69.9&lat=-11.7"; echo
curl -s "localhost:8000/api/get-layer-three?category=water_activity" | head -c 300; echo
curl -s "localhost:8000/api/get-layer-four?season=winter" -o /dev/null -w "%{http_code} %{size_download}\n"
T=$(cd data/raw/tiles/Coprates_EMelas_Chasm_CTX_BlockAdj_dd && find 5 -name '*.png' | head -1); curl -s "localhost:8000/api/tiles/ctx_coprates/${T%.png}" -o /dev/null -w "%{http_code} %{content_type}\n"
```
Expected: JSON for the first three; `200` and roughly 1.2 MB for layer four; `200 image/png` for the tile. Stop uvicorn afterwards.

- [ ] **Step 6: Confirm nothing was committed**

Run: `git status --short && git log --oneline -1`
Expected: modified/untracked files listed; last commit is still `4a7d21f upadted architecture conetxt`.
