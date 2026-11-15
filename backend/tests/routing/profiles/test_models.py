import numpy as np
import pytest

from app.core.profiles import EdgeGeometry, check_edge_attrs
from app.core.resources import EDGE_ATTRS, ProfileId
from app.routing.profiles import (AstronautModel, AstronautParams, CarModel, CarParams, default_models)
from app.routing.profiles.astronaut import minetti_cost, tobler_speed_ms
from app.routing.profiles.params import versioned

MODELS = [AstronautModel(), CarModel()]
ids = [m.profile_id.value for m in MODELS]


def geom(gradients, d=400.0):
    g = np.asarray(gradients, dtype=float)
    return EdgeGeometry(d_m=np.full(g.shape, d), dz_m=g * d)


def slope_geom(deg, d=400.0):
    return EdgeGeometry(d_m=np.array([d]), dz_m=np.array([np.tan(np.radians(deg)) * d]))


@pytest.mark.parametrize("model", MODELS, ids=ids)
def test_attrs_are_valid_for_the_graph(model):
    g = geom(np.linspace(-0.8, 0.8, 41))
    attrs = model.compute_edge_attrs(g)
    check_edge_attrs(attrs, len(g))  # complete, float, no NaN, no negatives
    assert set(attrs) == set(EDGE_ATTRS)


@pytest.mark.parametrize("model", MODELS, ids=ids)
def test_flat_edge_cost_equals_its_length(model):
    g = geom([0.0])
    assert model.compute_edge_attrs(g)["cost"][0] == pytest.approx(g.length_m[0])  # alpha + beta == 1


@pytest.mark.parametrize("model", MODELS, ids=ids)
def test_beyond_the_hard_limit_every_attribute_is_inf_and_inside_it_is_finite(model):
    limit = model.params.hard_limit_deg
    over, under = model.compute_edge_attrs(slope_geom(limit + 1)), model.compute_edge_attrs(slope_geom(limit - 1))
    assert all(np.isinf(v).all() for v in over.values())
    assert all(np.isfinite(v).all() for v in under.values())
    # the limit applies to downhill too
    assert np.isinf(model.compute_edge_attrs(slope_geom(-(limit + 1)))["cost"]).all()


@pytest.mark.parametrize("model", MODELS, ids=ids)
def test_cost_grows_with_steepness_uphill(model):
    attrs = model.compute_edge_attrs(geom([0.0, 0.05, 0.1, 0.2]))
    assert (np.diff(attrs["cost"]) > 0).all() and (np.diff(attrs["energy_wh"]) > 0).all()


@pytest.mark.parametrize("model", MODELS, ids=ids)
def test_a_to_b_differs_from_b_to_a_on_a_slope(model):
    up, down = (model.compute_edge_attrs(geom([i]))["cost"][0] for i in (0.15, -0.15))
    assert up != pytest.approx(down) and up > down


@pytest.mark.parametrize("model", MODELS, ids=ids)
def test_resources_scale_linearly_with_length_on_a_uniform_slope(model):
    a = model.compute_edge_attrs(geom([0.1], d=100.0))
    b = model.compute_edge_attrs(geom([0.1], d=300.0))
    for name in EDGE_ATTRS:
        assert b[name][0] == pytest.approx(3 * a[name][0])


def test_astronaut_gentle_downhill_is_cheaper_than_flat_and_steep_downhill_costs_more():
    g = geom([0.0, -0.1, -0.2, -0.25])
    c = AstronautModel().compute_edge_attrs(g)
    per_m = c["o2_g"] / g.length_m  # metabolic: energy_wh is suit power x time, so it is not the right check
    assert per_m[1] < per_m[0]
    assert c["cost"][1] / g.length_m[1] < c["cost"][0] / g.length_m[0]  # gentle downhill beats flat
    assert per_m[3] > per_m[2]  # Minetti minimum is near i = -0.2


