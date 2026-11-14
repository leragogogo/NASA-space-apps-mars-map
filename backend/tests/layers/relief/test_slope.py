import math

import numpy as np
from app.core.config import AOI, SLOPE_CLASSES
from app.layers.relief.slope import M_PER_DEG, classify, pixel_size_m, slope_degrees


def test_pixel_size_matches_real_grid():
    dx, dy = pixel_size_m((1073, 1200), AOI)
    assert round(dx) == 184 and round(dy) == 188
    assert M_PER_DEG == 2 * math.pi * 3_396_190 / 360


def test_slope_of_tilted_plane():
    shape = (5, 7)
    dx, _ = pixel_size_m(shape, AOI)
    plane = np.tile(
        np.arange(shape[1]) * dx * math.tan(math.radians(20)), (shape[0], 1)
    )
    assert np.allclose(slope_degrees(plane, AOI), 20.0)


def test_classify_edges_and_nodata():
    s = np.array([0, 4.99, 5, 14.9, 15, 24.9, 25, 35, 60, np.nan])
    assert classify(s, SLOPE_CLASSES).tolist() == [0, 0, 1, 1, 2, 2, 3, 4, 4, -1]
