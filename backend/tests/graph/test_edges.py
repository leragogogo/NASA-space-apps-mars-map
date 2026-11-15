import numpy as np
import pytest

from app.graph.edges import enumerate_edges
from app.layers.contracts import default_grid
from app.layers.fakes import fake_grid


def pairs(src, dst):
    return set(zip(src.tolist(), dst.tolist()))


def test_3x3_degrees_and_total():
    g = fake_grid(3, 3)
    src, dst = enumerate_edges(g, np.ones(g.shape, bool))
    assert len(src) == 40  # 4 corners*3 + 4 sides*5 + centre*8
    deg = np.bincount(src, minlength=9)
    assert deg[[0, 2, 6, 8]].tolist() == [3, 3, 3, 3]
    assert deg[[1, 3, 5, 7]].tolist() == [5, 5, 5, 5]
    assert deg[4] == 8


def test_every_edge_has_a_reverse_no_duplicates_no_self_loops():
    g = fake_grid(5, 6)
    src, dst = enumerate_edges(g, np.ones(g.shape, bool))
    p = pairs(src, dst)
    assert len(p) == len(src)
    assert p == {(b, a) for a, b in p}
    assert (src != dst).all()


def test_sorted_dtype_and_range():
    g = fake_grid(4, 4)
    src, dst = enumerate_edges(g, np.ones(g.shape, bool))
    assert src.dtype == dst.dtype == np.int32
    assert (np.diff(src) >= 0).all()
    assert src.min() >= 0 and max(src.max(), dst.max()) < g.n_nodes
    same_src = src[1:] == src[:-1]
    assert (np.diff(dst)[same_src] > 0).all()  # sorted by dst within a source


def test_nodata_cell_has_no_edges_but_keeps_its_id():
    g = fake_grid(3, 3)
    valid = np.ones(g.shape, bool)
    valid[1, 1] = False
    src, dst = enumerate_edges(g, valid)
    assert 4 not in src and 4 not in dst
    assert len(src) == 40 - 16  # the centre had 8 out + 8 in
    assert len(src) == len(pairs(src, dst))


def test_all_invalid_gives_empty_arrays():
    g = fake_grid(3, 3)
    src, dst = enumerate_edges(g, np.zeros(g.shape, bool))
    assert len(src) == len(dst) == 0 and src.dtype == np.int32


def test_four_neighbourhood_and_single_row():
    g = fake_grid(3, 3)
    src, _ = enumerate_edges(g, np.ones(g.shape, bool), neighbours=4)
    assert len(src) == 24
    row = fake_grid(1, 4)
    src, dst = enumerate_edges(row, np.ones(row.shape, bool))
    assert pairs(src, dst) == {(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2)}


def test_bad_arguments():
    g = fake_grid(3, 3)
    with pytest.raises(ValueError):
        enumerate_edges(g, np.ones(g.shape, bool), neighbours=6)
    with pytest.raises(ValueError):
        enumerate_edges(g, np.ones((2, 2), bool))


def test_edge_count_formula_at_default_grid_size():
    g = default_grid()
    rows, cols = g.shape
    src, dst = enumerate_edges(g, np.ones(g.shape, bool))
    undirected = rows * (cols - 1) + cols * (rows - 1) + 2 * (rows - 1) * (cols - 1)
    assert len(src) == len(dst) == 2 * undirected
