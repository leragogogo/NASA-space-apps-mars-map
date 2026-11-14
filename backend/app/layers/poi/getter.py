"""Layer 3: points of interest. All Trek vector files in one normalised FeatureCollection."""
from __future__ import annotations

import json
import logging
import math

import numpy as np
import shapely
from shapely.geometry import Point, box, mapping, shape

from app.layers.base import LayerUnavailable
from app.layers.poi.normalize import CATEGORIES, CLIP_TO_AOI, DATASETS, normalize_feature
from app.layers.relief.slope import M_PER_DEG
from app.tiles.store import TileStore

log = logging.getLogger(__name__)


class PoiGetter:
    name = "poi"

    def __init__(self, settings, store: TileStore):
        folder = settings.raw_dir / "features"
        files = sorted(folder.glob("*.geojson")) if folder.is_dir() else []
        if not files:
            raise LayerUnavailable(f"No point-of-interest files found in {folder}",
                                   "python scripts/download_data.py --only pois")
        w, s, e, n = settings.aoi
        aoi_box = box(w, s, e, n)
        features = []
        for f in files:
            if f.stem not in DATASETS:
                log.warning("Skipping unknown POI dataset %s", f.name)
                continue
            for i, raw in enumerate(json.loads(f.read_text()).get("features", [])):
                feat = normalize_feature(f.stem, i, raw)
                if f.stem in CLIP_TO_AOI and feat["geometry"]:
                    clipped = shape(feat["geometry"]).intersection(aoi_box)
                    if clipped.is_empty:
                        continue
                    feat["geometry"] = json.loads(json.dumps(mapping(clipped)))  # tuples -> lists
                features.append(feat)
        self._features = features
        self._store = store
        self._radius_km = settings.poi_sample_radius_km
        # Local flat projection in km (good enough over the ~4 deg demo area) for distance checks.
        self._k = np.array([M_PER_DEG / 1000 * math.cos(math.radians((s + n) / 2)), M_PER_DEG / 1000])
        self._geoms_km = [shapely.transform(shape(f["geometry"]), lambda c: c * self._k) if f["geometry"] else None
                          for f in features]

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
