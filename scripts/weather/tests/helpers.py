"""Tiny synthetic storm tables for the weather tests (no real data needed)."""
from __future__ import annotations

import math

import pandas as pd

from weather.config import KM_PER_DEG
from weather.mdad import season_of

RAW_COLUMNS = ["Mars Year", "Mission subphase", "Sol", "Ls", "Centroid longitude", "Centroid latitude",
               "Area (square km)", "Member ID", "Sequence ID", "Maximum latitude", "Minimum latitude",
               "Confidence interval", "Missing data"]


def raw_row(my=28, sub="B01", sol=1, ls=100.0, lon=-70.0, lat=-12.0, area=2.0e6, member="B01_001",
            lat_max=-2.0, lat_min=-22.0, missing="no"):
    return [my, sub, sol, ls, lon, lat, area, member, "", lat_max, lat_min, 75, missing]


def write_mdad(path, rows):
    pd.DataFrame(rows, columns=RAW_COLUMNS).to_csv(path, index=False)


def storms(rows):
    """Processed-style frame (what load_mdad returns) from (my, ls, lon, lat, storm_id, missing) tuples,
    with a large circular-ish footprint (semi axes 10 deg) so every storm covers its surroundings."""
    recs = []
    for my, ls, lon, lat, sid, missing in rows:
        recs.append(dict(my=my, ls=ls, lon=lon, lat=lat, lat_c=lat, semi_lat_deg=10.0, semi_lon_deg=10.0,
                         storm_id=sid, season=season_of(ls), missing=missing, sol=1, area_km2=1e6))
    return pd.DataFrame(recs)


def ellipse_area_km2(semi_lat_deg, semi_lon_deg, lat):
    a = semi_lon_deg * KM_PER_DEG * math.cos(math.radians(lat))
    b = semi_lat_deg * KM_PER_DEG
    return math.pi * a * b
