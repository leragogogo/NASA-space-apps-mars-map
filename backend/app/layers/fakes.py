"""Synthetic layer data for any GridSpec, so graph / routing / API / frontend work can proceed
without the real ingestion modules. Every fake passes the validators in validate.py."""
from __future__ import annotations

import math

import numpy as np

from app.layers.contracts import (Confidence, GraphInputs, GridSpec, PoiData, PoiFeature,
                                  PoiKind, ReliefData, RiskLevel, SEASONS, WeatherData, WeatherFrame)
from app.layers.relief.slope import slope_deg

RELIEF_KINDS = ("flat", "ramp", "bowl", "ridge", "cliff")
_MESSAGES = {
    Confidence.RELIABLE: "{risk} dust-storm risk (synthetic fixture).",
    Confidence.APPROXIMATE: "APPROXIMATE: not enough data to reliably calculate the risk (synthetic fixture).",
    Confidence.INSUFFICIENT_DATA: "NOT ENOUGH DATA: risk cannot be reliably calculated (synthetic fixture).",
}


# A small patch inside the AOI (~18 km wide), so default fake cells are ~600 m and elevations stay plausible.
FAKE_BBOX = (-70.9, -12.0, -70.6, -11.7)


def fake_grid(nrows: int = 24, ncols: int = 30, bbox=FAKE_BBOX) -> GridSpec:
    return GridSpec(*bbox, ncols=ncols, nrows=nrows)


def fake_relief(grid: GridSpec, kind: str = "flat", slope_deg_: float = 10.0,
                height_m: float = 1000.0, base_m: float = -2000.0) -> ReliefData:
    """kind: flat | ramp (rises to the east at slope_deg_) | bowl | ridge | cliff (step of height_m)."""
    if kind not in RELIEF_KINDS:
        raise ValueError(f"kind must be one of {RELIEF_KINDS}")
    nr, nc = grid.shape
    dx_m, _ = grid.metric_spacing()
    u = np.linspace(-1, 1, nc)[None, :] * np.ones((nr, 1))
    v = np.linspace(-1, 1, nr)[:, None] * np.ones((1, nc))
    if kind == "flat":
        elev = np.zeros(grid.shape)
    elif kind == "ramp":
        elev = np.arange(nc)[None, :] * dx_m[nr // 2] * math.tan(math.radians(slope_deg_)) * np.ones((nr, 1))
    elif kind == "bowl":
        elev = height_m * (u ** 2 + v ** 2) - height_m
    elif kind == "ridge":
        elev = height_m * np.exp(-(u / 0.2) ** 2)
    else:  # cliff
        elev = np.where(np.arange(nc)[None, :] >= nc // 2, height_m, 0.0) * np.ones((nr, 1))
    elev = (elev + base_m).astype(np.float32)
    return ReliefData(grid=grid, elev_m=elev, valid=np.ones(grid.shape, dtype=bool),
                      slope_deg=slope_deg(elev, grid), roughness_m=None, source_files=())


def fake_poi(grid: GridSpec, n: int = 5, seed: int = 0) -> PoiData:
    rng = np.random.default_rng(seed)
    kinds = [PoiKind.RSL, PoiKind.MINERAL_SULFATE, PoiKind.DUNE_FIELD, PoiKind.EXPLORATION_ROI]
    feats = []
    for i in range(n):
        lon = float(rng.uniform(grid.west, grid.east))
        lat = float(rng.uniform(grid.south, grid.north))
        feats.append(PoiFeature(id=f"fake:0:{i}", kind=kinds[i % len(kinds)],
                                geometry={"type": "Point", "coordinates": [lon, lat]},
                                source="fake/0", name=f"fake poi {i}"))
    return PoiData(features=tuple(feats))


def fake_weather(grid: GridSpec, risk: RiskLevel = RiskLevel.LOW,
                 confidence: Confidence = Confidence.RELIABLE,
                 by_season: dict[str, tuple[RiskLevel, Confidence]] | None = None) -> WeatherData:
    """Same risk/confidence everywhere, optionally overridden per season: {season: (risk, conf)}."""
    by_season = by_season or {}
    values = [by_season.get(s, (risk, confidence)) for s in SEASONS]
    risk_arr = np.stack([np.full(grid.shape, int(r), dtype=np.int8) for r, _ in values])
    conf_arr = np.stack([np.full(grid.shape, int(c), dtype=np.int8) for _, c in values])
    lon0, lat0 = math.floor(grid.west), math.floor(grid.south)
    n_lon = math.ceil(grid.east) - lon0
    n_lat = math.ceil(grid.north) - lat0
    frames, index = [], {}
    for j in range(n_lat):
        for i in range(n_lon):
            idx = len(frames)
            index[(i, j)] = idx
            props = {s: {"season": s, "display_risk": r.name.title(), "confidence": c.name.lower(),
                         "message": _MESSAGES[c].format(risk=r.name.title())}
                     for s, (r, c) in zip(SEASONS, values)}
            frames.append(WeatherFrame(idx, lon0 + i, lat0 + j, lon0 + i + 1, lat0 + j + 1, props))
    lon, lat = grid.node_lonlat()
    fi = np.array([index[(int(math.floor(x)) - lon0, int(math.floor(y)) - lat0)]
                   for x, y in zip(lon, lat)], dtype=np.int32).reshape(grid.shape)
    return WeatherData(grid=grid, seasons=SEASONS, risk=risk_arr, confidence=conf_arr, frame_idx=fi,
                       frames=tuple(frames), caveat="Synthetic fixture: not real storm statistics.")


def fake_inputs(grid: GridSpec | None = None, relief_kind: str = "ramp") -> GraphInputs:
    grid = grid or fake_grid()
    return GraphInputs(grid=grid, relief=fake_relief(grid, relief_kind),
                       weather=fake_weather(grid), poi=fake_poi(grid))
