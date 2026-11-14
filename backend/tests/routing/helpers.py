"""Tiny hand-built routing graphs for the routing tests."""
from __future__ import annotations

import numpy as np

from app.core.resources import PROFILES, RESOURCES, attr_key
from app.graph.contracts import GraphData
from app.layers.fakes import fake_grid
from app.routing.graph import RoutingGraph

INF = float("inf")


def resource_factor(resource: str) -> float:
    """Each resource = edge cost * factor, so expected sums are easy to compute."""
    return float(RESOURCES.index(resource) + 1)


def make_graph(n_nodes: int, edges, car_edges=None) -> RoutingGraph:
    """n_nodes in one grid row; edges: (from_node, to_node, cost).

    car_edges: {(from_node, to_node): car cost}; by default the car cost equals the astronaut cost.
    """
    grid = fake_grid(1, n_nodes)
    lon, lat = grid.node_lonlat()
    node = {"lon": lon, "lat": lat, "elev_m": np.zeros(n_nodes, np.float32), "valid": np.ones(n_nodes, bool)}
    src = np.array([edge[0] for edge in edges], dtype=np.int64)
    dst = np.array([edge[1] for edge in edges], dtype=np.int64)
    costs = {profile: np.array([edge[2] for edge in edges], dtype=np.float64) for profile in PROFILES}
    for endpoints, car_cost in (car_edges or {}).items():
        costs["car"][[i for i, edge in enumerate(edges) if edge[:2] == endpoints]] = car_cost
    edge_arrays = {}
    for profile in PROFILES:
        edge_arrays[attr_key(profile, "cost")] = costs[profile]
        for resource in RESOURCES:
            edge_arrays[attr_key(profile, resource)] = costs[profile] * resource_factor(resource)
    data = GraphData(grid=grid, node=node, src=src, dst=dst, edge_arrays=edge_arrays,
                     formula_version="test")
    data.validate()
    return RoutingGraph.from_graph_data(data)


def both(from_node: int, to_node: int, cost: float, back: float | None = None):
    """Edges from_node -> to_node and back (back defaults to the same cost)."""
    return [(from_node, to_node, cost), (to_node, from_node, cost if back is None else back)]
