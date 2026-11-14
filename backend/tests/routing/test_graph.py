import math

import pytest

from app.core.resources import RESOURCES, ProfileId
from tests.routing.helpers import INF, both, make_graph, resource_factor


@pytest.fixture
def routing_graph():
    return make_graph(4, [*both(0, 1, 2.0, back=5.0), (1, 2, INF), (2, 3, 1.0)])


def test_structure_and_edge_payload_is_edge_id(routing_graph):
    assert routing_graph.graph.num_nodes() == 4 and routing_graph.graph.num_edges() == 4
    edge_ids = [routing_graph.edge_id(0, 1), routing_graph.edge_id(1, 0),
                routing_graph.edge_id(1, 2), routing_graph.edge_id(2, 3)]
    assert edge_ids == [0, 1, 2, 3]
    assert isinstance(routing_graph.cost[ProfileId.ASTRONAUT], list)


def test_path_cost_is_directional_and_inf_propagates(routing_graph):
    assert routing_graph.path_cost("astronaut", (0, 1)) == 2.0
    assert routing_graph.path_cost("astronaut", (1, 0)) == 5.0
    assert math.isinf(routing_graph.path_cost("astronaut", (0, 1, 2, 3)))
    assert routing_graph.path_cost("astronaut", (2,)) == 0.0


def test_path_resources_sum_every_resource(routing_graph):
    resources = routing_graph.path_resources("car", (1, 0))
    assert set(resources) == set(RESOURCES)
    assert all(resources[resource] == 5.0 * resource_factor(resource) for resource in RESOURCES)
    assert all(value == 0.0 for value in routing_graph.path_resources("car", (3,)).values())


def test_coords_are_lon_lat_in_path_order(routing_graph):
    coords = routing_graph.coords((2, 0))
    assert coords == [[float(routing_graph.lon[2]), float(routing_graph.lat[2])],
                      [float(routing_graph.lon[0]), float(routing_graph.lat[0])]]
    assert coords[0][0] > coords[1][0]  # node 2 lies east of node 0 in the grid row
