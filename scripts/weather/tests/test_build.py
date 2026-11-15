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
