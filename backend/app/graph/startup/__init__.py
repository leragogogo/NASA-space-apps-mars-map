"""Build the routing graph when the API starts, so a deployment needs no manual `python -m app.graph`."""
from app.graph.startup.background import start_background_build
from app.graph.startup.lock import graph_lock
from app.graph.startup.prepare import prepare_routing_context

__all__ = ["graph_lock", "prepare_routing_context", "start_background_build"]
