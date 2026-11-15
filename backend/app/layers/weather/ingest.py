"""Weather ingestion: context_weather_frames.geojson (1 deg cells x 4 seasons) -> WeatherData on the grid.

Confidence and `message` travel with the data (data-sufficiency rule); the arrays only hold the display
risk and confidence class per grid cell. Season never enters edge weights.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

from app.layers.contracts import (SEASONS, Confidence, GridSpec, LayerDataError, RiskLevel, WeatherData,
                                  WeatherFrame)
from app.layers.validate import validate_weather

FIX = "Run `python scripts/download_data.py --only weather`."
RISK = {"Low": RiskLevel.LOW, "Moderate": RiskLevel.MODERATE, "High": RiskLevel.HIGH}
CONFIDENCE = {"reliable": Confidence.RELIABLE, "approximate": Confidence.APPROXIMATE,
              "insufficient_data": Confidence.INSUFFICIENT_DATA}


def display_risk(p: dict) -> str | None:
    """Skill rule: typical-year risk if set, else risk, else the neighbour estimate. Null counts as absent."""
    if p.get("typical_year_risk"):
        return p["typical_year_risk"]
    if p.get("risk"):
        return p["risk"]
    return (p.get("neighbour_estimate") or {}).get("risk")


def weather_file(settings):
    return settings.raw_dir / "weather" / "context_weather_frames.geojson"


def _bounds(geometry: dict) -> tuple[float, float, float, float]:
    ring = np.asarray(geometry["coordinates"][0], dtype=float)
    return (round(float(ring[:, 0].min()), 6), round(float(ring[:, 1].min()), 6),
            round(float(ring[:, 0].max()), 6), round(float(ring[:, 1].max()), 6))


def ingest_weather(settings, grid: GridSpec) -> WeatherData:
    path = weather_file(settings)
    if not path.is_file():
        raise LayerDataError("weather", f"Weather file not found: {path}. {FIX}")
    raw_bytes = path.read_bytes()
    try:
        doc = json.loads(raw_bytes)
        features = doc["features"]
    except (ValueError, KeyError, TypeError) as ex:
        raise LayerDataError("weather", f"Weather file unreadable: {ex}. {FIX}") from ex

    cells: dict[tuple, dict[str, dict]] = {}  # bounds -> season name -> frame properties (insertion ordered)
    for f in features:
        season = f["properties"].get("season")
        if season in SEASONS:
            cells.setdefault(_bounds(f["geometry"]), {})[season] = dict(f["properties"])

    nr, nc = grid.shape
    risk = np.full((len(SEASONS), nr, nc), int(RiskLevel.NONE), np.int8)
    conf = np.full((len(SEASONS), nr, nc), int(Confidence.INSUFFICIENT_DATA), np.int8)
    frame_idx = np.full((nr, nc), -1, np.int32)
    lon_c, lat_c = grid.lon_centers(), grid.lat_centers()
    frames = []
    for idx, (bounds, by_season) in enumerate(cells.items()):
        w, s, e, n = bounds
        frames.append(WeatherFrame(idx, w, s, e, n, by_season))
        rows = np.flatnonzero((lat_c >= s) & (lat_c < n))
        cols = np.flatnonzero((lon_c >= w) & (lon_c < e))
        if rows.size == 0 or cols.size == 0:
            continue  # cell outside the routing grid: still served by the layer endpoint
        window = np.ix_(rows, cols)
        frame_idx[window] = idx
        for k, season in enumerate(SEASONS):
            props = by_season.get(season)
            if props is None:
                continue
            risk[(k, *window)] = int(RISK.get(display_risk(props), RiskLevel.NONE))
            conf[(k, *window)] = int(CONFIDENCE.get(props.get("confidence"), Confidence.INSUFFICIENT_DATA))
    data = WeatherData(grid=grid, seasons=SEASONS, risk=risk, confidence=conf, frame_idx=frame_idx,
                       frames=tuple(frames), caveat=str(doc.get("caveat", "")),
                       source_files=(f"weather/{path.name}:{hashlib.sha256(raw_bytes).hexdigest()}",))
    validate_weather(data)
    return data
