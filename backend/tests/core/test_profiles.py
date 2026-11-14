import numpy as np
import pytest

from app.core.profiles import EdgeGeometry, check_edge_attrs
from app.core.resources import EDGE_ATTRS


def test_edge_geometry_derived_quantities():
    g = EdgeGeometry(d_m=[300.0, 400.0], dz_m=[400.0, -300.0])
    assert len(g) == 2
    np.testing.assert_allclose(g.length_m, [500.0, 500.0])
    np.testing.assert_allclose(g.gradient, [4 / 3, -0.75])
    assert g.theta_rad[0] > 0 > g.theta_rad[1]  # uphill vs downhill are signed


@pytest.mark.parametrize("d,dz", [([0.0], [1.0]), ([-5.0], [1.0]), ([1.0, 2.0], [1.0]), ([1.0], [np.nan]), ([np.inf], [1.0])])
def test_edge_geometry_rejects_bad_input(d, dz):
    with pytest.raises(ValueError):
        EdgeGeometry(d_m=d, dz_m=dz)


def test_edge_geometry_roughness_length_checked():
    with pytest.raises(ValueError):
        EdgeGeometry(d_m=[1.0, 2.0], dz_m=[0.0, 0.0], roughness_m=[1.0])


def _good(n=3):
    return {a: np.ones(n) for a in EDGE_ATTRS}


def test_check_edge_attrs_accepts_inf_but_not_nan_or_negative():
    attrs = _good()
    attrs["cost"][0] = np.inf
    check_edge_attrs(attrs, 3)
    for bad_value in (np.nan, -1.0):
        attrs = _good()
        attrs["o2_g"][1] = bad_value
        with pytest.raises(ValueError):
            check_edge_attrs(attrs, 3)


def test_check_edge_attrs_rejects_missing_extra_shape_dtype():
    attrs = _good()
    del attrs["water_g"]
    with pytest.raises(ValueError, match="missing"):
        check_edge_attrs(attrs, 3)
    attrs = _good()
    attrs["bogus"] = np.ones(3)
    with pytest.raises(ValueError, match="extra"):
        check_edge_attrs(attrs, 3)
    with pytest.raises(ValueError, match="shape"):
        check_edge_attrs(_good(2), 3)
    attrs = _good()
    attrs["cost"] = np.ones(3, dtype=int)
    with pytest.raises(ValueError, match="float"):
        check_edge_attrs(attrs, 3)
