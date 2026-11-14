"""Entry point of the routing engine: query -> cost matrix -> solver -> assembled route."""

from __future__ import annotations

from typing import Mapping

from app.routing.assemble import assemble
from app.routing.contracts import RoutePlan, RouteQuery
from app.routing.graph import RoutingGraph
from app.routing.matrix import build_cost_matrix
from app.routing.solver import solve


def plan_route(
    routing_graph: RoutingGraph,
    query: RouteQuery,
    capacities: Mapping[str, float] | None = None,
    reserve_margin: float = 0.0,
) -> RoutePlan:
    """Raises solver.NoFeasibleRoute when no route exists at all (e.g. unreachable fixed end)."""
    cost_matrix = build_cost_matrix(routing_graph, query.profile, query.point_nodes)
    solution = solve(cost_matrix, query.end_mode, query.time_limit_s)
    return assemble(
        routing_graph, query, cost_matrix, solution, capacities, reserve_margin
    )
