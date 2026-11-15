import math

import numpy as np
from app.core.config import AOI, SLOPE_CLASSES
from app.layers.contracts import GridSpec
from app.layers.relief.slope import M_PER_DEG, classify, pixel_size_m, slope_deg, slope_degrees


def test_pixel_size_matches_real_grid():
    dx, dy = pixel_size_m((1073, 1200), AOI)
    assert round(dx) == 184 and round(dy) == 188
    assert M_PER_DEG == 2 * math.pi * 3_396_190 / 360


def test_slope_of_tilted_plane():
    shape = (5, 7)
    grid = GridSpec(*AOI, ncols=shape[1], nrows=shape[0])
    dx_row, _ = grid.metric_spacing()  # east-west cell size shrinks with latitude
    rise_per_col = 200.0  # metres of rise per column; same on every row, so the plane is a true plane
    plane = np.tile(np.arange(shape[1]) * rise_per_col, (shape[0], 1))
    expected = np.degrees(np.arctan(rise_per_col / dx_row))[:, None] * np.ones(shape)
    assert np.allclose(slope_degrees(plane, AOI), expected, atol=1e-4)


def test_slope_degrees_is_the_shared_slope_deg():
    """Display slope and routing slope must be one implementation (SKILL.md section 9)."""
    rng = np.random.default_rng(0)
    elev = rng.normal(0, 50, (9, 11))
    elev[3, 4] = np.nan
    grid = GridSpec(*AOI, ncols=11, nrows=9)
    shared = slope_deg(elev, grid)
    got = slope_degrees(elev, AOI)
    assert got.dtype == np.float32
    assert np.array_equal(got, shared, equal_nan=True)
    assert np.isnan(got[3, 4]) and np.isfinite(got[3, 5])  # nodata does not poison its neighbours


def test_classify_edges_and_nodata():
    s = np.array([0, 4.99, 5, 14.9, 15, 19.9, 20, 24.9, 25, 60, np.nan])
    assert classify(s, SLOPE_CLASSES).tolist() == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, -1]
