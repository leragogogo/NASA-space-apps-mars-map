"""Layer 2 service: client-facing format of ReliefData (slope classes, walkability overlay, point lookup)."""
from __future__ import annotations

from dataclasses import asdict

import numpy as np

from app.layers.contracts import ReliefData
from app.layers.relief.render import walkability_png
from app.layers.relief.slope import classify, pixel_size_m
from app.tiles.store import TileStore

def caveats(resolution_m: int) -> list[str]:
    return [
        f"The {resolution_m} m elevation grid underestimates local slope: all slope values are approximate, and "
        "short steep features such as cliffs and crater rims are smoothed out.",
        "Slope class thresholds are provisional and not yet confirmed for walking or vehicle limits.",
    ]


class ReliefGetter:
    name = "relief"

    def __init__(self, settings, store: TileStore, data: ReliefData):
        self.data = data
        self._aoi = settings.aoi
        self._classes = settings.slope_classes
        self._store = store
        self._elev = data.elev_m
        self._slope = data.slope_deg  # the same array the graph builder reads
        self._class = classify(self._slope, self._classes)
        self._png = walkability_png(self._class, self._classes)
        dx, dy = pixel_size_m(self._elev.shape, self._aoi)
        self._resolution_m = int(round((dx + dy) / 2))

    def grid(self) -> dict:
        """The arrays the map overlay uses; the master graph must use these too."""
        return {"elevation_m": self._elev, "slope_deg": self._slope, "slope_class": self._class, "aoi": self._aoi}

    def walkability_png(self) -> bytes:
        return self._png

    def _index(self, lon: float, lat: float) -> tuple[int, int] | None:
        row, col = self.data.grid.lonlat_to_rc(lon, lat)
        return None if int(row) < 0 else (int(row), int(col))

    def point(self, lon: float, lat: float) -> dict | None:
        idx = self._index(lon, lat)
        if idx is None:
            return None
        k = int(self._class[idx])
        base = {"lon": lon, "lat": lat, "approximate": True}
        if k < 0:
            return {**base, "elevation_m": None, "slope_deg": None, "slope_class": None,
                    "walkable": False, "vehicle": False}
        c = self._classes[k]
        return {**base, "elevation_m": round(float(self._elev[idx]), 1), "slope_deg": round(float(self._slope[idx]), 2),
                "slope_class": c.id, "walkable": c.walkable, "vehicle": c.vehicle}

    def describe(self) -> dict:
        w, s, e, n = self._aoi
        bounds = [[s, w], [n, e]]
        return {
            "layer": self.name,
            "bounds": bounds,
            "resolution_m": self._resolution_m,
            "elevation_range_m": [int(round(float(np.nanmin(self._elev)))), int(round(float(np.nanmax(self._elev))))],
            "slope_classes": [asdict(c) for c in self._classes],
            "overlay": {"url": "/api/get-layer-two/walkability.png", "bounds": bounds},
            "hillshade_sources": self._store.available("relief"),
            "caveats": caveats(self._resolution_m),
        }

    def sample(self, lon: float, lat: float, season: str | None = None) -> dict | None:
        return self.point(lon, lat)
