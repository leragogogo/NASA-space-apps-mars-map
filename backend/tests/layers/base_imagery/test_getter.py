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
