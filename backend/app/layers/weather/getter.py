"""Layer 4: seasonal dust-storm risk on the 1 deg Valles Marineris grid (built by scripts/build_weather/build_weather.py)."""
from __future__ import annotations

import json
import math

from app.layers.base import LayerUnavailable

SEASONS = {
    "autumn": "S. Autumn (Ls 0-90)",
    "winter": "S. Winter (Ls 90-180)",
    "spring": "S. Spring (Ls 180-270, perihelion)",
    "summer": "S. Summer (Ls 270-360)",
}
STYLE = {"reliable": "solid", "approximate": "hatched", "insufficient_data": "grey"}


def display_risk(p: dict) -> str | None:
    """Skill rule: typical-year risk if set, else risk, else the neighbour estimate. Null counts as absent."""
    if p.get("typical_year_risk"):
        return p["typical_year_risk"]
    if p.get("risk"):
        return p["risk"]
    return (p.get("neighbour_estimate") or {}).get("risk")


def display_style(p: dict) -> str:
    return STYLE.get(p.get("confidence"), "grey")


def _cell_key(lon: float, lat: float) -> tuple[float, float]:
    """Centre of the 1 deg cell containing the point."""
    return round(math.floor(lon) + 0.5, 3), round(math.floor(lat) + 0.5, 3)


class WeatherGetter:
    name = "weather"

    def __init__(self, settings):
        folder = settings.derived_dir / "weather"
        grid_file, aoi_file = folder / "context_weather_frames.geojson", folder / "aoi_weather_frames.json"
        missing = [f.name for f in (grid_file, aoi_file) if not f.is_file()]
        if missing:
            raise LayerUnavailable(f"Weather files not found in {folder}: {', '.join(missing)}",
                                   "python scripts/build_weather/build_weather.py")
        grid = json.loads(grid_file.read_text())
        aoi = json.loads(aoi_file.read_text())
        key_of = {v: k for k, v in SEASONS.items()}
        self._caveat = grid.get("caveat", "")
        self._legend = dict(settings.risk_colors)
        self._cells = {k: [] for k in SEASONS}
        self._by_cell: dict[tuple[float, float], dict] = {}
        for f in grid["features"]:
            key = key_of.get(f["properties"].get("season"))
            if key is None:
                continue
            p = {**f["properties"]}
            p["display_risk"] = display_risk(p)
            p["display_style"] = display_style(p)
            self._cells[key].append({"type": "Feature", "geometry": f["geometry"], "properties": p})
            ring = f["geometry"]["coordinates"][0][:4]
            centre = (round(sum(x for x, _ in ring) / 4, 3), round(sum(y for _, y in ring) / 4, 3))
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
