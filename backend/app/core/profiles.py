"""Contract between the graph builder and the per-profile cost formulas.

The graph builder computes the geometry of every directed edge once (`EdgeGeometry`) and
hands it to each profile's `ProfileModel`, which returns the cost and the resource use for
every edge. Formulas live in app/routing/ (not here); this module only fixes the interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

import numpy as np

from app.core.resources import EDGE_ATTRS, ProfileId


@dataclass(frozen=True, eq=False)
class EdgeGeometry:
    """Geometry of m directed edges u -> v (signed: uphill and downhill differ).

    d_m: horizontal distance (> 0). dz_m = elev[v] - elev[u]. roughness_m optional (at v).
    """

    d_m: np.ndarray
    dz_m: np.ndarray
    roughness_m: np.ndarray | None = None

    def __post_init__(self):
        d = np.asarray(self.d_m, dtype=np.float64)
        dz = np.asarray(self.dz_m, dtype=np.float64)
        if d.ndim != 1 or d.shape != dz.shape:
            raise ValueError("d_m and dz_m must be 1-D arrays of the same length")
        if not (np.isfinite(d).all() and (d > 0).all()):
            raise ValueError("d_m must be finite and > 0")
        if not np.isfinite(dz).all():
            raise ValueError("dz_m must be finite (drop edges that touch nodata cells)")
        rough = None
        if self.roughness_m is not None:
            rough = np.asarray(self.roughness_m, dtype=np.float64)
            if rough.shape != d.shape:
                raise ValueError("roughness_m must have the same length as d_m")
        object.__setattr__(self, "d_m", d)
        object.__setattr__(self, "dz_m", dz)
        object.__setattr__(self, "roughness_m", rough)

    def __len__(self) -> int:
        return self.d_m.shape[0]

    @property
    def length_m(self) -> np.ndarray:
        return np.hypot(self.d_m, self.dz_m)

    @property
    def gradient(self) -> np.ndarray:
        return self.dz_m / self.d_m

    @property
    def theta_rad(self) -> np.ndarray:
        return np.arctan2(self.dz_m, self.d_m)


class ProfileModel(Protocol):
    """One profile's cost and resource formulas (implemented in app/routing/profiles)."""

    profile_id: ProfileId
    formula_version: str

    def compute_edge_attrs(self, geom: EdgeGeometry) -> Mapping[str, np.ndarray]:
        """Return one float array of length len(geom) for every name in EDGE_ATTRS.

        Impassable edges: every attribute = inf. All values >= 0, never NaN.
        """
        ...


def check_edge_attrs(attrs: Mapping[str, np.ndarray], n_edges: int) -> None:
    """Raise ValueError unless attrs is a valid result of ProfileModel.compute_edge_attrs."""
    missing = set(EDGE_ATTRS) - set(attrs)
    extra = set(attrs) - set(EDGE_ATTRS)
    if missing or extra:
        raise ValueError(f"edge attributes mismatch: missing={sorted(missing)} extra={sorted(extra)}")
    for name, arr in attrs.items():
        arr = np.asarray(arr)
        if arr.shape != (n_edges,):
            raise ValueError(f"{name}: expected shape ({n_edges},), got {arr.shape}")
        if not np.issubdtype(arr.dtype, np.floating):
            raise ValueError(f"{name}: expected a float dtype, got {arr.dtype}")
        if np.isnan(arr).any():
            raise ValueError(f"{name}: contains NaN")
        if (arr < 0).any():
            raise ValueError(f"{name}: contains negative values")
