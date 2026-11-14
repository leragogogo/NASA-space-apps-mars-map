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
    assert ex.value.fix == "python scripts/build_weather/build_weather.py"
