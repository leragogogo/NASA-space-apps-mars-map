"""Layer 2: relief. Elevation grid -> slope -> slope classes, walkability overlay and point lookup."""
from __future__ import annotations

from dataclasses import asdict

import numpy as np
import tifffile

from app.layers.base import LayerUnavailable
from app.layers.relief.render import walkability_png
from app.layers.relief.slope import classify, pixel_size_m, slope_degrees
from app.tiles.store import TileStore

NODATA_BELOW = -32000  # Trek exports noData as -32767
CAVEATS = [
    "The 200 m elevation grid underestimates local slope: all slope values are approximate, and short steep "
    "features such as cliffs and crater rims are smoothed out.",
    "Slope class thresholds are provisional and not yet confirmed for walking or vehicle limits.",
]


class ReliefGetter:
    name = "relief"

    def __init__(self, settings, store: TileStore):
        path = settings.raw_dir / "dem" / "dem_blend200m_aoi.tif"
        if not path.is_file():
            raise LayerUnavailable(f"Elevation grid not found: {path}", "python scripts/download_data.py --only dem")
        try:
            elev = tifffile.imread(path).astype("float64")
        except Exception as ex:  # noqa: BLE001
            raise LayerUnavailable(f"Elevation grid unreadable: {ex}",
                                   "python scripts/download_data.py --only dem --force") from ex
        elev[elev <= NODATA_BELOW] = np.nan
        self._aoi = settings.aoi
        self._classes = settings.slope_classes
        self._store = store
        self._elev = elev
        self._slope = slope_degrees(elev, self._aoi)
        self._class = classify(self._slope, self._classes)
        self._png = walkability_png(self._class, self._classes)
        dx, dy = pixel_size_m(elev.shape, self._aoi)
        self._resolution_m = int(round((dx + dy) / 2))

    def grid(self) -> dict:
        """The arrays the map overlay uses; the master graph must use these too."""
        return {"elevation_m": self._elev, "slope_deg": self._slope, "slope_class": self._class, "aoi": self._aoi}

    def walkability_png(self) -> bytes:
        return self._png

    def _index(self, lon: float, lat: float) -> tuple[int, int] | None:
        w, s, e, n = self._aoi
        if not (w <= lon <= e and s <= lat <= n):
            return None
        ny, nx = self._elev.shape
        col = min(int((lon - w) / (e - w) * nx), nx - 1)
        row = min(int((n - lat) / (n - s) * ny), ny - 1)
        return row, col

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
            "caveats": CAVEATS,
        }

    def sample(self, lon: float, lat: float, season: str | None = None) -> dict | None:
        return self.point(lon, lat)
