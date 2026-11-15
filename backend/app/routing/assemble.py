"""Step 6: join the solved legs into one route with costs and resources. Spec: SKILL.md section 10."""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

from app.core.resources import RESOURCES, UNITS
from app.routing.contracts import (
    CostMatrix,
    EndMode,
    Leg,
    RoutePlan,
    RouteQuery,
    SolverResult,
)
from app.routing.graph import RoutingGraph


def stop_points(query: RouteQuery, solution: SolverResult) -> list[int]:
    """Visited points in CostMatrix order, including start and end (open end: no end point)."""
    points = [0, *(destination + 1 for destination in solution.order)]
    if query.end_mode == EndMode.ROUND_TRIP:
        points.append(0)
    elif query.end_mode == EndMode.FIXED:
        points.append(len(query.destination_nodes) + 1)
    return points


def budget_warnings(
    totals: Mapping[str, float], capacities: Mapping[str, float], reserve_margin: float
) -> list[str]:
    warnings = []
    for resource, capacity in capacities.items():
        usable = capacity * (1.0 - reserve_margin)
        if totals.get(resource, 0.0) > usable:
            unit = UNITS[resource]
            warnings.append(
                f"Estimated {resource} ({totals[resource]:.1f} {unit}) exceeds the budget of {usable:.1f} {unit} "
                f"({capacity:.1f} {unit} minus a {reserve_margin:.0%} reserve)."
            )
    return warnings


def assemble(
    routing_graph: RoutingGraph,
    query: RouteQuery,
    cost_matrix: CostMatrix,
    solution: SolverResult,
    capacities: Mapping[str, float] | None = None,
    reserve_margin: float = 0.0,
    path_resources: Callable[[object, Sequence[int]], Mapping[str, float]] | None = None,
) -> RoutePlan:
    """Budgets are only checked, not enforced (capacities: resource name -> capacity).

    `path_resources(profile, nodes)` replaces the graph's own resource sums, e.g. to use the requesting
    user's body mass; by default the precomputed per-edge arrays are summed.
    """
    resources_of = path_resources or routing_graph.path_resources
    points = stop_points(query, solution)
    legs: list[Leg] = []
    path = [cost_matrix.nodes[0]]
    for from_point, to_point in zip(points, points[1:]):
        if from_point == to_point:  # round trip that visits nothing
            continue
        nodes = cost_matrix.legs.get((from_point, to_point))
        if nodes is None:
            raise ValueError(
                f"solver chose leg {from_point}->{to_point}, which has no saved path (unreachable)"
            )
        legs.append(
            Leg(
                from_point=from_point,
                to_point=to_point,
                nodes=nodes,
                cost=float(cost_matrix.matrix[from_point, to_point]),
                resources=dict(resources_of(query.profile, nodes)),
            )
        )
        path.extend(nodes[1:])  # each leg starts where the previous one ended

    totals = {
        resource: sum(leg.resources[resource] for leg in legs) for resource in RESOURCES
    }
    return RoutePlan(
        profile=query.profile,
        nodes=tuple(path),
        stop_order=solution.order,
        legs=tuple(legs),
        total_cost=sum(leg.cost for leg in legs),
        resources=totals,
        dropped=solution.dropped,
        warnings=tuple(budget_warnings(totals, capacities or {}, reserve_margin)),
    )
