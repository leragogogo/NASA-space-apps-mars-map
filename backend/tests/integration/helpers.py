"""Shared data for the integration tests: the synthetic data root with a DEM both profiles can cross."""
from pathlib import Path

import numpy as np
import tifffile

from app.layers.contracts import AOI_BBOX, GridSpec
from tests.conftest import DEM_SHAPE, build_fixture_data

FIXTURE_GRID = GridSpec(*AOI_BBOX, ncols=DEM_SHAPE[1], nrows=DEM_SHAPE[0])  # the graph grid of the fixture data


def node_point(row: int, col: int, jitter: float = 0.0) -> dict:
    """lon/lat of a graph node centre of the fixture grid (its nodes are ~28 km apart, snap limit is 1 km)."""
    return {"lon": float(FIXTURE_GRID.lon_centers()[col]) + jitter, "lat": float(FIXTURE_GRID.lat_centers()[row])}


def make_gentle_data(root: Path) -> Path:
    """The shared fixture data root, but with a gentle DEM.

    The fixture DEM is a steep 10 deg plane (tens of km high at this size); a smooth surface keeps
    elevations plausible and slopes drivable and walkable.
    """
    build_fixture_data(root)
    rows, cols = DEM_SHAPE
    y, x = np.mgrid[0:rows, 0:cols]
    tifffile.imwrite(root / "raw/dem/dem_blend200m_aoi.tif",
                     (1200.0 * np.sin(x / 3.0) + 400.0 * np.cos(y / 2.0)).astype("float32"))
    return root
