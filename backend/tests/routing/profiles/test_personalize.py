import numpy as np
import pytest

from app.core.config import Settings
from app.core.profiles import EdgeGeometry
from app.core.resources import RESOURCES, ProfileId
from app.graph.build import BuildConfig, build_graph
from app.layers.fakes import fake_grid, fake_inputs
from app.routing.graph import RoutingGraph
from app.routing.profiles import AstronautModel, AstronautParams, CarModel, default_models
from app.routing.profiles.personalize import (graph_matches_models, path_resources_for_mass, reference_models,
                                              supports_body_mass)


def geom(gradients, d=400.0):
    g = np.asarray(gradients, dtype=float)
    return EdgeGeometry(d_m=np.full(g.shape, d), dz_m=g * d)


@pytest.fixture(scope="module")
def graph_and_path():
    """A graph built with the real profile models over a gentle ramp, and a walkable path along its top row."""
    grid = fake_grid(8, 10)
    data = build_graph(fake_inputs(grid, relief_kind="ramp"), default_models(), BuildConfig())
    rg = RoutingGraph.from_graph_data(data)
    return data, rg, list(range(grid.ncols))  # nodes 0..9: the north row, west to east


# ------------------------------------------------------------------ the model: mass changes resources, not the route
def test_cost_is_identical_for_every_body_mass():
    g = geom([-0.2, -0.05, 0.0, 0.1, 0.2])
    light = AstronautModel(AstronautParams(body_mass_kg=50.0)).compute_edge_attrs(g)["cost"]
    heavy = AstronautModel(AstronautParams(body_mass_kg=120.0)).compute_edge_attrs(g)["cost"]
    np.testing.assert_allclose(light, heavy)  # mass cancels in the cost formula: the same route for everyone


def test_only_oxygen_co2_and_water_depend_on_mass():
    m, g = AstronautModel(), geom([0.0, 0.1, -0.1])
    base, heavy = m.resources(g), m.resources(g, body_mass_kg=m.params.body_mass_kg + 40.0)
    for name in ("time_s", "energy_wh"):
        np.testing.assert_allclose(base[name], heavy[name])
    for name in ("o2_g", "co2_g", "water_g"):
        assert (heavy[name] > base[name]).all()


def test_metabolic_resources_are_linear_in_total_mass():
    m, g = AstronautModel(AstronautParams(o2_leak_g_per_s=0.0, env_heat_w=0.0)), geom([0.05])
    q = m.params
    totals = {mass: m.resources(g, mass)["o2_g"][0] for mass in (50.0, 70.0, 90.0)}
    assert totals[90.0] - totals[70.0] == pytest.approx(totals[70.0] - totals[50.0])
    assert totals[70.0] / totals[50.0] == pytest.approx((70 + q.suit_mass_kg + q.gear_mass_kg)
                                                        / (50 + q.suit_mass_kg + q.gear_mass_kg))


def test_the_default_mass_reproduces_what_the_graph_builder_stores():
    m, g = AstronautModel(), geom([-0.1, 0.0, 0.15])
    stored = m.compute_edge_attrs(g)
    for name, value in m.resources(g).items():
        np.testing.assert_allclose(stored[name], value)
    np.testing.assert_allclose(m.resources(g, m.params.body_mass_kg)["o2_g"], stored["o2_g"])


def test_nonpositive_mass_is_rejected():
    with pytest.raises(ValueError, match="body_mass_kg"):
        AstronautModel().resources(geom([0.0]), body_mass_kg=0.0)


# ------------------------------------------------------------------ on a real graph path
def test_at_the_reference_mass_the_request_time_numbers_equal_the_graphs_own(graph_and_path):
    data, rg, nodes = graph_and_path
    model = reference_models(Settings())[ProfileId.ASTRONAUT]
    live = path_resources_for_mass(rg, model, nodes, model.params.body_mass_kg)
    stored = rg.path_resources(ProfileId.ASTRONAUT, nodes)
    assert set(live) == set(RESOURCES)
    for r in RESOURCES:
        assert live[r] == pytest.approx(stored[r], rel=1e-5)  # the stored arrays are float32


def test_a_heavier_user_uses_more_o2_co2_and_water_but_the_same_time_and_energy(graph_and_path):
    _, rg, nodes = graph_and_path
    model = reference_models(Settings())[ProfileId.ASTRONAUT]
    light, heavy = (path_resources_for_mass(rg, model, nodes, kg) for kg in (60.0, 110.0))
    for r in ("o2_g", "co2_g", "water_g"):
        assert heavy[r] > light[r]
    for r in ("time_s", "energy_wh"):
        assert heavy[r] == pytest.approx(light[r])


def test_a_path_without_edges_costs_nothing(graph_and_path):
    _, rg, _ = graph_and_path
    model = reference_models(Settings())[ProfileId.ASTRONAUT]
    assert path_resources_for_mass(rg, model, [3], 80.0) == {r: 0.0 for r in RESOURCES}


# ------------------------------------------------------------------ guards
def test_only_the_astronaut_depends_on_body_mass():
    assert supports_body_mass("astronaut") and not supports_body_mass(ProfileId.CAR)


def test_graph_version_guard(graph_and_path):
    data, _, _ = graph_and_path
    assert graph_matches_models(data.formula_version, reference_models(Settings()))
    assert not graph_matches_models("something-else", reference_models(Settings()))
    other = [AstronautModel(AstronautParams(suit_mass_kg=60.0)), CarModel()]
    assert not graph_matches_models(data.formula_version, {m.profile_id: m for m in other})
