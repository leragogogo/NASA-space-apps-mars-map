import numpy as np
import pytest

from app.core.resources import ProfileId
from app.routing.contracts import DEFAULT_TIME_LIMIT_S, CostMatrix, EndMode, RouteLimits, RouteQuery


def q(**kw):
    base = dict(profile=ProfileId.ASTRONAUT, start_node=0, destination_nodes=(1, 2))
    return RouteQuery(**{**base, **kw})


def test_route_query_point_nodes_by_end_mode():
    assert q().point_nodes == (0, 1, 2)
    assert q(end_mode=EndMode.FIXED, end_node=9).point_nodes == (0, 1, 2, 9)
    assert q(end_mode=EndMode.OPEN).point_nodes == (0, 1, 2)


@pytest.mark.parametrize("kw", [
    dict(destination_nodes=()),
    dict(end_mode=EndMode.FIXED),                       # fixed needs an end
    dict(end_mode=EndMode.OPEN, end_node=5),            # end only allowed for fixed
    dict(destination_nodes=(1, 1)),                     # duplicate snapped destinations
    dict(destination_nodes=(0, 2)),                     # destination snapped onto the start
    dict(end_mode=EndMode.FIXED, end_node=2),           # end snapped onto a destination
])
def test_route_query_rejects_invalid(kw):
    with pytest.raises(ValueError):
        q(**kw)


def test_cost_matrix_validation_and_reachability():
    m = np.array([[0, 5.0, np.inf], [7.0, 0, 1.0], [2.0, 3.0, 0]])
    cm = CostMatrix(nodes=(10, 11, 12), matrix=m, legs={(0, 1): (10, 11)})
    assert cm.reachable(0, 1) and not cm.reachable(0, 2)
    assert cm.matrix[0, 1] != cm.matrix[1, 0]  # not symmetric
    with pytest.raises(ValueError, match="shape"):
        CostMatrix(nodes=(1, 2), matrix=np.zeros((3, 3)), legs={})
    with pytest.raises(ValueError, match="diagonal"):
        CostMatrix(nodes=(1, 2), matrix=np.array([[1.0, 2.0], [2.0, 0.0]]), legs={})
    with pytest.raises(ValueError, match="NaN or negative"):
        CostMatrix(nodes=(1, 2), matrix=np.array([[0.0, np.nan], [2.0, 0.0]]), legs={})


def test_time_limit_clamp():
    lim = RouteLimits()
    assert lim.clamp_time_limit(None) == DEFAULT_TIME_LIMIT_S == 10.0
    assert lim.clamp_time_limit(0.1) == 1.0
    assert lim.clamp_time_limit(999) == 30.0


def test_no_destinations_needs_a_fixed_end():
    with pytest.raises(ValueError, match="at least one destination is required"):
        RouteQuery(profile="car", start_node=0, destination_nodes=())
    q = RouteQuery(profile="car", start_node=0, destination_nodes=(), end_mode=EndMode.FIXED, end_node=1)
    assert q.point_nodes == (0, 1)
