"""Step 2: geometry of every directed edge, the input to the per-profile cost formulas.

d_m   horizontal distance: R * sqrt(dlat^2 + (cos(lat_mid) * dlon)^2), angles in radians
dz_m  elev[dst] - elev[src]  (signed: the reverse edge has the opposite sign)
Elevation comes from ReliefData.elev_m, the same array the slope overlay is derived from.
Optional terrain: the larger map slope of the two end cells, and a dune / RSL flag when either end cell has one.
"""
from __future__ import annotations

import numpy as np

from app.core.profiles import EdgeGeometry
from app.layers.contracts import GridSpec


def edge_geometry(grid: GridSpec, elev_m: np.ndarray, src: np.ndarray, dst: np.ndarray,
                  roughness_m: np.ndarray | None = None, slope_deg: np.ndarray | None = None,
                  dune: np.ndarray | None = None, rsl: np.ndarray | None = None) -> EdgeGeometry:
    """Geometry of the edges (src[i] -> dst[i]). Edges touching nodata must be dropped first
    (enumerate_edges does this from the valid mask); a NaN elevation raises ValueError."""
    for name, arr in (("elev_m", elev_m), ("roughness_m", roughness_m), ("slope_deg", slope_deg),
                      ("dune", dune), ("rsl", rsl)):
        if arr is not None and arr.shape != grid.shape:
            raise ValueError(f"{name} shape {arr.shape} != grid shape {grid.shape}")
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
    terrain = None
    if slope_deg is not None:
        s = slope_deg.astype(np.float64).ravel()
        terrain = np.maximum(s[src], s[dst])
    either = lambda mask: None if mask is None else (mask.ravel()[src] | mask.ravel()[dst])  # noqa: E731
    return EdgeGeometry(d_m=d_m, dz_m=z_dst - z_src, roughness_m=rough, terrain_slope_deg=terrain,
                        dune=either(dune), rsl=either(rsl))
