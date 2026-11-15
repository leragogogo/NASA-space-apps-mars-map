"""Terrain and hazard terms shared by both profile formulas (edge-cost-model.md section 4a).

They change only `cost` and passability, never the resources (time, O2, energy): there is no calibrated data
for how roughness or sand change consumption.
"""
from __future__ import annotations

import numpy as np

from app.core.profiles import EdgeGeometry

ROUGHNESS_CAP = 3.0  # roughness beyond 3x the reference adds no further cost


def effective_slope_rad(geom: EdgeGeometry) -> np.ndarray:
    """Steepness for the slope margin and the hard limit: the larger of the travel gradient and the map slope of
    the end cells, so walking along a steep hillside counts as steep. Without map slope: the travel gradient."""
    theta = np.abs(geom.theta_rad)
    if geom.terrain_slope_deg is None:
        return theta
    return np.maximum(theta, np.radians(geom.terrain_slope_deg))


def roughness_factor(geom: EdgeGeometry, weight: float, ref_m: float) -> np.ndarray:
    if geom.roughness_m is None or weight == 0:
        return np.ones(len(geom))
    r = np.nan_to_num(geom.roughness_m, nan=0.0)
    return 1.0 + weight * np.minimum(r / ref_m, ROUGHNESS_CAP)


def dune_factor(geom: EdgeGeometry, penalty: float) -> np.ndarray:
    if geom.dune is None:
        return np.ones(len(geom))
    return np.where(geom.dune, penalty, 1.0)


def hazard_blocked(geom: EdgeGeometry, dune_blocked: bool, rsl_blocked: bool) -> np.ndarray:
    blocked = np.zeros(len(geom), dtype=bool)
    if dune_blocked and geom.dune is not None:
        blocked |= geom.dune
    if rsl_blocked and geom.rsl is not None:
        blocked |= geom.rsl
    return blocked
