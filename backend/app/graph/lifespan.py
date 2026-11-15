"""FastAPI wiring for the routing graph: load once at startup, expose through a dependency.

Not yet attached in main.py: with the lifespan attached, the app fails to start until
`python -m app.graph` has produced graph.npz (by design: no silent builds). Attach it when the
route endpoint lands:

    app = FastAPI(lifespan=routing_graph_lifespan)
    @router.post("/api/route")
    def route(req: RouteRequest, rg: RoutingGraph = Depends(get_routing_graph)): ...
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.graph.loader import load_routing_graph
from app.graph.store import DEFAULT_GRAPH_PATH
from app.routing.graph import RoutingGraph


@asynccontextmanager
async def routing_graph_lifespan(app: FastAPI, path=DEFAULT_GRAPH_PATH):
    app.state.routing_graph = load_routing_graph(path)  # raises GraphNotBuiltError with a clear hint
    try:
        yield
    finally:
        app.state.routing_graph = None


def get_routing_graph(request: Request) -> RoutingGraph:
    rg = getattr(request.app.state, "routing_graph", None)
    if rg is None:
        raise RuntimeError("routing graph is not loaded (is routing_graph_lifespan attached?)")
    return rg
