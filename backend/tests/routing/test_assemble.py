import pytest

from app.core.resources import RESOURCES
from app.routing.assemble import assemble, budget_warnings, stop_points
from app.routing.contracts import DropReason, DroppedStop, EndMode, RouteQuery, SolverResult
from app.routing.matrix import build_cost_matrix
from tests.routing.helpers import both, make_graph, resource_factor

# line 0 - 1 - 2 - 3 - 4, uphill (to the east) costs 2, downhill 1
LINE_GRAPH = make_graph(5, [edge for node in range(4) for edge in both(node, node + 1, 2.0, back=1.0)])


def plan(start, destinations, order, end_mode=EndMode.ROUND_TRIP, end=None, dropped=(), **kwargs):
    query = RouteQuery(profile="astronaut", start_node=start, destination_nodes=destinations,
                       end_mode=end_mode, end_node=end)
    cost_matrix = build_cost_matrix(LINE_GRAPH, query.profile, query.point_nodes)
    return assemble(LINE_GRAPH, query, cost_matrix, SolverResult(order=order, dropped=dropped), **kwargs)


def test_round_trip_joins_legs_without_duplicate_nodes():
    route = plan(0, (4, 2), order=(1, 0))  # 0 -> 2 -> 4 -> 0
    assert route.nodes == (0, 1, 2, 3, 4, 3, 2, 1, 0)
    assert [(leg.from_point, leg.to_point) for leg in route.legs] == [(0, 2), (2, 1), (1, 0)]
    assert [leg.cost for leg in route.legs] == [4.0, 4.0, 4.0]
    assert route.total_cost == 12.0 and route.stop_order == (1, 0)


def test_totals_match_the_sum_of_unscaled_legs_and_resources():
    route = plan(1, (3,), order=(0,))  # 1 -> 3 (cost 4), 3 -> 1 (cost 2)
    assert route.total_cost == sum(leg.cost for leg in route.legs) == 6.0
    for resource in RESOURCES:
        factor = resource_factor(resource)
        assert route.resources[resource] == 6.0 * factor
        assert [leg.resources[resource] for leg in route.legs] == [4.0 * factor, 2.0 * factor]


def test_fixed_end_and_open_end():
    fixed = plan(0, (2,), order=(0,), end_mode=EndMode.FIXED, end=4)
    assert fixed.nodes == (0, 1, 2, 3, 4) and fixed.legs[-1].to_point == 2
    open_end = plan(4, (2, 0), order=(0, 1), end_mode=EndMode.OPEN)
    assert open_end.nodes == (4, 3, 2, 1, 0) and len(open_end.legs) == 2 and open_end.total_cost == 4.0


def test_round_trip_that_visits_nothing_is_just_the_start():
    dropped = (DroppedStop(0, DropReason.UNREACHABLE_FOR_PROFILE),)
    route = plan(2, (4,), order=(), dropped=dropped)
    assert route.nodes == (2,) and route.legs == () and route.total_cost == 0.0
    assert route.dropped == dropped and all(value == 0.0 for value in route.resources.values())


def test_leg_without_saved_path_is_rejected():
    one_way_graph = make_graph(2, [(0, 1, 1.0)])  # no way back
    query = RouteQuery(profile="astronaut", start_node=0, destination_nodes=(1,))
    cost_matrix = build_cost_matrix(one_way_graph, query.profile, query.point_nodes)
    with pytest.raises(ValueError, match="no saved path"):
        assemble(one_way_graph, query, cost_matrix, SolverResult(order=(0,)))


def test_stop_points_per_end_mode():
    solution = SolverResult(order=(1, 0))
    base = dict(profile="astronaut", start_node=0, destination_nodes=(5, 6))
    assert stop_points(RouteQuery(**base), solution) == [0, 2, 1, 0]
    assert stop_points(RouteQuery(**base, end_mode=EndMode.FIXED, end_node=7), solution) == [0, 2, 1, 3]
    assert stop_points(RouteQuery(**base, end_mode=EndMode.OPEN), solution) == [0, 2, 1]


def test_budget_warnings_respect_the_reserve_margin():
    assert budget_warnings({"o2_g": 70.0}, {"o2_g": 100.0}, 0.2) == []
    [warning] = budget_warnings({"o2_g": 90.0, "time_s": 10.0}, {"o2_g": 100.0, "time_s": 100.0}, 0.2)
    assert "o2_g" in warning and "80.0 g" in warning
    route = plan(0, (4,), order=(0,), capacities={"time_s": 1.0})
    assert len(route.warnings) == 1 and "time_s" in route.warnings[0]
