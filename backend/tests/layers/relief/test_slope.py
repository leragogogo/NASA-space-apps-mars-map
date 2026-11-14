import numpy as np
import pytest

from app.layers.fakes import fake_grid, fake_relief
from app.layers.relief.slope import slope_deg


def test_flat_is_zero():
    g = fake_grid()
    r = fake_relief(g, "flat")
    assert np.allclose(r.slope_deg, 0.0)
    assert r.slope_deg.dtype == np.float32


def test_ramp_recovers_its_angle():
    r = fake_relief(fake_grid(), "ramp", slope_deg_=10.0)
    assert np.allclose(r.slope_deg, 10.0, atol=0.5)


def test_cliff_is_steep_only_at_the_step():
    g = fake_grid()
    r = fake_relief(g, "cliff", height_m=5000.0)
    assert r.slope_deg.max() > 60
    assert np.allclose(r.slope_deg[:, :3], 0.0)


def test_nodata_stays_nan_and_neighbours_stay_finite():
    g = fake_grid(6, 6)
    elev = fake_relief(g, "ramp").elev_m.copy()
    elev[3, 3] = np.nan
    s = slope_deg(elev, g)
    assert np.isnan(s[3, 3])
    assert np.isfinite(np.delete(s.ravel(), 3 * 6 + 3)).all()


def test_isolated_valid_cell_gets_zero_not_nan():
    g = fake_grid(3, 3)
    elev = np.full(g.shape, np.nan, dtype=np.float32)
    elev[1, 1] = 100.0
    assert slope_deg(elev, g)[1, 1] == 0.0


def test_bad_shapes_rejected():
    g = fake_grid(4, 4)
    with pytest.raises(ValueError):
        slope_deg(np.zeros((3, 3), dtype=np.float32), g)
    with pytest.raises(ValueError):
        slope_deg(np.zeros((1, 4), dtype=np.float32), fake_grid(1, 4))
