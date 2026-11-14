import pytest

from app.core.config import Settings
from app.layers.base import LayerUnavailable
from app.layers.registry import build_registry


def test_all_layers_load_from_fixture_data(fixture_settings):
    reg = build_registry(fixture_settings)
    assert reg.status() == {"base_imagery": "ok", "relief": "ok", "poi": "ok", "weather": "ok"}
    assert reg.get("relief").name == "relief"
    assert reg.tiles.info("ctx_coprates") is not None


def test_missing_data_is_recorded_not_raised(tmp_path):
    reg = build_registry(Settings(data_dir=tmp_path))  # must not raise
    assert all(v != "ok" for v in reg.status().values())
    with pytest.raises(LayerUnavailable) as ex:
        reg.get("weather")
    assert ex.value.fix == "python scripts/build_weather/build_weather.py"
