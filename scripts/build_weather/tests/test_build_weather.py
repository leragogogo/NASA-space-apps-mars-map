"""build_weather.py must reproduce the files made by the skill's own scripts 06 + 07 exactly.

Run from the repo root:  pytest scripts/build_weather/tests
Skips when the downloaded MDAD file or the reference copy of the skill output is missing.
"""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "build_weather.py"
REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "data/raw/mdad/MDAD_original"
REF = REPO / "data/derived/weather_skill_reference"

pytestmark = pytest.mark.skipif(not SRC.is_file() or not REF.is_dir(),
                                reason="needs data/raw/mdad and data/derived/weather_skill_reference")


def load_script():
    spec = importlib.util.spec_from_file_location("build_weather", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_default_paths_point_at_repo_data():
    mod = load_script()
    assert mod.DEFAULT_SRC == REPO / "data/raw/mdad/MDAD_original"
    assert mod.DEFAULT_OUT == REPO / "data/derived/weather"


def test_matches_skill_output(tmp_path):
    info = load_script().build(SRC, tmp_path)
    assert info == {"cells": 6400, "aoi_frames": 4}
    for name in ("context_weather_frames.geojson", "aoi_weather_frames.json"):
        assert json.loads((tmp_path / name).read_text()) == json.loads((REF / name).read_text()), name
