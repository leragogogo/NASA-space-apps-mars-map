"""Visit the destinations in the order the user entered them (decided with the team 2026-11-15).

Works on point indices (CostMatrix order: 0 = start, 1..D = destinations, D+1 = fixed end) and returns destination
indices (0-based into the request's destinations). A destination is skipped, and reported as dropped, when it cannot
be reached from the previous visited point or when the end (the start for a round trip, the fixed end) cannot be
reached from it; the route then continues from the previous point. An open end needs no way back.
"""
from __future__ import annotations

from app.core.resources import ProfileId
from app.routing.contracts import CostMatrix, DroppedStop, DropReason, EndMode, SolverResult
from app.routing.solver import NoFeasibleRoute


def in_input_order(cost_matrix: CostMatrix, end_mode: EndMode, profile: ProfileId | str) -> SolverResult:
    n_points = len(cost_matrix.nodes)
    if end_mode == EndMode.FIXED:
        destination_points, end_point = range(1, n_points - 1), n_points - 1
    elif end_mode == EndMode.ROUND_TRIP:
        destination_points, end_point = range(1, n_points), 0
    else:  # open: the route ends at the last visited destination
        destination_points, end_point = range(1, n_points), None

    order: list[int] = []
    dropped: list[DroppedStop] = []
    current = 0
    for point in destination_points:
        can_return = end_point is None or cost_matrix.reachable(point, end_point)
        if cost_matrix.reachable(current, point) and can_return:
            order.append(point - 1)
            current = point
        else:
            dropped.append(DroppedStop(index=point - 1, reason=DropReason.UNREACHABLE_FOR_PROFILE))
    if end_point is not None and not cost_matrix.reachable(current, end_point):
        raise NoFeasibleRoute(f"no route exists for the {ProfileId(profile).value} profile "
                              "between the start and the end")
    return SolverResult(order=tuple(order), dropped=tuple(dropped))
