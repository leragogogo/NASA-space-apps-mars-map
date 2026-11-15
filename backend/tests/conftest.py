"""Shared test fixtures: a tiny, fully synthetic data/ folder that mimics the real layout."""
import json
import math
import os
from pathlib import Path

# Set before main.py is imported (it builds the app at import time). The database then defaults to
# app.db inside each test's data folder, never the real one.
TEST_JWT_SECRET = "test-secret-key-that-is-at-least-32-bytes"
os.environ["JWT_SECRET_KEY"] = TEST_JWT_SECRET
os.environ.pop("MARS_DATABASE_URL", None)

import numpy as np
import pytest
import tifffile
from fastapi.testclient import TestClient
from PIL import Image

FIXTURE_SLOPE_DEG = 6.0  # the fixture DEM is a plane rising to the east at this slope (cells are ~27 km wide: keep it gentle)
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
    from app.layers.contracts import GridSpec

    raw = root / "raw"
    # --- tiles: two base sources, one relief source (jpg), one poi source
    _tile(raw / "tiles/Coprates_EMelas_Chasm_CTX_BlockAdj_dd/5/2/3.png")
    _tile(raw / "tiles/Coprates_EMelas_Chasm_CTX_BlockAdj_dd/6/5/6.png")
    _tile(raw / "tiles/HiRISE_Global/5/1/1.png", size=512)
    _tile(raw / "tiles/Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw/5/2/3.jpg", fmt="JPEG")
    _tile(raw / "tiles/MC18_PolySulfate_Mineral_IndicatorV2_SP/5/2/3.png")

    # --- DEM: plane rising to the east with a constant slope
    dx_row, _ = GridSpec(*AOI, ncols=DEM_SHAPE[1], nrows=DEM_SHAPE[0]).metric_spacing()  # metres per row
    dem = (np.arange(DEM_SHAPE[1]) * dx_row[:, None] * math.tan(math.radians(FIXTURE_SLOPE_DEG)) - 3000.0
           ).astype("float32")
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
    weather = root / "raw/weather"
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
    return Settings(data_dir=fixture_data, grid_coarsen=1)  # grid = the fixture DEM shape


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


@pytest.fixture
def db_session(tmp_path):
    """A session on a fresh SQLite file with every table created."""
    from app.db.session import init_db, make_engine
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with init_db(engine)() as session:
        yield session
    engine.dispose()


def register_and_login(client, email: str = "astro@example.com", body_mass_kg: float = 80.0,
                       password: str = "correct-horse") -> dict:
    """Create a user through the API and return its Authorization header (reuses the account if it exists)."""
    r = client.post("/api/auth/register", json={"email": email, "password": password,
                                                "body_mass_kg": body_mass_kg, "birth_year": 1990})
    assert r.status_code in (201, 409), r.text
    r = client.post("/api/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class AuthedTestClient(TestClient):
    """A TestClient that registers a default user (80 kg) and sends its token once the app has started.

    Use `anonymous()`-style access by building a plain TestClient instead when a test needs no token.
    """

    def __enter__(self):
        super().__enter__()
        self.headers.update(register_and_login(self))
        return self
