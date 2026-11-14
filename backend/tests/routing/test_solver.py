import numpy as np
import pytest

from app.routing.contracts import CostMatrix, DropReason, DroppedStop, EndMode
from app.routing.solver import BIG, NoFeasibleRoute, drop_reason, integer_costs, solve

INF = np.inf
TIME_LIMIT_S = 1.0


def make_cost_matrix(rows):
    matrix = np.array(rows, dtype=float)
    return CostMatrix(nodes=tuple(range(100, 100 + len(matrix))), matrix=matrix, legs={})


def line_matrix(positions):
    """Points on a line; cost = distance."""
    return make_cost_matrix([[abs(from_x - to_x) for to_x in positions] for from_x in positions])


def test_integer_costs_replace_inf_and_keep_penalty_between_real_costs_and_big():
    costs, penalty = integer_costs(np.array([[0, 1.5, INF], [2.25, 0, 3.0], [INF, 1.0, 0]]))
    assert costs == [[0, 1500, BIG], [2250, 0, 3000], [BIG, 1000, 0]]
    assert penalty == 3 * 3000 + 1 < BIG


def test_integer_costs_lower_the_scale_when_the_penalty_would_reach_big():
    costs, penalty = integer_costs(np.array([[0, 1e10], [1e10, 0]]))
    assert penalty < BIG and costs[0][1] < BIG


def test_round_trip_finds_the_cheap_direction():
    # start -> A -> B -> start costs 3; the reverse costs 15
    result = solve(make_cost_matrix([[0, 1, 5], [5, 0, 1], [1, 5, 0]]), EndMode.ROUND_TRIP, TIME_LIMIT_S)
    assert result.order == (0, 1) and result.dropped == ()


def test_open_end_visits_in_line_order():
    result = solve(line_matrix([0, 3, 1, 2]), EndMode.OPEN, TIME_LIMIT_S)  # start, then dests at 3, 1, 2
    assert result.order == (1, 2, 0)


def test_fixed_end_is_last_and_never_in_order():
    result = solve(line_matrix([0, 2, 1, 3]), EndMode.FIXED, TIME_LIMIT_S)  # start, dest, dest, end
    assert result.order == (1, 0)


def test_destination_unreachable_from_start_is_dropped():
    result = solve(make_cost_matrix([[0, 1, INF], [1, 0, INF], [1, 1, 0]]), EndMode.ROUND_TRIP, TIME_LIMIT_S)
    assert result.order == (0,)
    assert result.dropped == (DroppedStop(index=1, reason=DropReason.UNREACHABLE_FOR_PROFILE),)


def test_destination_without_a_way_back_dropped_on_round_trip_but_visited_on_open_end():
    rows = [[0, 1, 2], [1, 0, 1], [INF, INF, 0]]  # dest 1 is a dead end
    round_trip = solve(make_cost_matrix(rows), EndMode.ROUND_TRIP, TIME_LIMIT_S)
    assert round_trip.order == (0,) and [stop.index for stop in round_trip.dropped] == [1]
    assert solve(make_cost_matrix(rows), EndMode.OPEN, TIME_LIMIT_S).order == (0, 1)


def test_all_destinations_unreachable_gives_an_empty_order():
    rows = [[0, INF, INF], [INF, 0, 1], [INF, 1, 0]]
    result = solve(make_cost_matrix(rows), EndMode.ROUND_TRIP, TIME_LIMIT_S)
    assert result.order == ()
    assert {stop.index for stop in result.dropped} == {0, 1}


def test_unreachable_fixed_end_raises():
    with pytest.raises(NoFeasibleRoute):
        solve(make_cost_matrix([[0, 1, INF], [1, 0, INF], [INF, INF, 0]]), EndMode.FIXED, TIME_LIMIT_S)


def test_drop_reason_rules():
    cost_matrix = make_cost_matrix([[0, 1, INF], [1, 0, INF], [1, INF, 0]])
    assert drop_reason(cost_matrix, 1, end_point=0) == DropReason.NOT_SCHEDULED
    assert drop_reason(cost_matrix, 2, end_point=None) == DropReason.UNREACHABLE_FOR_PROFILE
    dead_end = make_cost_matrix([[0, 1, 1], [1, 0, 1], [INF, INF, 0]])
    assert drop_reason(dead_end, 2, end_point=0) == DropReason.UNREACHABLE_FOR_PROFILE  # no way back
    assert drop_reason(dead_end, 2, end_point=None) == DropReason.NOT_SCHEDULED  # open end: no return needed

