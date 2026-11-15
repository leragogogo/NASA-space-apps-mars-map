"""Validators every layer ingestion must pass (and every fake does). They collect all problems
and raise one LayerDataError, so a failure lists everything that is wrong at once."""
from __future__ import annotations

import numpy as np

from app.layers.contracts import (SEASONS, Confidence, GraphInputs, GridSpec, LayerDataError,
                                  PoiData, ReliefData, RiskLevel, WeatherData)


def _raise(layer: str, problems: list[str]) -> None:
    if problems:
        raise LayerDataError(layer, "; ".join(problems))


def validate_relief(d: ReliefData) -> None:
    p: list[str] = []
    shape = d.grid.shape
    for name in ("elev_m", "valid", "slope_deg"):
        arr = getattr(d, name)
        if arr.shape != shape:
            p.append(f"{name}: shape {arr.shape} != grid {shape}")
    if d.roughness_m is not None and d.roughness_m.shape != shape:
        p.append(f"roughness_m: shape {d.roughness_m.shape} != grid {shape}")
    if p:
        _raise("relief", p)
    if d.elev_m.dtype != np.float32 or d.slope_deg.dtype != np.float32:
        p.append("elev_m and slope_deg must be float32")
    if d.valid.dtype != np.bool_:
        p.append("valid must be bool")
    if np.isinf(d.elev_m).any() or np.isinf(d.slope_deg).any():
        p.append("inf found in elev_m or slope_deg")
    if (np.isnan(d.elev_m) != ~d.valid).any():
        p.append("elev_m must be NaN exactly where valid is False")
    if not np.isfinite(d.slope_deg[d.valid]).all():
        p.append("slope_deg must be finite wherever valid")
    finite = d.slope_deg[np.isfinite(d.slope_deg)]
    if finite.size and (finite.min() < 0 or finite.max() > 90):
        p.append("slope_deg outside 0..90")
    if d.valid.any() and not (-12000 <= np.nanmin(d.elev_m) and np.nanmax(d.elev_m) <= 30000):
        p.append("elev_m outside the plausible Mars range (-12000..30000 m)")
    _raise("relief", p)


def validate_poi(d: PoiData, grid: GridSpec | None = None) -> None:
    p: list[str] = []
    ids = [f.id for f in d.features]
    if len(set(ids)) != len(ids):
        p.append("duplicate feature ids")
    for f in d.features:
        try:
            lon, lat = f.lonlat()
        except (ValueError, TypeError, IndexError, KeyError) as e:
            p.append(f"{f.id}: bad geometry ({e})")
            continue
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            p.append(f"{f.id}: lon/lat out of range (normalise 0-360 longitudes)")
        elif grid is not None and f.geometry.get("type") == "Point" and not grid.contains(lon, lat):
            p.append(f"{f.id}: point outside the grid")
    for name, dtype in (("nearest_poi_dist_m", np.float32), ("nearest_poi_id", np.int32)):
        arr = getattr(d, name)
        if arr is not None:
            if arr.dtype != dtype:
                p.append(f"{name}: dtype {arr.dtype} != {np.dtype(dtype)}")
            if grid is not None and arr.shape != grid.shape:
                p.append(f"{name}: shape {arr.shape} != grid {grid.shape}")
    if d.nearest_poi_id is not None and d.nearest_poi_id.size:
        if d.nearest_poi_id.max() >= len(d.features) or d.nearest_poi_id.min() < -1:
            p.append("nearest_poi_id outside -1..len(features)-1")
    _raise("poi", p)


def validate_weather(d: WeatherData) -> None:
    p: list[str] = []
    if tuple(d.seasons) != SEASONS:
        p.append(f"seasons must be exactly {SEASONS}")
    shape3 = (len(SEASONS), *d.grid.shape)
    for name in ("risk", "confidence"):
        arr = getattr(d, name)
        if arr.shape != shape3:
            p.append(f"{name}: shape {arr.shape} != {shape3}")
        if arr.dtype != np.int8:
            p.append(f"{name}: dtype must be int8")
    if d.frame_idx.shape != d.grid.shape:
        p.append(f"frame_idx: shape {d.frame_idx.shape} != grid {d.grid.shape}")
    if p:
        _raise("weather", p)
    if not np.isin(d.risk, [int(r) for r in RiskLevel]).all():
        p.append("risk values must be in {-1, 0, 1, 2}")
    if not np.isin(d.confidence, [int(c) for c in Confidence]).all():
        p.append("confidence values must be in {0, 1, 2}")
    if d.frame_idx.size and (d.frame_idx.min() < -1 or d.frame_idx.max() >= len(d.frames)):
        p.append("frame_idx outside -1..len(frames)-1")
    if not d.caveat.strip():
        p.append("caveat must not be empty (the UI must show it)")
    for f in d.frames:
        for season, props in f.by_season.items():
            if season not in SEASONS:
                p.append(f"frame {f.frame_idx}: unknown season {season!r}")
            if not str(props.get("message", "")).strip():
                p.append(f"frame {f.frame_idx}/{season}: missing message (the UI renders it verbatim)")
    _raise("weather", p)


def validate_inputs(i: GraphInputs) -> None:
    validate_relief(i.relief)
    validate_weather(i.weather)
    validate_poi(i.poi, i.grid)
