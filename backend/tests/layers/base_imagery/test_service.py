from app.layers.base_imagery.ingest import ingest_imagery
from app.layers.base_imagery.service import BaseImageryGetter


def make(settings):
    return BaseImageryGetter(settings, ingest_imagery(settings))


def test_describe(fixture_settings):
    d = make(fixture_settings).describe()
    assert d["layer"] == "base_imagery"
    assert d["default_source"] == "ctx_coprates"
    assert [s["id"] for s in d["sources"]] == ["ctx_coprates", "hirise"]
    assert [s["role"] for s in d["sources"]] == ["primary", "zoom-in detail"]
    assert d["sources"][0]["tile_url"] == "/api/tiles/ctx_coprates/{z}/{y}/{x}"
    assert d["sources"][1]["tile_size"] == 512 and d["sources"][0]["bounds"] == [[-13.4, -71.8], [-10.0, -68.0]]


def test_tile_path_and_sample(fixture_settings):
    g = make(fixture_settings)
    assert g.tile_path("ctx_coprates", 5, 2, 3).is_file()
    assert g.tile_path("ctx_coprates", 9, 9, 9) is None and g.tile_path("nope", 5, 2, 3) is None
    assert g.sample(-70.0, -12.0) is None  # routing does not use imagery
