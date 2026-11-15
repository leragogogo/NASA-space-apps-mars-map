import numpy as np
import pytest

from app.core.config import Settings
from app.layers.contracts import SEASONS, Confidence, LayerDataError, RiskLevel
from app.layers.relief.ingest import grid_for
from app.layers.validate import validate_weather
from app.layers.weather.ingest import ingest_weather


@pytest.fixture(scope="module")
def weather(fixture_settings):
    return ingest_weather(fixture_settings, grid_for(fixture_settings))


def test_matches_contract(weather):
    validate_weather(weather)
    assert weather.seasons == SEASONS and weather.caveat == "Fixture caveat."
    assert len(weather.frames) == 3 and weather.risk.dtype == np.int8
    assert weather.source_files[0].startswith("weather/context_weather_frames.geojson:")


def test_frame_at_returns_full_frame_with_message(weather):
    # fixture grid is 6 x 8 over the AOI; the cell centred at (-70.5, -11.5) covers lon -71..-70, lat -12..-11
    frame = weather.frame_at(-70.6, -11.4, "S. Winter (Ls 90-180)")
    assert frame["message"].startswith("APPROXIMATE:") and frame["confidence"] == "approximate"
    assert weather.frame_at(-60.0, -11.4, "S. Winter (Ls 90-180)") is None  # outside the grid


def test_risk_arrays_use_display_risk_and_confidence_classes(weather):
    w = SEASONS.index("S. Winter (Ls 90-180)")
    cases = {-69.5: (RiskLevel.HIGH, Confidence.RELIABLE),
             -70.5: (RiskLevel.LOW, Confidence.APPROXIMATE),  # typical-year risk wins over the extreme year
             -71.5: (RiskLevel.MODERATE, Confidence.INSUFFICIENT_DATA)}  # neighbour estimate, labelled grey
    g = weather.grid
    for lon, expected in cases.items():
        row, col = g.lonlat_to_rc(lon, -11.5)
        assert (RiskLevel(int(weather.risk[w, row, col])), Confidence(int(weather.confidence[w, row, col]))) == expected


def test_cells_without_frame_are_marked_no_estimate(weather):
    row, col = weather.grid.lonlat_to_rc(-70.0, -13.0)  # south of every fixture cell
    assert weather.frame_idx[row, col] == -1
    assert weather.risk[0, row, col] == RiskLevel.NONE and weather.confidence[0, row, col] == Confidence.INSUFFICIENT_DATA


def test_missing_file_raises_with_fix(tmp_path, fixture_settings):
    with pytest.raises(LayerDataError) as ex:
        ingest_weather(Settings(data_dir=tmp_path), grid_for(fixture_settings))
    assert "--only weather" in ex.value.message
