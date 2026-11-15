import numpy as np
import pytest

from app.core.profiles import EdgeGeometry
from app.routing.profiles import AstronautModel, CarModel, CarParams
from app.routing.profiles.terrain import (ROUGHNESS_CAP, dune_factor, effective_slope_rad, hazard_blocked,
                                          roughness_factor)

MODELS = [AstronautModel(), CarModel()]
IDS = ["astronaut", "car"]


def flat(n=1, d=400.0, **extra):
    return EdgeGeometry(d_m=np.full(n, d), dz_m=np.zeros(n), **extra)


def test_effective_slope_is_the_steeper_of_travel_gradient_and_map_slope():
    g = EdgeGeometry(d_m=np.array([400.0, 400.0]), dz_m=np.array([0.0, 400.0 * np.tan(np.radians(30))]),
                     terrain_slope_deg=np.array([22.0, 10.0]))
    assert np.degrees(effective_slope_rad(g)) == pytest.approx([22.0, 30.0])


def test_without_map_slope_the_travel_gradient_is_used():
    g = EdgeGeometry(d_m=np.array([400.0]), dz_m=np.array([400.0 * np.tan(np.radians(12))]))
    assert np.degrees(effective_slope_rad(g)) == pytest.approx([12.0])


def test_roughness_factor_is_linear_then_capped():
    g = flat(3, roughness_m=np.array([0.0, 3.0, 300.0]))
    assert roughness_factor(g, 0.5, 3.0) == pytest.approx([1.0, 1.5, 1.0 + 0.5 * ROUGHNESS_CAP])
    assert roughness_factor(flat(2), 0.5, 3.0) == pytest.approx([1.0, 1.0])  # no roughness data


def test_dune_factor_and_hazard_blocking():
    g = flat(3, dune=np.array([True, False, False]), rsl=np.array([False, True, False]))
    assert dune_factor(g, 1.5) == pytest.approx([1.5, 1.0, 1.0])
    assert hazard_blocked(g, dune_blocked=True, rsl_blocked=True).tolist() == [True, True, False]
    assert hazard_blocked(g, dune_blocked=False, rsl_blocked=False).tolist() == [False, False, False]
    assert hazard_blocked(flat(), True, True).tolist() == [False]


@pytest.mark.parametrize("terrain, walk_ok, drive_ok", [(10.0, True, True), (22.0, False, True), (30.0, False, False)])
def test_moving_along_a_steep_hillside_is_blocked_as_the_map_shows(terrain, walk_ok, drive_ok):
    g = flat(terrain_slope_deg=np.array([terrain]))  # dz = 0: along the contour line
    assert bool(np.isfinite(AstronautModel().compute_edge_attrs(g)["cost"][0])) == walk_ok
    assert bool(np.isfinite(CarModel().compute_edge_attrs(g)["cost"][0])) == drive_ok


@pytest.mark.parametrize("model", MODELS, ids=IDS)
def test_cross_slope_costs_more_than_flat_ground(model):
    on_flat = model.compute_edge_attrs(flat(terrain_slope_deg=np.array([0.0])))["cost"][0]
    on_hillside = model.compute_edge_attrs(flat(terrain_slope_deg=np.array([15.0])))["cost"][0]
    assert on_hillside > on_flat


def test_dunes_slow_walking_and_block_the_car():
    walk = AstronautModel().compute_edge_attrs(flat(dune=np.array([True])))
    plain = AstronautModel().compute_edge_attrs(flat())
    assert walk["cost"][0] == pytest.approx(1.5 * plain["cost"][0])
    assert walk["time_s"][0] == pytest.approx(plain["time_s"][0])  # terrain terms never change resources
    assert all(np.isinf(v[0]) for v in CarModel().compute_edge_attrs(flat(dune=np.array([True]))).values())
    assert np.isfinite(CarModel(CarParams(dune_blocked=False)).compute_edge_attrs(flat(dune=np.array([True])))["cost"][0])


@pytest.mark.parametrize("model", MODELS, ids=IDS)
def test_rsl_buffer_blocks_both_profiles(model):
    assert all(np.isinf(v[0]) for v in model.compute_edge_attrs(flat(rsl=np.array([True]))).values())


def test_rough_ground_costs_more_for_the_car_than_for_walking():
    g = flat(roughness_m=np.array([3.0]))
    ratio = lambda m: m.compute_edge_attrs(g)["cost"][0] / m.compute_edge_attrs(flat())["cost"][0]  # noqa: E731
    assert ratio(AstronautModel()) == pytest.approx(1.5) and ratio(CarModel()) == pytest.approx(2.0)


def test_formula_versions_are_bumped():
    assert AstronautModel().formula_version.startswith("astronaut-tobler-minetti-2-")
    assert CarModel().formula_version.startswith("car-traction-2-")


def test_the_slope_margin_uses_the_map_slope_across_the_path():
    # Car on a level edge across a 15 deg hillside: speed and energy ratios stay 1, only the margin changes.
    cost = CarModel().compute_edge_attrs(flat(terrain_slope_deg=np.array([15.0])))["cost"][0]
    assert cost == pytest.approx(400.0 * (1 + (15.0 / 25.0) ** 2))


@pytest.mark.parametrize("model", MODELS, ids=IDS)
def test_a_map_slope_exactly_at_the_limit_is_still_passable(model):
    g = flat(terrain_slope_deg=np.array([model.params.hard_limit_deg]))
    assert np.isfinite(model.compute_edge_attrs(g)["cost"][0])
