"""POI ingestion: data/raw/features/*.geojson -> PoiData (layer-ingestion.md section 4)."""
from __future__ import annotations

import hashlib
import json
import logging

from shapely.geometry import box, mapping, shape

from app.layers.contracts import GridSpec, LayerDataError, PoiData, PoiFeature, PoiKind
from app.layers.poi.normalize import CLIP_TO_AOI, DATASETS, kind_of, normalize_feature, poi_id
from app.layers.validate import validate_poi

log = logging.getLogger(__name__)
FIX = "Run `python scripts/download_data.py --only pois`."


def ingest_poi(settings, grid: GridSpec | None = None) -> PoiData:
    """Reads every known dataset, normalises longitudes to -180..180, clips context polygons to the AOI.
    Unknown files are skipped with a warning. `grid` is accepted for the common ingest signature."""
    folder = settings.raw_dir / "features"
    files = sorted(folder.glob("*.geojson")) if folder.is_dir() else []
    if not files:
        raise LayerDataError("poi", f"No point-of-interest files found in {folder}. {FIX}")
    w, s, e, n = settings.aoi
    aoi_box = box(w, s, e, n)
    features: list[PoiFeature] = []
    used: list[str] = []
    for f in files:
        if f.stem not in DATASETS:
            log.warning("Skipping unknown POI dataset %s", f.name)
            continue
        raw_bytes = f.read_bytes()
        used.append(f"features/{f.name}:{hashlib.sha256(raw_bytes).hexdigest()}")
        for i, raw in enumerate(json.loads(raw_bytes).get("features", [])):
            feat = normalize_feature(f.stem, i, raw)
            geometry = feat["geometry"]
            if not geometry:
                continue
            if f.stem in CLIP_TO_AOI:
                clipped = shape(geometry).intersection(aoi_box)
                if clipped.is_empty:
                    continue
                geometry = json.loads(json.dumps(mapping(clipped)))  # tuples -> lists
            p = feat["properties"]
            service, _, layer_id = f.stem.rpartition("__")
            features.append(PoiFeature(
                id=poi_id(f.stem, i, raw.get("properties") or {}),
                kind=PoiKind(kind_of(f.stem, raw.get("properties") or {})),
                name=p["name"] or None, geometry=geometry, source=f"{service}/{layer_id}",
                properties={"category": p["category"], "description": p["description"],
                            "source_title": p["source"], "raw": p["raw"]}))
    data = PoiData(features=tuple(features), source_files=tuple(used))
    validate_poi(data)
    return data
