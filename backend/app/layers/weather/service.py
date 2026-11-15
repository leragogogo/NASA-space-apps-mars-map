"""Layer 4 service: client-facing GeoJSON of WeatherData, one season at a time (1 deg Valles Marineris grid)."""
from __future__ import annotations

import json
import math

from app.layers.base import LayerUnavailable
from app.layers.contracts import SEASONS as SEASON_NAMES
from app.layers.contracts import WeatherData
from app.layers.weather.ingest import display_risk

SEASONS = {  # API key -> exact season name used in the data
    "autumn": SEASON_NAMES[0],
    "winter": SEASON_NAMES[1],
    "spring": SEASON_NAMES[2],
    "summer": SEASON_NAMES[3],
}
STYLE = {"reliable": "solid", "approximate": "hatched", "insufficient_data": "grey"}


def display_style(p: dict) -> str:
    return STYLE.get(p.get("confidence"), "grey")


def _cell_key(lon: float, lat: float) -> tuple[float, float]:
    """Centre of the 1 deg cell containing the point."""
    return round(math.floor(lon) + 0.5, 3), round(math.floor(lat) + 0.5, 3)


class WeatherGetter:
    name = "weather"

    def __init__(self, settings, data: WeatherData):
        folder = settings.raw_dir / "weather"
        aoi_file = folder / "aoi_weather_frames.json"
        if not aoi_file.is_file():
            raise LayerUnavailable(f"Weather file not found: {aoi_file}", "python scripts/download_data.py --only weather")
        aoi = json.loads(aoi_file.read_text())
        self.data = data
        self._caveat = data.caveat
        self._legend = dict(settings.risk_colors)
        key_of = {v: k for k, v in SEASONS.items()}
        self._cells = {k: [] for k in SEASONS}
        self._by_cell: dict[tuple[float, float], dict] = {}
        for fr in data.frames:
            ring = [[fr.west, fr.south], [fr.east, fr.south], [fr.east, fr.north], [fr.west, fr.north],
                    [fr.west, fr.south]]
            centre = (round((fr.west + fr.east) / 2, 3), round((fr.south + fr.north) / 2, 3))
            for name, props in fr.by_season.items():
                key = key_of[name]
                p = {**props, "display_risk": display_risk(props), "display_style": display_style(props)}
                self._cells[key].append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                                         "properties": p})
                self._by_cell.setdefault(centre, {})[key] = {
                    "risk": p["display_risk"], "confidence": p.get("confidence"), "message": p.get("message")}
        self._aoi = {key_of[fr["season"]]: fr for fr in aoi.get("frames", []) if fr.get("season") in key_of}

    def cells(self, season: str) -> list[dict]:
        return self._cells[season]

    def aoi_frame(self, season: str) -> dict | None:
        return self._aoi.get(season)

    def describe(self, season: str) -> dict:
        return {"type": "FeatureCollection", "layer": self.name, "season": season, "season_name": SEASONS[season],
                "caveat": self._caveat, "legend": self._legend, "aoi_summary": self.aoi_frame(season),
                "features": self._cells[season]}

    def sample(self, lon: float, lat: float, season: str | None = None) -> dict | None:
        """Risk, confidence and message of the cell containing the point, for all four seasons."""
        return self._by_cell.get(_cell_key(lon, lat))
