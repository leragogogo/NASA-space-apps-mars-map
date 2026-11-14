"""Checks against the real downloaded data. Skipped automatically when data/ is not there."""
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

REPO_DATA = Path(__file__).resolve().parents[3] / "data"  # backend/tests/integration/ -> repo root
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
