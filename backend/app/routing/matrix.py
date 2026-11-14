"""Step 4: cost matrix between all route points (rustworkx). Spec: SKILL.md section 10."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
import rustworkx as rx
from app.core.resources import ProfileId
from app.routing.contracts import CostMatrix
from app.routing.graph import RoutingGraph


def build_cost_matrix(
    routing_graph: RoutingGraph, profile: ProfileId | str, point_nodes: Sequence[int]
) -> CostMatrix:
    """One Dijkstra per point over the profile's `cost`.

    A target missing from the result (not connected) or reached only over inf edges stays
    unreachable: the cell is inf and no leg path is saved.
    """
    edge_costs = routing_graph.cost[ProfileId(profile)]
    n_points = len(point_nodes)
    matrix = np.full((n_points, n_points), np.inf)
    np.fill_diagonal(matrix, 0.0)
    legs: dict[tuple[int, int], tuple[int, ...]] = {}
    for from_point, source in enumerate(point_nodes):
        paths = rx.dijkstra_shortest_paths(
            routing_graph.graph, source, weight_fn=edge_costs.__getitem__
        )
        for to_point, target in enumerate(point_nodes):
            if from_point == to_point or target not in paths:
                continue
            path = tuple(paths[target])
            cost = routing_graph.path_cost(profile, path)
            if math.isfinite(cost):
                matrix[from_point, to_point] = cost
                legs[(from_point, to_point)] = path
    return CostMatrix(nodes=tuple(point_nodes), matrix=matrix, legs=legs)
