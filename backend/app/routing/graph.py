"""In-memory routing graph: the rustworkx PyDiGraph plus per-profile edge arrays.

Built once from GraphData at startup (package F's loader calls `from_graph_data`) and read-only
afterwards, so it is safe to share across requests. The edge payload is the edge id, an index
into every edge array. Spec: SKILL.md section 10, step 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import rustworkx as rx
from app.core.resources import PROFILES, RESOURCES, ProfileId
from app.graph.contracts import GraphData


@dataclass(frozen=True, eq=False)
class RoutingGraph:
    graph: rx.PyDiGraph
    cost: Mapping[
        ProfileId, list[float]
    ]  # per profile, indexed by edge id (a list: fast in weight_fn)
    resources: Mapping[
        ProfileId, Mapping[str, np.ndarray]
    ]  # per profile and resource, by edge id
    lon: np.ndarray  # per node id
    lat: np.ndarray

    @classmethod
    def from_graph_data(cls, data: GraphData) -> "RoutingGraph":
        graph = rx.PyDiGraph(multigraph=False)
        graph.add_nodes_from(range(data.grid.n_nodes))
        graph.add_edges_from(
            list(zip(data.src.tolist(), data.dst.tolist(), range(data.n_edges)))
        )
        cost = {
            profile: data.cost(profile).astype(np.float64).tolist()
            for profile in PROFILES
        }
        resources = {
            profile: {resource: data.array(profile, resource) for resource in RESOURCES}
            for profile in PROFILES
        }
        return cls(
            graph=graph,
            cost=cost,
            resources=resources,
            lon=np.asarray(data.node["lon"]),
            lat=np.asarray(data.node["lat"]),
        )

    def edge_id(self, from_node: int, to_node: int) -> int:
        return self.graph.get_edge_data(from_node, to_node)

    def edge_ids(self, nodes: Sequence[int]) -> list[int]:
        """Edge ids along a node path."""
        return [
            self.edge_id(from_node, to_node)
            for from_node, to_node in zip(nodes, nodes[1:])
        ]

    def path_cost(self, profile: ProfileId | str, nodes: Sequence[int]) -> float:
        edge_costs = self.cost[ProfileId(profile)]
        return float(sum(edge_costs[edge_id] for edge_id in self.edge_ids(nodes)))

    def path_resources(
        self, profile: ProfileId | str, nodes: Sequence[int]
    ) -> dict[str, float]:
        edge_ids = np.asarray(self.edge_ids(nodes), dtype=np.int64)
        resource_arrays = self.resources[ProfileId(profile)]
        return {
            resource: float(
                resource_arrays[resource][edge_ids].astype(np.float64).sum()
            )
            for resource in RESOURCES
        }

    def coords(self, nodes: Sequence[int]) -> list[list[float]]:
        """[lon, lat] of every node, e.g. for a GeoJSON LineString."""
        node_ids = np.asarray(nodes, dtype=np.int64)
        return (
            np.column_stack([self.lon[node_ids], self.lat[node_ids]])
            .astype(np.float64)
            .tolist()
        )
