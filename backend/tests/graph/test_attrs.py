import numpy as np
import pytest

from app.core.resources import EDGE_ATTRS, PROFILES, ProfileId, attr_key
from app.graph.attrs import combined_formula_version, compute_edge_arrays
from app.graph.contracts import GraphData
from app.graph.edges import enumerate_edges
from app.graph.geometry import edge_geometry
from app.layers.fakes import fake_grid, fake_relief
from tests.graph.stubs import StubProfile, stub_models


def geometry(kind="ramp", **kw):
    g = fake_grid(6, 8)
    relief = fake_relief(g, kind, **kw)
    src, dst = enumerate_edges(g, relief.valid)
    return g, relief, src, dst, edge_geometry(g, relief.elev_m, src, dst)


def test_arrays_for_every_profile_and_attribute_with_dtypes():
    *_, geom = geometry()
    arrays = compute_edge_arrays(geom, stub_models())
    assert set(arrays) == {attr_key(p, a) for p in PROFILES for a in EDGE_ATTRS}
    for key, arr in arrays.items():
        assert arr.shape == (len(geom),)
        assert arr.dtype == (np.float64 if key.endswith("__cost") else np.float32)


def test_profiles_get_their_own_values():
    *_, geom = geometry("flat")
    arrays = compute_edge_arrays(geom, stub_models())
    np.testing.assert_allclose(arrays["car__cost"], 2.0 * arrays["astronaut__cost"])


def test_hard_limit_makes_every_attribute_inf_for_that_profile_only():
    *_, geom = geometry("ramp", slope_deg_=20.0)  # steeper than 15, gentler than 35
    arrays = compute_edge_arrays(geom, stub_models(astronaut_limit_deg=15.0, car_limit_deg=35.0))
    too_steep = np.abs(np.degrees(geom.theta_rad)) > 15.0
    assert too_steep.any() and (~too_steep).any()
    for a in EDGE_ATTRS:
        np.testing.assert_array_equal(np.isinf(arrays[attr_key("astronaut", a)]), too_steep)
        assert np.isfinite(arrays[attr_key("car", a)]).all()


def test_inconsistent_impassable_edges_are_rejected():
    class Bad(StubProfile):
        def compute_edge_attrs(self, geom):
            attrs = super().compute_edge_attrs(geom)
            attrs["cost"] = attrs["cost"].copy()
            attrs["cost"][0] = np.inf  # cost inf but resources finite
            return attrs

    *_, geom = geometry("flat")
    with pytest.raises(ValueError, match="inf exactly where cost is inf"):
        compute_edge_arrays(geom, [Bad(ProfileId.ASTRONAUT), StubProfile(ProfileId.CAR)])


def test_model_output_is_validated():
    class NanModel(StubProfile):
        def compute_edge_attrs(self, geom):
            attrs = super().compute_edge_attrs(geom)
            attrs["o2_g"] = np.full(len(geom), np.nan)
            return attrs

    *_, geom = geometry("flat")
    with pytest.raises(ValueError, match="NaN"):
        compute_edge_arrays(geom, [NanModel(ProfileId.ASTRONAUT), StubProfile(ProfileId.CAR)])


def test_model_set_must_cover_each_profile_exactly_once():
    *_, geom = geometry("flat")
    with pytest.raises(ValueError, match="missing"):
        compute_edge_arrays(geom, [StubProfile(ProfileId.ASTRONAUT)])
    with pytest.raises(ValueError, match="duplicate"):
        compute_edge_arrays(geom, [StubProfile(ProfileId.CAR), StubProfile(ProfileId.CAR), StubProfile(ProfileId.ASTRONAUT)])


def test_combined_formula_version_is_stable_and_ordered():
    models = [StubProfile(ProfileId.CAR, "v2"), StubProfile(ProfileId.ASTRONAUT, "v1")]
    assert combined_formula_version(models) == "astronaut=v1;car=v2"
    assert combined_formula_version(models[::-1]) == "astronaut=v1;car=v2"


def test_steps_1_to_3_compose_into_a_valid_graph_data():
    g, relief, src, dst, geom = geometry("ramp", slope_deg_=10.0)
    models = stub_models()
    lon, lat = g.node_lonlat()
    node = {"lon": lon, "lat": lat, "elev_m": relief.elev_m.ravel(), "valid": relief.valid.ravel()}
    graph = GraphData(grid=g, node=node, src=src, dst=dst, edge_arrays=compute_edge_arrays(geom, models),
                      formula_version=combined_formula_version(models))
    graph.validate()
    view = graph.edge_attrs(0)
    assert set(view) == {"astronaut", "car"} and set(view["car"]) == set(EDGE_ATTRS)
