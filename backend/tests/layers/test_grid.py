import numpy as np
import pytest

from app.layers.contracts import AOI_BBOX, GridSpec, default_grid


@pytest.fixture
def grid():
    return GridSpec(-72.0, -14.0, -68.0, -10.0, ncols=8, nrows=4)


def test_shape_and_cell_size(grid):
    assert grid.shape == (4, 8) and grid.n_nodes == 32
    assert grid.dlon == pytest.approx(0.5) and grid.dlat == pytest.approx(1.0)


def test_node_id_roundtrip(grid):
    row, col = grid.rc(grid.node_id(3, 5))
    assert (int(row), int(col)) == (3, 5)
    assert int(grid.node_id(0, 0)) == 0 and int(grid.node_id(3, 7)) == 31


def test_centres_row0_is_north(grid):
    assert grid.lat_centers()[0] > grid.lat_centers()[-1]
    assert grid.lat_centers()[0] == pytest.approx(-10.5)
    assert grid.lon_centers()[0] == pytest.approx(-71.75)
    lon, lat = grid.node_lonlat()
    assert lon.shape == lat.shape == (32,)
    assert (lon[0], lat[0]) == (grid.lon_centers()[0], grid.lat_centers()[0])
    assert lon[9] == grid.lon_centers()[1] and lat[9] == grid.lat_centers()[1]


def test_lonlat_to_rc_inside_edges_and_outside(grid):
    r, c = grid.lonlat_to_rc(-71.9, -10.1)
    assert (int(r), int(c)) == (0, 0)
    r, c = grid.lonlat_to_rc(-68.0, -14.0)  # east/south edges belong to the last cell
    assert (int(r), int(c)) == (3, 7)
    r, c = grid.lonlat_to_rc([-80.0, -70.0, np.nan], [-12.0, -20.0, -12.0])
    assert r.tolist() == [-1, -1, -1] and c.tolist() == [-1, -1, -1]


def test_centre_maps_back_to_its_own_cell(grid):
    lon, lat = grid.node_lonlat()
    r, c = grid.lonlat_to_rc(lon, lat)
    np.testing.assert_array_equal(grid.node_id(r, c), np.arange(grid.n_nodes))


def test_metric_spacing_shrinks_with_latitude():
    g = GridSpec(0.0, 0.0, 10.0, 80.0, ncols=10, nrows=8)
    dx, dy = g.metric_spacing()
    assert dy == pytest.approx(np.radians(10) * g.radius_m)
    assert dx[0] < dx[-1] and dx[0] < dy  # row 0 is the northernmost (highest latitude)


def test_default_grid_matches_context():
    g = default_grid()
    assert (g.west, g.south, g.east, g.north) == AOI_BBOX
    assert g.shape == (536, 600) and 300_000 < g.n_nodes < 340_000
    with pytest.raises(ValueError):
        default_grid(0)


def test_from_bbox_and_dict_roundtrip():
    g = GridSpec.from_bbox(AOI_BBOX, cell_m=400.0)
    assert 500 < g.ncols < 600 and 480 < g.nrows < 520
    assert GridSpec.from_dict(g.to_dict()) == g


@pytest.mark.parametrize("kwargs", [dict(west=1, south=0, east=0, north=1), dict(west=0, south=1, east=1, north=0),
                                    dict(west=-181, south=0, east=0, north=1)])
def test_invalid_bbox_rejected(kwargs):
    with pytest.raises(ValueError):
        GridSpec(**kwargs, ncols=2, nrows=2)
