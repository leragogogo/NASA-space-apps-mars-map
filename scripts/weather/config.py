"""Constants for the weather layer (seasonal dust-storm risk). Ported from the exploration
scripts 06/07 (context/skills/mars-mvp-data/scripts/); thresholds are tuned there and documented
in SKILL.md section 6."""
from __future__ import annotations

import math

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
RISK_BINS = [(1.0, "Low"), (4.0, "Moderate"), (np.inf, "High")]  # storm-days per Mars year

GLOBAL_CAVEAT = ("Source: MDAD, MY24-32 (1999-2015). Dust storms smaller than ~100,000 km² are not reliably "
                 "catalogued, and storm footprints are ellipse approximations (no outlines in the source). "
                 "Values are historical frequencies, not forecasts.")