def test_minetti_and_tobler_reference_values():
    assert minetti_cost(np.array([0.0]))[0] == pytest.approx(2.5)
    assert minetti_cost(np.array([0.2]))[0] > minetti_cost(np.array([0.0]))[0]
    assert minetti_cost(np.array([-0.2]))[0] < 2.5
    # Tobler: 6 km/h at i = -0.05, scaled by speed_factor
    assert tobler_speed_ms(np.array([-0.05]), 1.0)[0] == pytest.approx(6 / 3.6)


def test_astronaut_resources_follow_the_metabolic_formulas():
    q = AstronautParams(o2_leak_g_per_s=0.0, env_heat_w=0.0)
    g = geom([0.0])
    a = AstronautModel(q).compute_edge_attrs(g)
    e_met = 2.5 * q.total_mass_kg * q.suit_mobility_penalty * g.length_m[0]
    o2_l = e_met / (q.o2_kj_per_l * 1000)
    assert a["o2_g"][0] == pytest.approx(o2_l * 1.429)
    assert a["co2_g"][0] == pytest.approx(q.rq * o2_l * 1.977)
    assert a["water_g"][0] == pytest.approx(e_met / q.h_cool_j_per_g)
    assert a["energy_wh"][0] == pytest.approx(q.p_suit_w * a["time_s"][0] / 3600)


def test_car_resources_are_driven_by_time_and_traction():
    q = CarParams()
    g = geom([0.0])
    a = CarModel(q).compute_edge_attrs(g)
    t = g.length_m[0] / q.v_max_ms
    assert a["time_s"][0] == pytest.approx(t)
    assert a["o2_g"][0] == pytest.approx(q.crew_n * q.crew_o2_g_per_s * t)
    traction = q.mass_kg * 3.71 * q.c_rr / q.eta_drive * g.length_m[0]
    assert a["energy_wh"][0] == pytest.approx((traction + q.p_aux_w * t) / 3600)


def test_car_gets_no_traction_credit_downhill_and_slows_near_the_limit():
    car = CarModel()
    steep_down = car.compute_edge_attrs(slope_geom(-20))
    flat = car.compute_edge_attrs(slope_geom(0))
    assert steep_down["energy_wh"][0] < flat["energy_wh"][0]
    assert steep_down["energy_wh"][0] >= car.params.p_aux_w * steep_down["time_s"][0] / 3600 - 1e-9
    assert car.speed_ms(np.radians(np.array([0.0, 15.0, 24.0]))).tolist() == sorted(
        car.speed_ms(np.radians(np.array([0.0, 15.0, 24.0]))), reverse=True)


def test_the_car_climbs_what_the_astronaut_cannot():
    g = slope_geom(22)  # between the astronaut limit (20) and the car limit (25)
    assert np.isinf(AstronautModel().compute_edge_attrs(g)["cost"]).all()
    assert np.isfinite(CarModel().compute_edge_attrs(g)["cost"]).all()


def test_default_models_order_and_profile_ids():
    models = default_models()
    assert [m.profile_id for m in models] == [ProfileId.ASTRONAUT, ProfileId.CAR]
    assert all("placeholder" in m.formula_version for m in models)


def test_formula_version_changes_when_a_parameter_changes():
    assert AstronautModel().formula_version == AstronautModel().formula_version
    assert AstronautModel(AstronautParams(suit_mass_kg=60.0)).formula_version != AstronautModel().formula_version
    assert versioned("x", CarParams()) != versioned("x", CarParams(mass_kg=900.0))


@pytest.mark.parametrize("bad", [dict(alpha=-1.0), dict(alpha=0.0, beta=0.0), dict(p=0.0), dict(hard_limit_deg=95.0),
                                 dict(body_mass_kg=0.0), dict(rq=-0.1)])
def test_astronaut_params_validate(bad):
    with pytest.raises(ValueError):
        AstronautParams(**bad)


@pytest.mark.parametrize("bad", [dict(v_min_ms=10.0), dict(mass_kg=0.0), dict(crew_n=-1), dict(beta=-0.5)])
def test_car_params_validate(bad):
    with pytest.raises(ValueError):
        CarParams(**bad)
