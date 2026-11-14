"""Step 5: stop order (OR-Tools). Spec: SKILL.md section 10.

Works on point indices (CostMatrix order: 0 = start, 1..D = destinations, D+1 = fixed end) and
returns destination indices (0-based into the request's destinations).
"""

from __future__ import annotations

import numpy as np
from app.routing.contracts import (
    CostMatrix,
    DroppedStop,
    DropReason,
    EndMode,
    SolverResult,
)
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

# TODO: move to a shared constants module (e.g. app/core/constants.py).
BIG = (
    10**12
)  # stands in for inf; (N + 1) * BIG plus all penalties stays far below int64 max
DEFAULT_SCALE = 1000.0


class NoFeasibleRoute(Exception):
    """No route exists at all, e.g. the start cannot reach a fixed end."""


def integer_costs(
    matrix: np.ndarray, scale: float = DEFAULT_SCALE
) -> tuple[list[list[int]], int]:
    """Scaled integer matrix (inf -> BIG) and the drop penalty.

    PENALTY = N * max finite scaled cell + 1 is above any real route cost (a route uses at most
    N arcs) and must stay below BIG; the scale is lowered until it does.
    """
    finite = np.isfinite(matrix)
    n_points = matrix.shape[0]
    max_cell = float(matrix[finite].max()) if finite.any() else 0.0
    while (penalty := n_points * round(max_cell * scale) + 1) >= BIG:
        scale /= 10.0
    scaled = np.where(finite, np.rint(matrix * scale), BIG).astype(np.int64)
    return scaled.tolist(), penalty


def drop_reason(
    cost_matrix: CostMatrix, point: int, end_point: int | None
) -> DropReason:
    """Exact because reachability in a shortest-path matrix is transitive.

    end_point: the start for a round trip, the end for a fixed end, None for an open end.
    """
    if not cost_matrix.reachable(0, point) or (
        end_point is not None and not cost_matrix.reachable(point, end_point)
    ):
        return DropReason.UNREACHABLE_FOR_PROFILE
    return DropReason.NOT_SCHEDULED


def solve(
    cost_matrix: CostMatrix,
    end_mode: EndMode,
    time_limit_s: float,
    scale: float = DEFAULT_SCALE,
) -> SolverResult:
    n_points = len(cost_matrix.nodes)
    costs, penalty = integer_costs(cost_matrix.matrix, scale)
    if end_mode == EndMode.ROUND_TRIP:
        destination_points = range(1, n_points)
        end_point = 0
        manager = pywrapcp.RoutingIndexManager(n_points, 1, 0)
    elif end_mode == EndMode.FIXED:
        destination_points = range(1, n_points - 1)
        end_point = n_points - 1
        manager = pywrapcp.RoutingIndexManager(n_points, 1, [0], [n_points - 1])
    else:  # open: dummy end node reachable from everywhere at zero cost, never shown
        destination_points = range(1, n_points)
        end_point = None
        for row in costs:
            row.append(0)
        costs.append([BIG] * n_points + [0])
        manager = pywrapcp.RoutingIndexManager(n_points + 1, 1, [0], [n_points])

    routing = pywrapcp.RoutingModel(manager)

    def arc_cost(from_index: int, to_index: int) -> int:
        return costs[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(arc_cost))
    for point in destination_points:
        routing.AddDisjunction([manager.NodeToIndex(point)], penalty)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromMilliseconds(
        max(1, round(time_limit_s * 1000))
    )  # GLS never stops by itself

    solution = routing.SolveWithParameters(params)
    if solution is None:
        raise NoFeasibleRoute("the solver found no route")

    visited: list[int] = []
    index = routing.Start(0)
    while True:
        visited.append(manager.IndexToNode(index))
        if routing.IsEnd(index):
            break
        index = solution.Value(routing.NextVar(index))
    if any(
        costs[from_point][to_point] >= BIG
        for from_point, to_point in zip(visited, visited[1:])
    ):
        raise NoFeasibleRoute(
            "no route exists for this profile between the start and the end"
        )

    destination_set = set(destination_points)
    order = tuple(point - 1 for point in visited if point in destination_set)
    dropped = tuple(
        DroppedStop(index=point - 1, reason=drop_reason(cost_matrix, point, end_point))
        for point in destination_points
        if solution.Value(routing.NextVar(manager.NodeToIndex(point)))
        == manager.NodeToIndex(point)
    )
    return SolverResult(order=order, dropped=dropped)
