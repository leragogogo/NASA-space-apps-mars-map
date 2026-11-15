"""Step 2: geometry of every directed edge, the input to the per-profile cost formulas.

d_m   horizontal distance: R * sqrt(dlat^2 + (cos(lat_mid) * dlon)^2), angles in radians
dz_m  elev[dst] - elev[src]  (signed: the reverse edge has the opposite sign)
Elevation comes from ReliefData.elev_m, the same array the slope overlay is derived from.
"""
from __future__ import annotations

import numpy as np

from app.core.profiles import EdgeGeometry
from app.layers.contracts import GridSpec


def edge_geometry(grid: GridSpec, elev_m: np.ndarray, src: np.ndarray, dst: np.ndarray,
                  roughness_m: np.ndarray | None = None) -> EdgeGeometry:
    """Geometry of the edges (src[i] -> dst[i]). Edges touching nodata must be dropped first
    (enumerate_edges does this from the valid mask); a NaN elevation raises ValueError."""
    if elev_m.shape != grid.shape:
        raise ValueError(f"elev_m shape {elev_m.shape} != grid shape {grid.shape}")
    if roughness_m is not None and roughness_m.shape != grid.shape:
        raise ValueError(f"roughness_m shape {roughness_m.shape} != grid shape {grid.shape}")
    src, dst = np.asarray(src), np.asarray(dst)
    if src.shape != dst.shape or src.ndim != 1:
        raise ValueError("src and dst must be 1-D arrays of the same length")

    elev = elev_m.astype(np.float64).ravel()  # row-major ravel == node-id order
    z_src, z_dst = elev[src], elev[dst]
    if np.isnan(z_src).any() or np.isnan(z_dst).any():
        raise ValueError("an edge touches a nodata cell; drop such edges before computing geometry")

    row_s, col_s = grid.rc(src)
    row_d, col_d = grid.rc(dst)
    lat_c, lon_c = grid.lat_centers(), grid.lon_centers()
    lat_s, lat_d = np.radians(lat_c[row_s]), np.radians(lat_c[row_d])
    dlon = np.radians(lon_c[col_d] - lon_c[col_s])
    dlat = lat_d - lat_s
    d_m = grid.radius_m * np.hypot(dlat, np.cos((lat_s + lat_d) / 2.0) * dlon)

    rough = None if roughness_m is None else roughness_m.astype(np.float64).ravel()[dst]
    return EdgeGeometry(d_m=d_m, dz_m=z_dst - z_src, roughness_m=rough)
