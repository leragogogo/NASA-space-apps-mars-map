import pytest

from app.routing.contracts import DropReason, EndMode, RouteQuery
from app.routing.service import plan_route
from app.routing.solver import NoFeasibleRoute
from tests.routing.helpers import INF, both, make_graph

# 0 - 1 - 2 - 3 on flat ground; 3 -> 4 is a cliff: the car can climb it, the astronaut cannot.
# 4 -> 3 is passable for both, 5 is isolated.
EDGES = [*both(0, 1, 1.0), *both(1, 2, 1.0), *both(2, 3, 1.0), (3, 4, INF), (4, 3, 1.0)]
CLIFF_GRAPH = make_graph(6, EDGES, car_edges={(3, 4): 5.0})


def make_query(profile="astronaut", destinations=(3, 1, 4), **kwargs):
    return RouteQuery(profile=profile, start_node=0, destination_nodes=destinations, time_limit_s=1, **kwargs)


def assert_continuous(route):
    for from_node, to_node in zip(route.nodes, route.nodes[1:]):
        assert CLIFF_GRAPH.edge_id(from_node, to_node) >= 0


def test_astronaut_drops_the_stop_beyond_the_cliff():
    route = plan_route(CLIFF_GRAPH, make_query())
    assert route.stop_order == (0, 1)  # the order given; the stop beyond the cliff is skipped
    assert [(stop.index, stop.reason) for stop in route.dropped] == [(2, DropReason.UNREACHABLE_FOR_PROFILE)]
    assert route.nodes == (0, 1, 2, 3, 2, 1, 0) and route.total_cost == 6.0
    assert_continuous(route)


def test_car_reaches_every_stop():
    route = plan_route(CLIFF_GRAPH, make_query(profile="car"))
    # stops in the order given (nodes 3, 1, 4), not reordered: 0->3, 3->1, 1->4 (over the climb), 4->0
    assert route.stop_order == (0, 1, 2) and route.dropped == ()
    assert route.total_cost == 3.0 + 2.0 + 7.0 + 4.0
    assert_continuous(route)


def test_isolated_fixed_end_raises():
    with pytest.raises(NoFeasibleRoute):
        plan_route(CLIFF_GRAPH, make_query(destinations=(2,), end_mode=EndMode.FIXED, end_node=5))


def p2p(end_node, profile="astronaut"):
    return RouteQuery(profile=profile, start_node=0, destination_nodes=(), end_mode=EndMode.FIXED,
                      end_node=end_node, time_limit_s=1)


def test_point_to_point_route_needs_no_destinations():
    route = plan_route(CLIFF_GRAPH, p2p(3))
    assert route.nodes == (0, 1, 2, 3) and route.total_cost == 3.0 and route.stop_order == ()
    assert [(leg.from_point, leg.to_point) for leg in route.legs] == [(0, 1)]


def test_point_to_point_without_a_path_raises():
    with pytest.raises(NoFeasibleRoute, match="astronaut"):
        plan_route(CLIFF_GRAPH, p2p(4))
    assert plan_route(CLIFF_GRAPH, p2p(4, "car")).nodes[-1] == 4


def test_stops_are_visited_in_the_order_given_not_reordered():
    route = plan_route(CLIFF_GRAPH, make_query(profile="car", destinations=(3, 1)))
    assert route.stop_order == (0, 1) and route.nodes[:4] == (0, 1, 2, 3)  # node 3 first, as asked


def test_a_skipped_stop_does_not_stop_the_route():
    route = plan_route(CLIFF_GRAPH, make_query(destinations=(4, 2)))  # 4 is beyond the cliff for the astronaut
    assert route.stop_order == (1,) and [d.index for d in route.dropped] == [0]
    assert route.nodes == (0, 1, 2, 1, 0)
