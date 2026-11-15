import numpy as np
import pytest

from app.graph.contracts import GraphData
from app.graph.loader import build_routing_context
from app.routing.snap import SnapError, snap
from tests.routing.helpers import INF, both, make_graph_data

DATA = make_graph_data(4, [*both(0, 1, 1.0), *both(1, 2, 1.0), *both(2, 3, 1.0)])


def ctx(valid=(True, True, True, True)):
    node = {**DATA.node, "valid": np.array(valid)}
    return build_routing_context(GraphData(DATA.grid, node, DATA.src, DATA.dst, DATA.edge_arrays, "test"))


def test_snaps_to_nearest_node():
    c = ctx()
    s = snap(c, float(c.graph.lon[2]) + 0.001, float(c.graph.lat[2]), "start", 1000)
    assert s.node == 2 and 0 < s.distance_m < 100
    assert (s.lon, s.lat) == (c.graph.lon[2], c.graph.lat[2])


def test_invalid_nodes_are_never_chosen():
    c = ctx(valid=(True, False, True, True))
    s = snap(c, float(c.graph.lon[1]), float(c.graph.lat[1]), "start", 100_000)
    assert s.node != 1


def test_outside_and_too_far_raise():
    c = ctx()
    with pytest.raises(SnapError, match="outside the routing area"):
        snap(c, 0.0, 0.0, "start", 1000)
    with pytest.raises(SnapError, match="maximum 5 m"):
        snap(c, float(c.graph.lon[0]) + 0.001, float(c.graph.lat[0]), "end", 5)


def test_graph_without_valid_nodes_is_unavailable():
    from app.layers.base import LayerUnavailable
    with pytest.raises(LayerUnavailable):
        ctx(valid=(False,) * 4)


# Node 2 has no usable outgoing edge for the car (e.g. a dune cell): the car must snap past it.
CAR_DATA = make_graph_data(4, [*both(0, 1, 1.0), *both(1, 2, 1.0), *both(2, 3, 1.0)],
                           car_edges={(2, 1): INF, (2, 3): INF})


def test_each_profile_snaps_to_a_node_it_can_leave():
    c = build_routing_context(CAR_DATA)
    lon, lat = float(c.graph.lon[2]) + 0.01, float(c.graph.lat[2])  # nudged towards node 3
    assert snap(c, lon, lat, "start", 100_000, "astronaut").node == 2
    assert snap(c, lon, lat, "start", 100_000, "car").node == 3
    with pytest.raises(SnapError, match="passable for the car profile"):
        snap(c, float(c.graph.lon[2]), float(c.graph.lat[2]), "start", 10, "car")


def test_a_profile_with_no_passable_node_cannot_snap():
    data = make_graph_data(2, both(0, 1, 1.0), car_edges={(0, 1): INF, (1, 0): INF})
    c = build_routing_context(data)
    with pytest.raises(SnapError, match="No part of the routing area is passable for the car"):
        snap(c, float(c.graph.lon[0]), float(c.graph.lat[0]), "start", 100_000, "car")
