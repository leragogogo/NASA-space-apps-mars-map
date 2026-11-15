"""Step 4: cost matrix between all route points (SciPy Dijkstra on arrays). Spec: SKILL.md section 10."""

from __future__ import annotations

from typing import Sequence

import numpy as np
from app.core.resources import ProfileId
from app.routing.contracts import CostMatrix
from app.routing.graph import RoutingGraph

CHUNK = 8  # sources per Dijkstra call: bounds the (sources x nodes) distance and predecessor arrays


def build_cost_matrix(
    routing_graph: RoutingGraph, profile: ProfileId | str, point_nodes: Sequence[int]
) -> CostMatrix:
    """One Dijkstra per point over the profile's `cost`.

    Impassable (inf) edges are not in the search graph, so a target that can only be reached over them
    is unreachable: the cell is inf and no leg path is saved.
    """
    profile = ProfileId(profile)
    n_points = len(point_nodes)
    matrix = np.full((n_points, n_points), np.inf)
    np.fill_diagonal(matrix, 0.0)
    legs: dict[tuple[int, int], tuple[int, ...]] = {}
    for start in range(0, n_points, CHUNK):
        chunk = list(point_nodes[start : start + CHUNK])
        dist, pred = routing_graph.shortest_paths(profile, chunk)
        for k, source in enumerate(chunk):
            from_point = start + k
            for to_point, target in enumerate(point_nodes):
                d = dist[k, target]
                if from_point == to_point or not np.isfinite(d):
                    continue
                matrix[from_point, to_point] = d
                legs[(from_point, to_point)] = routing_graph.trace_path(pred[k], int(source), int(target))
    return CostMatrix(nodes=tuple(point_nodes), matrix=matrix, legs=legs)
