"""Step 7: load graph.npz into the in-memory `RoutingGraph` that routing consumes (NumPy arrays + SciPy CSR).

The graph is read-only after loading, so it is safe to share across requests.
"""
from __future__ import annotations

from pathlib import Path

from app.graph.contracts import GraphData
from app.routing.graph import RoutingGraph, SnapError, SnapResult  # noqa: F401  (re-exported for callers)

BUILD_HINT = "run `python -m app.graph` to build it"


class GraphNotBuiltError(FileNotFoundError):
    """graph.npz does not exist (the app does not build it silently)."""


def load_routing_graph(path: str | Path) -> RoutingGraph:
    path = Path(path)
    if not path.is_file():
        raise GraphNotBuiltError(f"graph file not found at {path}; {BUILD_HINT}")
    data = GraphData.load(path)
    data.validate()
    return RoutingGraph.from_graph_data(data)
