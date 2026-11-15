import json
from pathlib import Path

import pytest

from weather import config as cfg
from weather.build import DEFAULT_OUT, build_weather_layer
from weather.tests.helpers import raw_row, write_mdad


def make_src(tmp_path):
    rows = []
    for my in range(24, 33):
        for k in range(0, 360, 5):
            rows.append(raw_row(my=my, sol=k, ls=float(k), lon=-70.0 + (k % 7), lat=-12.0 + (k % 5),
                                member=f"B01_{my}{k:03d}", lat_max=-2.0, lat_min=-22.0, area=2.0e6))
    p = tmp_path / "MDAD_original"
    write_mdad(p, rows)
    return p


def test_build_writes_the_three_files(tmp_path):
    out = tmp_path / "weather"
    summary = build_weather_layer(make_src(tmp_path), out)
    assert set(summary["files"]) == {"aoi_weather_frames.json", "context_weather_frames.geojson", "observation_gaps.csv"}
    assert summary["frames"] == 40 * 40 * 4
    gj = json.loads((out / "context_weather_frames.geojson").read_text())
    assert gj["type"] == "FeatureCollection" and gj["caveat"] == cfg.GLOBAL_CAVEAT and len(gj["features"]) == 6400
    f = gj["features"][0]
    ring = f["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == 5
    assert {"season", "confidence", "message"} <= set(f["properties"]) and "lon" not in f["properties"]
    aoi = json.loads((out / "aoi_weather_frames.json").read_text())
    assert [fr["season"] for fr in aoi["frames"]] == cfg.SEASON_NAMES and aoi["caveat"] == cfg.GLOBAL_CAVEAT


def test_missing_source_gives_actionable_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="download_data.py --only mdad"):
        build_weather_layer(tmp_path / "nope", tmp_path / "out")


REAL = DEFAULT_OUT / "context_weather_frames.geojson"


@pytest.mark.skipif(not REAL.exists(), reason="data/raw/weather not generated (run scripts/download_data.py)")
def test_generated_layer_matches_documented_counts():
    gj = json.loads(Path(REAL).read_text())
    counts = {}
    for f in gj["features"]:
        p = f["properties"]
        c = counts.setdefault(p["season"], {})
        c[p["confidence"]] = c.get(p["confidence"], 0) + 1
    assert counts[cfg.SEASON_NAMES[0]] == {"reliable": 1341, "approximate": 259}
    assert counts[cfg.SEASON_NAMES[1]] == {"reliable": 1128, "approximate": 472}
    assert counts[cfg.SEASON_NAMES[2]] == {"reliable": 220, "approximate": 1380}
    assert counts[cfg.SEASON_NAMES[3]] == {"reliable": 666, "approximate": 934}


# ------------------------------------------------------------------ risk thresholds from config/mars.yaml
def test_the_shipped_config_has_the_default_thresholds():
    assert cfg.risk_bins_from_config() == cfg.DEFAULT_RISK_BINS


def test_the_output_records_the_thresholds_it_was_computed_with(tmp_path):
    out = tmp_path / "weather"
    summary = build_weather_layer(make_src(tmp_path), out)
    assert summary["risk_bins"] == cfg.DEFAULT_RISK_BINS
    for name in ("context_weather_frames.geojson", "aoi_weather_frames.json"):
        assert json.loads((out / name).read_text())["risk_bins"] == cfg.DEFAULT_RISK_BINS


def test_other_thresholds_change_the_labels_and_are_recorded(tmp_path):
    src = make_src(tmp_path)
    default, strict = tmp_path / "default", tmp_path / "strict"
    build_weather_layer(src, default)
    build_weather_layer(src, strict, risk_bins={"moderate_from": 0.01, "high_from": 0.02})  # almost everything High
    def risks(folder):
        feats = json.loads((folder / "context_weather_frames.geojson").read_text())["features"]
        return [f["properties"].get("risk") for f in feats if f["properties"].get("risk")]
    assert risks(default) != risks(strict) and "High" in risks(strict)
    assert json.loads((strict / "aoi_weather_frames.json").read_text())["risk_bins"] == {"moderate_from": 0.01, "high_from": 0.02}


def test_thresholds_are_only_in_force_during_a_build(tmp_path):
    before = list(cfg.RISK_BINS)
    build_weather_layer(make_src(tmp_path), tmp_path / "w", risk_bins={"moderate_from": 2.0, "high_from": 9.0})
    assert cfg.RISK_BINS == before  # restored: later calls to risk_of see the defaults again


def test_thresholds_come_from_the_configuration_file(tmp_path):
    path = tmp_path / "cfg.yaml"
    path.write_text("weather:\n  risk_bins:\n    moderate_from: 2\n    high_from: 6\n")
    assert cfg.risk_bins_from_config(path) == {"moderate_from": 2.0, "high_from": 6.0}
    path.write_text("weather:\n  risk_bins:\n    high_from: 7\n")  # a missing key keeps its default
    assert cfg.risk_bins_from_config(path) == {"moderate_from": 1.0, "high_from": 7.0}
    path.write_text("grid: {}\n")  # no weather section at all
    assert cfg.risk_bins_from_config(path) == cfg.DEFAULT_RISK_BINS


@pytest.mark.parametrize("bins", [{"moderate_from": 4.0, "high_from": 1.0}, {"moderate_from": 0, "high_from": 1},
                                  {"moderate_from": "x", "high_from": 4}, {"high_from": 4}])
def test_bad_thresholds_are_rejected(bins):
    with pytest.raises(ValueError, match="risk_bins"):
        cfg.check_risk_bins(bins)


def test_a_configuration_file_that_was_asked_for_must_exist(tmp_path):
    with pytest.raises(FileNotFoundError, match="not found"):
        cfg.risk_bins_from_config(tmp_path / "nope.yaml")
