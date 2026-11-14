import math

import numpy as np

from app.routing.matrix import build_cost_matrix
from tests.routing.helpers import INF, both, make_graph


def test_asymmetric_costs_shortest_paths_and_zero_diagonal():
    # uphill 0 -> 1 -> 2 costs more than downhill; 0 -> 2 has a direct but expensive edge
    routing_graph = make_graph(3, [*both(0, 1, 3.0, back=1.0), *both(1, 2, 3.0, back=1.0), (0, 2, 10.0)])
    cost_matrix = build_cost_matrix(routing_graph, "astronaut", (0, 1, 2))
    np.testing.assert_array_equal(np.diag(cost_matrix.matrix), 0.0)
    assert cost_matrix.matrix[0, 2] == 6.0 and cost_matrix.matrix[2, 0] == 2.0
    assert cost_matrix.legs[(0, 2)] == (0, 1, 2) and cost_matrix.legs[(2, 0)] == (2, 1, 0)
    assert cost_matrix.matrix[0, 1] != cost_matrix.matrix[1, 0]


def test_target_reachable_only_over_inf_edges_is_unreachable():
    routing_graph = make_graph(3, [*both(0, 1, 1.0), (1, 2, INF), (2, 1, 1.0)])
    cost_matrix = build_cost_matrix(routing_graph, "astronaut", (0, 2))
    assert math.isinf(cost_matrix.matrix[0, 1]) and (0, 1) not in cost_matrix.legs
    assert cost_matrix.matrix[1, 0] == 2.0 and cost_matrix.legs[(1, 0)] == (2, 1, 0)


def test_isolated_target_is_unreachable_both_ways():
    routing_graph = make_graph(3, both(0, 1, 1.0))
    cost_matrix = build_cost_matrix(routing_graph, "astronaut", (0, 1, 2))
    assert math.isinf(cost_matrix.matrix[0, 2]) and math.isinf(cost_matrix.matrix[2, 0])
    assert set(cost_matrix.legs) == {(0, 1), (1, 0)}


def test_uses_only_the_chosen_profile():
    routing_graph = make_graph(2, both(0, 1, INF), car_edges={(0, 1): 4.0, (1, 0): 4.0})
    assert not build_cost_matrix(routing_graph, "astronaut", (0, 1)).reachable(0, 1)
    assert build_cost_matrix(routing_graph, "car", (0, 1)).matrix[0, 1] == 4.0
