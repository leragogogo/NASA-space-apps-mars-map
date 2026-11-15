"""Layer 3 service: client-facing GeoJSON of PoiData, filtered by category."""
from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import Point, shape

from app.layers.contracts import PoiData, PoiFeature
from app.layers.poi.normalize import CATEGORIES
from app.layers.relief.slope import M_PER_DEG
from app.tiles.store import TileStore


def to_client_feature(f: PoiFeature) -> dict:
    p = f.properties
    return {"type": "Feature", "geometry": dict(f.geometry),
            "properties": {"id": f.id, "kind": f.kind.value, "category": p["category"], "name": f.name,
                           "description": p["description"], "source": p["source_title"], "raw": p["raw"]}}


class PoiGetter:
    name = "poi"

    def __init__(self, settings, store: TileStore, data: PoiData):
        self.data = data
        self._features = [to_client_feature(f) for f in data.features]
        self._store = store
        self._radius_km = settings.poi_sample_radius_km
        s, n = settings.aoi[1], settings.aoi[3]
        # Local flat projection in km (good enough over the ~4 deg demo area) for distance checks.
        self._k = np.array([M_PER_DEG / 1000 * math.cos(math.radians((s + n) / 2)), M_PER_DEG / 1000])
        self._geoms_km = [shapely.transform(shape(f.geometry), lambda c: c * self._k) for f in data.features]

    def features(self, categories: set[str] | None = None) -> list[dict]:
        if not categories:
            return list(self._features)
        return [f for f in self._features if f["properties"]["category"] in categories]

    def describe(self, categories: set[str] | None = None) -> dict:
        counts = {c: 0 for c in CATEGORIES}
        for f in self._features:
            counts[f["properties"]["category"]] += 1
        return {"type": "FeatureCollection", "layer": self.name, "categories": counts,
                "overlays": self._store.available("poi"), "features": self.features(categories)}

    def sample(self, lon: float, lat: float, season: str | None = None) -> list[dict]:
        """Features within poi_sample_radius_km of the point, nearest first."""
        p = Point(lon * self._k[0], lat * self._k[1])
        near = []
        for f, g in zip(self._features, self._geoms_km):
            if g is None:
                continue
            d = g.distance(p)
            if d <= self._radius_km:
                pr = f["properties"]
                near.append({"id": pr["id"], "category": pr["category"], "name": pr["name"],
                             "distance_km": round(d, 2)})
        return sorted(near, key=lambda x: x["distance_km"])
