from app.core.config import AOI, REPO_ROOT, SLOPE_CLASSES, TILE_SOURCES, Settings


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
