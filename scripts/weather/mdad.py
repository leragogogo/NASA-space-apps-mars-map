"""Load the Mars Dust Activity Database (MDAD, Battalio & Wang 2021) and approximate storm
footprints.

Each row = one dust storm on one sol: centroid, area, min/max latitude. No outlines, so a storm
is approximated by an ellipse centred on the centroid: its N-S semi-axis comes from the min/max
latitude and its E-W semi-axis is solved so the ellipse area equals the reported area. A point is
"hit" on a sol if it lies inside the ellipse.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from weather.config import KM_PER_DEG, SEASONS

_COLUMNS = {"Mars Year": "my", "Mission subphase": "subphase", "Sol": "sol", "Ls": "ls",
            "Centroid longitude": "lon", "Centroid latitude": "lat", "Area (square km)": "area_km2",
            "Member ID": "member", "Sequence ID": "sequence", "Maximum latitude": "lat_max",
            "Minimum latitude": "lat_min", "Confidence interval": "conf", "Missing data": "missing"}


def season_of(ls: float) -> str:
    for lo, hi, name in SEASONS:
        if lo <= ls < hi:
            return name
    return SEASONS[-1][2]


def load_mdad(path: str | Path) -> pd.DataFrame:
    """Read MDAD_original and add: storm_id, season, ellipse semi-axes (semi_lat_deg, semi_lon_deg)
    and lat_c (the latitude-span centre used as the ellipse centre)."""
    d = pd.read_csv(path)
    d.columns = [c.strip() for c in d.columns]
    for c in d.columns:  # text columns are space-padded in the source
        if d[c].dtype == object or str(d[c].dtype) == "str":
            d[c] = d[c].astype(str).str.strip()
    d = d.rename(columns=_COLUMNS)
    missing = set(_COLUMNS.values()) - set(d.columns)
    if missing:
        raise ValueError(f"MDAD file is missing columns: {sorted(missing)}")
    d["storm_id"] = d.subphase + "_" + d.member  # member ids restart per subphase
    d["season"] = d.ls.apply(season_of)
    b_km = np.maximum((d.lat_max - d.lat_min) / 2 * KM_PER_DEG, 1.0)
    a_km = d.area_km2 / (math.pi * b_km)
    d["semi_lat_deg"] = b_km / KM_PER_DEG
    d["semi_lon_deg"] = a_km / (KM_PER_DEG * np.maximum(np.cos(np.radians(d.lat)), 0.05))
    d["lat_c"] = (d.lat_max + d.lat_min) / 2
    return d


def inside(d: pd.DataFrame, lon: float, lat: float) -> pd.Series:
    """Boolean per storm-sol: is (lon, lat) inside its ellipse (longitude wraps at 180)."""
    dlon = (lon - d.lon + 180) % 360 - 180
    return (dlon / d.semi_lon_deg) ** 2 + ((lat - d.lat_c) / d.semi_lat_deg) ** 2 <= 1


def hits_box(d: pd.DataFrame, box, step: float = 0.25) -> pd.DataFrame:
    """Storm-sols whose ellipse covers any sample point inside box (west, south, east, north)."""
    w, s, e, n = box
    pts = [(x, y) for x in np.arange(w, e + 1e-9, step) for y in np.arange(s, n + 1e-9, step)]
    mask = np.zeros(len(d), bool)
    frac = np.zeros(len(d))
    for x, y in pts:
        m = inside(d, x, y).to_numpy()
        mask |= m
        frac += m
    out = d[mask].copy()
    out["aoi_cover_frac"] = (frac[mask] / len(pts)).round(2)
    return out
