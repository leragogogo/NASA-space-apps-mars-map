"""Constants for the weather layer (seasonal dust-storm risk). Ported from the exploration
scripts 06/07 (context/skills/mars-mvp-data/scripts/); thresholds are tuned there and documented
in SKILL.md section 6."""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np

AOI = (-71.8, -13.4, -68.0, -10.0)  # west, south, east, north: East Melas / Coprates
CONTEXT = (-90.0, -30.0, -50.0, 10.0)  # Valles Marineris neighbourhood: the 1 deg grid extent
CELL = 1.0  # deg

R_KM = 3389.5  # Mars mean radius
KM_PER_DEG = 2 * math.pi * R_KM / 360

# Ls quarters. The AOI is at ~12 S, so seasons are named for the SOUTHERN hemisphere.
SEASONS = [(0, 90, "S. Autumn (Ls 0-90)"), (90, 180, "S. Winter (Ls 90-180)"),
           (180, 270, "S. Spring (Ls 180-270, perihelion)"), (270, 360, "S. Summer (Ls 270-360)")]
SEASON_NAMES = [name for *_, name in SEASONS]

# Observation window: MY24 Ls150 -> MY32 Ls171.
FIRST_MY, LAST_MY = 24, 32
FIRST_LS, LAST_LS = 150.0, 171.0

# Thresholds (tune here)
MIN_YEARS_RELIABLE = 6.0  # observed Mars years in the frame-season
MIN_YEARS_ANY = 3.0  # below this the frame itself cannot be used
MIN_STORMS_RELIABLE = 5  # distinct storms; fewer -> wide uncertainty
MAX_SINGLE_YEAR_SHARE = 0.5  # one Mars year contributing >50 % of storm-days -> skewed
MAX_MISSING_SHARE = 0.5  # >50 % of storm records flagged "missing data" in source images
NEIGHBOUR_RADIUS_DEG = 3.0
DEFAULT_RISK_BINS = {"moderate_from": 1.0, "high_from": 4.0}  # storm-days per Mars year
RISK_BINS = [(DEFAULT_RISK_BINS["moderate_from"], "Low"), (DEFAULT_RISK_BINS["high_from"], "Moderate"),
             (np.inf, "High")]  # in use: set from config/mars.yaml by build_weather_layer (see set_risk_bins)
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "mars.yaml"


def check_risk_bins(bins: dict) -> dict:
    """{"moderate_from", "high_from"} as floats; raises ValueError unless 0 < moderate_from < high_from."""
    try:
        moderate, high = float(bins["moderate_from"]), float(bins["high_from"])
    except (KeyError, TypeError, ValueError) as ex:
        raise ValueError(f"risk_bins needs numeric moderate_from and high_from, got {bins!r}") from ex
    if not 0 < moderate < high:
        raise ValueError(f"risk_bins must satisfy 0 < moderate_from < high_from, got {moderate} and {high}")
    return {"moderate_from": moderate, "high_from": high}


def risk_bins_from_config(path: Path | str | None = None) -> dict:
    """The thresholds of config/mars.yaml (`weather.risk_bins`; $MARS_CONFIG or `path` selects another file).
    A missing default file or a missing key means the built-in defaults; a file that was asked for must exist."""
    explicit = path or os.environ.get("MARS_CONFIG")
    file = Path(explicit) if explicit else CONFIG_PATH
    if not file.is_file():
        if explicit:
            raise FileNotFoundError(f"configuration file {file} not found")
        return dict(DEFAULT_RISK_BINS)
    import yaml  # PyYAML: in scripts/requirements.txt

    doc = yaml.safe_load(file.read_text()) or {}
    bins = ((doc.get("weather") or {}).get("risk_bins")) or DEFAULT_RISK_BINS
    return check_risk_bins({**DEFAULT_RISK_BINS, **bins})


def set_risk_bins(bins: dict) -> list:
    """Make `bins` the thresholds used by `risk_of`; returns the previous RISK_BINS so a caller can restore them."""
    global RISK_BINS
    previous, bins = RISK_BINS, check_risk_bins(bins)
    RISK_BINS = [(bins["moderate_from"], "Low"), (bins["high_from"], "Moderate"), (np.inf, "High")]
    return previous

GLOBAL_CAVEAT = ("Source: MDAD, MY24-32 (1999-2015). Dust storms smaller than ~100,000 km² are not reliably "
                 "catalogued, and storm footprints are ellipse approximations (no outlines in the source). "
                 "Values are historical frequencies, not forecasts.")
