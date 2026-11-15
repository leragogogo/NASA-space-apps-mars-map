import numpy as np
import pytest

from app.graph.edges import enumerate_edges
from app.graph.geometry import edge_geometry
from app.layers.fakes import fake_grid, fake_relief


def edge_index(src, dst, a, b):
    return int(np.flatnonzero((src == a) & (dst == b))[0])


def setup(kind="flat", **kw):
    g = fake_grid(6, 8)
    relief = fake_relief(g, kind, **kw)
    src, dst = enumerate_edges(g, relief.valid)
    return g, relief, src, dst


def test_distances_match_cell_spacing():
    g, relief, src, dst = setup()
    geom = edge_geometry(g, relief.elev_m, src, dst)
    dx, dy = g.metric_spacing()
    row, col = 2, 3
    n = int(g.node_id(row, col))
    east = edge_index(src, dst, n, n + 1)
    south = edge_index(src, dst, n, n + g.ncols)
    diag = edge_index(src, dst, n, n + g.ncols + 1)
    assert geom.d_m[east] == pytest.approx(dx[row], rel=1e-9)
    assert geom.d_m[south] == pytest.approx(dy, rel=1e-9)
    assert geom.d_m[diag] == pytest.approx(np.hypot(dx[row], dy), rel=1e-3)
    assert np.allclose(geom.dz_m, 0.0)


def test_reverse_edges_have_equal_distance_and_opposite_dz():
    g, relief, src, dst = setup("ramp", slope_deg_=10.0)
    geom = edge_geometry(g, relief.elev_m, src, dst)
    rev = np.array([edge_index(src, dst, b, a) for a, b in zip(src, dst)])
    np.testing.assert_allclose(geom.d_m[rev], geom.d_m, rtol=1e-12)
    np.testing.assert_allclose(geom.dz_m[rev], -geom.dz_m, atol=1e-9)


def test_ramp_uphill_east_downhill_west():
    g, relief, src, dst = setup("ramp", slope_deg_=10.0)
    geom = edge_geometry(g, relief.elev_m, src, dst)
    n = int(g.node_id(3, 3))
    up = edge_index(src, dst, n, n + 1)
    down = edge_index(src, dst, n + 1, n)
    assert np.degrees(geom.theta_rad[up]) == pytest.approx(10.0, abs=0.3)
    assert np.degrees(geom.theta_rad[down]) == pytest.approx(-10.0, abs=0.3)


def test_length_is_hypot_of_d_and_dz():
    g, relief, src, dst = setup("bowl")
    geom = edge_geometry(g, relief.elev_m, src, dst)
    np.testing.assert_allclose(geom.length_m, np.hypot(geom.d_m, geom.dz_m))


def test_roughness_is_taken_at_the_destination():
    g, relief, src, dst = setup()
    rough = np.arange(g.n_nodes, dtype=np.float32).reshape(g.shape)
    geom = edge_geometry(g, relief.elev_m, src, dst, roughness_m=rough)
    np.testing.assert_array_equal(geom.roughness_m, dst.astype(np.float64))


def test_edge_touching_nodata_is_rejected():
    g, relief, src, dst = setup()
    elev = relief.elev_m.copy()
    elev[0, 0] = np.nan
    with pytest.raises(ValueError, match="nodata"):
        edge_geometry(g, elev, src, dst)


def test_nodata_dropped_by_enumerate_edges_then_geometry_works():
    g = fake_grid(4, 4)
    relief = fake_relief(g, "ramp")
    elev = relief.elev_m.copy()
    elev[1, 1] = np.nan
    src, dst = enumerate_edges(g, ~np.isnan(elev))
    geom = edge_geometry(g, elev, src, dst)
    assert len(geom) == len(src) and np.isfinite(geom.dz_m).all()


def test_shape_mismatches_rejected():
    g, relief, src, dst = setup()
    with pytest.raises(ValueError):
        edge_geometry(g, relief.elev_m[:-1], src, dst)
    with pytest.raises(ValueError):
        edge_geometry(g, relief.elev_m, src, dst[:-1])
    with pytest.raises(ValueError):
        edge_geometry(g, relief.elev_m, src, dst, roughness_m=np.zeros((2, 2), np.float32))
