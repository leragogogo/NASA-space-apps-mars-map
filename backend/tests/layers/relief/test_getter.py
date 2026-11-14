import numpy as np
import pytest
from tests.conftest import DEM_SHAPE, FIXTURE_SLOPE_DEG

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
