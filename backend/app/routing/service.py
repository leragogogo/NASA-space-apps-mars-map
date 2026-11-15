"""Entry point of the routing engine: query -> cost matrix -> stops in input order -> assembled route."""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

from app.routing.assemble import assemble
from app.routing.contracts import RoutePlan, RouteQuery
from app.routing.graph import RoutingGraph
from app.routing.matrix import build_cost_matrix
from app.routing.sequence import in_input_order


def plan_route(
    routing_graph: RoutingGraph,
    query: RouteQuery,
    capacities: Mapping[str, float] | None = None,
    reserve_margin: float = 0.0,
    path_resources: Callable[[object, Sequence[int]], Mapping[str, float]] | None = None,
) -> RoutePlan:
    """Raises solver.NoFeasibleRoute when no route exists at all (e.g. unreachable fixed end)."""
    cost_matrix = build_cost_matrix(routing_graph, query.profile, query.point_nodes)
    # Destinations are visited in the order the user gave them (no reordering).
    solution = in_input_order(cost_matrix, query.end_mode, query.profile)
    return assemble(
        routing_graph, query, cost_matrix, solution, capacities, reserve_margin, path_resources
    )
