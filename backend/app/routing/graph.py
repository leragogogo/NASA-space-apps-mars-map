"""In-memory routing graph: flat NumPy arrays plus a SciPy CSR matrix per profile.

Built once from GraphData at startup and read-only afterwards, so it is safe to share across requests.
Nothing is stored per edge as a Python object: topology (`src`, `dst`), costs and resources are arrays
indexed by edge id, so the 200 m graph (1.29 M nodes, 10.3 M edges) stays at a few hundred MB.
Shortest paths run in SciPy's compiled Dijkstra (`scipy.sparse.csgraph`), with no Python callback per edge.
Spec: SKILL.md section 10, step 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import dijkstra

from app.core.resources import PROFILES, RESOURCES, ProfileId
from app.graph.contracts import GraphData
from app.layers.contracts import GridSpec

NO_PREDECESSOR = -9999  # what scipy stores for "no predecessor"


@dataclass(frozen=True, eq=False)
class RoutingGraph:
    grid: GridSpec
    src: np.ndarray  # int32 (n_edges,)
    dst: np.ndarray
    cost: Mapping[ProfileId, np.ndarray]  # per profile: float64, indexed by edge id; inf = impassable
    resources: Mapping[ProfileId, Mapping[str, np.ndarray]]  # per profile and resource, by edge id
    lon: np.ndarray  # per node id
    lat: np.ndarray
    valid: np.ndarray  # per node id: has elevation data
    _edge_keys: np.ndarray  # sorted src * n_nodes + dst
    _edge_order: np.ndarray  # edge id of each sorted key
    _cache: dict = field(default_factory=dict)  # lazily built CSR matrices

    @classmethod
    def from_graph_data(cls, data: GraphData) -> "RoutingGraph":
        n = data.grid.n_nodes
        src, dst = np.asarray(data.src, dtype=np.int32), np.asarray(data.dst, dtype=np.int32)
        keys = src.astype(np.int64) * n + dst
        order = np.argsort(keys, kind="stable")
        sorted_keys = keys[order]
        if sorted_keys.size > 1 and (np.diff(sorted_keys) == 0).any():
            raise ValueError("the graph has parallel edges (the same source and destination twice)")
        valid = np.asarray(data.node.get("valid", np.ones(n, dtype=bool)), dtype=bool)
        return cls(
            grid=data.grid, src=src, dst=dst,
            cost={p: np.asarray(data.cost(p), dtype=np.float64) for p in PROFILES},
            resources={p: {r: data.array(p, r) for r in RESOURCES} for p in PROFILES},
            lon=np.asarray(data.node["lon"]), lat=np.asarray(data.node["lat"]), valid=valid,
            _edge_keys=sorted_keys, _edge_order=order.astype(np.int32))

    # ------------------------------------------------------------------ size
    @property
    def n_nodes(self) -> int:
        return self.grid.n_nodes

    @property
    def n_edges(self) -> int:
        return int(self.src.shape[0])

    # ------------------------------------------------------------------ edges
    def edge_ids(self, nodes: Sequence[int]) -> np.ndarray:
        """Edge ids along a node path (int64 array; empty for a path of fewer than two nodes)."""
        nodes = np.asarray(nodes, dtype=np.int64)
        if nodes.size < 2:
            return np.empty(0, dtype=np.int64)
        keys = nodes[:-1] * self.n_nodes + nodes[1:]
        pos = np.minimum(np.searchsorted(self._edge_keys, keys), self._edge_keys.size - 1)
        missing = self._edge_keys[pos] != keys
        if missing.any():
            k = int(np.flatnonzero(missing)[0])
            raise KeyError(f"no edge {int(nodes[k])} -> {int(nodes[k + 1])}")
        return self._edge_order[pos].astype(np.int64)

    def edge_id(self, from_node: int, to_node: int) -> int:
        return int(self.edge_ids((from_node, to_node))[0])

    def path_cost(self, profile: ProfileId | str, nodes: Sequence[int]) -> float:
        return float(self.cost[ProfileId(profile)][self.edge_ids(nodes)].sum())

    def path_resources(self, profile: ProfileId | str, nodes: Sequence[int]) -> dict[str, float]:
        ids = self.edge_ids(nodes)
        arrays = self.resources[ProfileId(profile)]
        return {r: float(arrays[r][ids].astype(np.float64).sum()) for r in RESOURCES}

    def coords(self, nodes: Sequence[int]) -> list[list[float]]:
        """[lon, lat] of every node, e.g. for a GeoJSON LineString."""
        node_ids = np.asarray(nodes, dtype=np.int64)
        return np.column_stack([self.lon[node_ids], self.lat[node_ids]]).astype(np.float64).tolist()

    # ------------------------------------------------------------------ shortest paths
    def csr(self, profile: ProfileId | str) -> sparse.csr_matrix:
        """Adjacency matrix of one profile: entry (u, v) = cost. Impassable (inf) edges are left out."""
        profile = ProfileId(profile)
        key = ("csr", profile)
        if key not in self._cache:
            c = self.cost[profile]
            ok = np.isfinite(c)
            self._cache[key] = sparse.csr_matrix((c[ok], (self.src[ok], self.dst[ok])),
                                                 shape=(self.n_nodes, self.n_nodes))
        return self._cache[key]

    def shortest_paths(self, profile: ProfileId | str, sources: Sequence[int]):
        """Dijkstra from each source over `cost`: (distance, predecessor), each shaped (len(sources), n_nodes).

        Unreachable nodes have distance inf. Trace a path with `trace_path`.
        """
        return dijkstra(self.csr(profile), directed=True, indices=np.asarray(sources, dtype=np.int64),
                        return_predecessors=True)

    @staticmethod
    def trace_path(predecessors: np.ndarray, source: int, target: int) -> tuple[int, ...]:
        """Node path source -> target from one row of `shortest_paths` predecessors."""
        path = [int(target)]
        node = int(target)
        while node != source:
            node = int(predecessors[node])
            if node == NO_PREDECESSOR or len(path) > predecessors.shape[0]:
                raise ValueError(f"node {target} is not reachable from {source}")
            path.append(node)
        return tuple(reversed(path))
