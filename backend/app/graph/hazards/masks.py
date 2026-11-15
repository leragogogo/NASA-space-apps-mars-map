"""Hazard masks: which grid cells a POI hazard covers (edge-cost-model.md section 4a).

Dune fields (Polygon / MultiPolygon) cover the cells whose centre lies inside them; point-only dune features
have no area and are ignored. RSL sites cover every cell whose centre lies within `rsl_buffer_m` of the site's
representative point. Computed from GraphInputs.poi, never from data/raw/.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import shapely
from shapely.geometry import shape

from app.layers.contracts import GridSpec, PoiData, PoiKind

_AREAS = ("Polygon", "MultiPolygon")


@dataclass(frozen=True, eq=False)
class HazardMasks:
    dune: np.ndarray  # bool (nrows, ncols)
    rsl: np.ndarray  # bool (nrows, ncols)

    @classmethod
    def empty(cls, grid: GridSpec) -> "HazardMasks":
        return cls(dune=np.zeros(grid.shape, dtype=bool), rsl=np.zeros(grid.shape, dtype=bool))


def _area_mask(grid: GridSpec, geometries: Iterable[dict]) -> np.ndarray:
    lon, lat = grid.node_lonlat()
    mask = np.zeros(grid.n_nodes, dtype=bool)
    for geometry in geometries:
        mask |= shapely.contains_xy(shape(geometry), lon, lat)
    return mask.reshape(grid.shape)


def _buffer_mask(grid: GridSpec, points: Iterable[tuple[float, float]], radius_m: float) -> np.ndarray:
    lon, lat = grid.node_lonlat()
    m_per_deg = np.radians(1.0) * grid.radius_m
    mask = np.zeros(grid.n_nodes, dtype=bool)
    for p_lon, p_lat in points:
        dx = (lon - p_lon) * np.cos(np.radians(p_lat)) * m_per_deg
        dy = (lat - p_lat) * m_per_deg
        mask |= dx * dx + dy * dy <= radius_m * radius_m
    return mask.reshape(grid.shape)


def hazard_masks(grid: GridSpec, poi: PoiData, rsl_buffer_m: float) -> HazardMasks:
    if rsl_buffer_m < 0:
        raise ValueError(f"rsl_buffer_m must be >= 0, got {rsl_buffer_m}")
    dunes = [f.geometry for f in poi.features if f.kind == PoiKind.DUNE_FIELD and f.geometry.get("type") in _AREAS]
    rsl = [f.lonlat() for f in poi.features if f.kind == PoiKind.RSL]
    return HazardMasks(dune=_area_mask(grid, dunes), rsl=_buffer_mask(grid, rsl, rsl_buffer_m))
