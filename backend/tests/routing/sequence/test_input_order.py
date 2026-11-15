import numpy as np
import pytest

from app.routing.contracts import CostMatrix, DropReason, EndMode
from app.routing.sequence import in_input_order
from app.routing.solver import NoFeasibleRoute

INF = np.inf


def matrix(rows):
    m = np.array(rows, dtype=float)
    return CostMatrix(nodes=tuple(range(len(rows))), matrix=m, legs={})


def test_destinations_are_visited_in_the_order_given_even_when_another_order_is_cheaper():
    # start, d0, d1: going to d1 first would be cheaper, but the user asked for d0 first
    cm = matrix([[0, 9, 1], [9, 0, 9], [1, 9, 0]])
    result = in_input_order(cm, EndMode.ROUND_TRIP, "car")
    assert result.order == (0, 1) and result.dropped == ()


def test_a_stop_that_cannot_be_reached_from_the_previous_one_is_skipped_and_the_rest_still_visited():
    cm = matrix([[0, INF, 1], [INF, 0, INF], [1, INF, 0]])  # d0 unreachable, d1 fine
    result = in_input_order(cm, EndMode.ROUND_TRIP, "astronaut")
    assert result.order == (1,)
    assert [(d.index, d.reason) for d in result.dropped] == [(0, DropReason.UNREACHABLE_FOR_PROFILE)]


def test_a_stop_with_no_way_back_to_the_end_is_skipped():
    cm = matrix([[0, 1, 1], [INF, 0, INF], [1, 1, 0]])  # d0 reachable but a dead end (cannot return)
    assert in_input_order(cm, EndMode.ROUND_TRIP, "car").order == (1,)


def test_open_end_needs_no_way_back():
    cm = matrix([[0, 1], [INF, 0]])
    assert in_input_order(cm, EndMode.OPEN, "car").order == (0,)


def test_fixed_end_that_cannot_be_reached_raises_naming_the_profile():
    cm = matrix([[0, INF], [INF, 0]])  # start -> end only, unreachable
    with pytest.raises(NoFeasibleRoute, match="astronaut"):
        in_input_order(cm, EndMode.FIXED, "astronaut")


def test_point_to_point_has_no_stops():
    cm = matrix([[0, 5], [5, 0]])
    result = in_input_order(cm, EndMode.FIXED, "car")
    assert result.order == () and result.dropped == ()
