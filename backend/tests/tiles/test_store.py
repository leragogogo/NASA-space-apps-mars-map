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
