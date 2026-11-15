import math

import numpy as np
import pytest

from app.core.resources import RESOURCES, ProfileId
from app.routing.graph import SnapError
from tests.routing.helpers import INF, both, make_graph, resource_factor


@pytest.fixture
def routing_graph():
    return make_graph(4, [*both(0, 1, 2.0, back=5.0), (1, 2, INF), (2, 3, 1.0)])


def test_structure_and_edge_ids_index_the_arrays(routing_graph):
    assert routing_graph.n_nodes == 4 and routing_graph.n_edges == 4
    edge_ids = [routing_graph.edge_id(0, 1), routing_graph.edge_id(1, 0),
                routing_graph.edge_id(1, 2), routing_graph.edge_id(2, 3)]
    assert edge_ids == [0, 1, 2, 3]
    assert isinstance(routing_graph.cost[ProfileId.ASTRONAUT], np.ndarray)  # arrays, not Python lists


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


def test_edge_ids_along_a_path_and_missing_edges(routing_graph):
    assert routing_graph.edge_ids((0, 1, 0)).tolist() == [0, 1]
    assert routing_graph.edge_ids((3,)).size == 0
    with pytest.raises(KeyError, match="no edge 0 -> 3"):
        routing_graph.edge_ids((0, 3))


def test_inf_edges_are_not_in_the_search_matrix(routing_graph):
    csr = routing_graph.csr("astronaut")
    assert csr.nnz == 3 and csr[1, 2] == 0 and csr[0, 1] == 2.0  # (1, 2) is inf, so it is absent


def test_shortest_paths_and_trace(routing_graph):
    dist, pred = routing_graph.shortest_paths("astronaut", [0])
    assert dist[0, 1] == 2.0 and np.isinf(dist[0, 2]) and np.isinf(dist[0, 3])
    assert routing_graph.trace_path(pred[0], 0, 1) == (0, 1)
    with pytest.raises(ValueError, match="not reachable"):
        routing_graph.trace_path(pred[0], 0, 3)


def test_parallel_edges_are_rejected():
    with pytest.raises(ValueError, match="parallel"):
        make_graph(2, [(0, 1, 1.0), (0, 1, 2.0)])


def test_snap_returns_the_nearest_valid_node_and_rejects_outside(routing_graph):
    s = routing_graph.snap(float(routing_graph.lon[2]), float(routing_graph.lat[2]))
    assert s.node == 2 and s.distance_m == pytest.approx(0.0, abs=1e-6)
    with pytest.raises(SnapError, match="outside"):
        routing_graph.snap(0.0, 0.0)
