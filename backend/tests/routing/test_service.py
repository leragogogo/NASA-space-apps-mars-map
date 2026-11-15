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
    assert sorted(route.stop_order) == [0, 1]  # on a line both orders cost the same
    assert [(stop.index, stop.reason) for stop in route.dropped] == [(2, DropReason.UNREACHABLE_FOR_PROFILE)]
    assert route.nodes == (0, 1, 2, 3, 2, 1, 0) and route.total_cost == 6.0
    assert_continuous(route)


def test_car_reaches_every_stop():
    route = plan_route(CLIFF_GRAPH, make_query(profile="car"))
    assert sorted(route.stop_order) == [0, 1, 2] and route.dropped == ()
    assert route.total_cost == 3.0 + 5.0 + 4.0
    assert_continuous(route)


def test_isolated_fixed_end_raises():
    with pytest.raises(NoFeasibleRoute):
        plan_route(CLIFF_GRAPH, make_query(destinations=(2,), end_mode=EndMode.FIXED, end_node=5))
