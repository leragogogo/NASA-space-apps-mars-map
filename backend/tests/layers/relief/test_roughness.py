import numpy as np

from app.layers.relief.roughness import roughness_m


def test_any_plane_has_zero_roughness_however_steep():
    rows, cols = np.mgrid[0:6, 0:7]
    plane = (50.0 * cols - 30.0 * rows + 1000.0).astype(np.float32)
    assert np.allclose(roughness_m(plane), 0.0, atol=1e-3)


def test_a_bump_is_rough_and_its_neighbours_half_as_much_on_one_axis():
    z = np.zeros((5, 5), dtype=np.float32)
    z[2, 2] = 10.0
    r = roughness_m(z)
    assert r[2, 2] == np.float32(10.0)
    # north neighbour: north/south pair deviates by 5, west/east pair by 0 -> mean 2.5
    assert r[1, 2] == np.float32(2.5) and r[0, 0] == 0.0


def test_nodata_stays_nan_and_a_cell_without_a_full_neighbour_pair_is_zero():
    z = np.array([[1.0, np.nan], [np.nan, np.nan]], dtype=np.float32)
    r = roughness_m(z)
    assert r[0, 0] == 0.0 and np.isnan(r[0, 1]) and np.isnan(r[1, 0]) and np.isnan(r[1, 1])
    assert r.dtype == np.float32
