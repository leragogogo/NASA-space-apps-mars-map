"""Slope from the elevation grid. The single implementation shared by the relief display overlay
and the master graph, so users and the router see the same slope (SKILL.md section 9)."""
from __future__ import annotations

import math

import numpy as np

from app.layers.contracts import MARS_RADIUS_M, GridSpec

M_PER_DEG = 2 * math.pi * MARS_RADIUS_M / 360  # metres per degree of arc on the Mars 2000 sphere


def _index_gradient(a: np.ndarray, axis: int) -> np.ndarray:
    """d(a)/d(index): central difference, one-sided next to nodata or at the edge.

    A valid cell with no valid neighbour along the axis gets 0 for that axis (no information).
    NaN is kept where the cell itself is NaN.
    """
    pad = [(0, 0), (0, 0)]
    pad[axis] = (1, 1)
    p = np.pad(a, pad, constant_values=np.nan)
    n = a.shape[axis]
    prv = np.take(p, np.arange(0, n), axis=axis)
    cen = np.take(p, np.arange(1, n + 1), axis=axis)
    nxt = np.take(p, np.arange(2, n + 2), axis=axis)
    central = (nxt - prv) / 2.0
    fwd = nxt - cen
    bwd = cen - prv
    out = np.where(np.isnan(central), np.where(np.isnan(fwd), bwd, fwd), central)
    out = np.nan_to_num(out, nan=0.0)
    return np.where(np.isnan(cen), np.nan, out)


def slope_deg(elev_m: np.ndarray, grid: GridSpec) -> np.ndarray:
    """Slope in degrees (float32), same shape as elev_m. NaN where elev_m is NaN."""
    if elev_m.shape != grid.shape:
        raise ValueError(f"elev_m shape {elev_m.shape} != grid shape {grid.shape}")
    if min(grid.shape) < 2:
        raise ValueError("slope needs a grid of at least 2 x 2 cells")
    elev = elev_m.astype(np.float64)
    dx_m, dy_m = grid.metric_spacing()
    gx = _index_gradient(elev, axis=1) / dx_m[:, None]
    gy = _index_gradient(elev, axis=0) / dy_m
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)


def pixel_size_m(shape: tuple[int, int], aoi: tuple) -> tuple[float, float]:
    """(east-west, north-south) pixel size in metres for a grid covering `aoi`,
    east-west measured at the latitude of the area centre."""
    ny, nx = shape
    w, s, e, n = aoi
    lat_c = math.radians((s + n) / 2)
    return (e - w) / nx * M_PER_DEG * math.cos(lat_c), (n - s) / ny * M_PER_DEG


def slope_degrees(elev: np.ndarray, aoi: tuple) -> np.ndarray:
    """`slope_deg` for a grid that covers `aoi` exactly (what the relief getter holds)."""
    ny, nx = elev.shape
    return slope_deg(elev, GridSpec(*aoi, ncols=nx, nrows=ny))


def classify(slope: np.ndarray, classes) -> np.ndarray:
    """Index into `classes` per cell (lower edge inclusive); -1 where slope is NaN."""
    edges = [c.max_deg for c in classes[:-1]]
    out = np.digitize(slope, edges).astype(np.int8)
    out[np.isnan(slope)] = -1
    return out
