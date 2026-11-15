import asyncio
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI

import dataclasses

from app.core.resources import RESOURCES, ProfileId
from app.graph.build import build_graph
from app.graph.lifespan import get_routing_graph, routing_graph_lifespan
from app.graph.loader import GraphNotBuiltError, SnapError, load_routing_graph
from app.routing.graph import RoutingGraph
from app.layers.fakes import fake_grid, fake_inputs
from app.layers.relief.slope import slope_deg
from tests.graph.stubs import stub_models


@pytest.fixture(scope="module")
def mg():
    return RoutingGraph.from_graph_data(build_graph(fake_inputs(fake_grid(8, 10), relief_kind="ramp"), stub_models()))


def test_sizes_costs_and_edge_ids(mg):
    assert mg.n_nodes == mg.grid.n_nodes and mg.n_edges == len(mg.src)
    for p in (ProfileId.ASTRONAUT, ProfileId.CAR):
        assert mg.cost[p].shape == (mg.n_edges,)
    u, v = int(mg.src[5]), int(mg.dst[5])
    assert mg.edge_id(u, v) == 5


def test_missing_edge_raises_keyerror(mg):
    with pytest.raises(KeyError):
        mg.edge_id(0, mg.n_nodes - 1)  # opposite corners are not neighbours


def test_dijkstra_over_the_loaded_graph_matches_summed_edge_costs(mg):
    start, goal = 0, mg.grid.ncols - 1  # along the top row
    dist, pred = mg.shortest_paths("astronaut", [start])
    nodes = list(mg.trace_path(pred[0], start, goal))
    assert nodes[0] == start and nodes[-1] == goal
    ids = mg.edge_ids(nodes)
    assert dist[0, goal] == pytest.approx(mg.cost[ProfileId.ASTRONAUT][ids].sum())
    assert mg.path_cost("astronaut", nodes) == pytest.approx(dist[0, goal])
    res = mg.path_resources("astronaut", nodes)
    assert set(res) == set(RESOURCES)
    assert res["o2_g"] == pytest.approx(float(mg.resources[ProfileId.ASTRONAUT]["o2_g"][ids].astype(np.float64).sum()))


def test_empty_and_single_node_paths_cost_nothing(mg):
    assert mg.path_cost("car", [3]) == 0.0
    assert mg.path_resources("car", [3]) == {a: 0.0 for a in RESOURCES}


def test_snap_to_node_centre_and_nearby(mg):
    lon, lat = (float(mg.lon[23]), float(mg.lat[23]))
    s = mg.snap(lon, lat)
    assert s.node == 23 and s.distance_m == pytest.approx(0.0, abs=1e-6)
    near = mg.snap(lon + mg.grid.dlon * 0.2, lat)
    assert near.node == 23 and 0 < near.distance_m < 0.2 * 1.01 * mg.grid.metric_spacing()[0].max()


def test_snap_rejects_outside_and_too_far(mg):
    with pytest.raises(SnapError, match="outside"):
        mg.snap(0.0, 0.0)
    lon, lat = (float(mg.lon[23]), float(mg.lat[23]))
    with pytest.raises(SnapError, match="limit"):
        mg.snap(lon + mg.grid.dlon * 0.4, lat, max_distance_m=1.0)


def test_snap_skips_nodata_cells():
    inputs = fake_inputs(fake_grid(8, 10), relief_kind="flat")
    elev, valid = inputs.relief.elev_m.copy(), inputs.relief.valid.copy()
    elev[3, 4], valid[3, 4] = np.nan, False
    relief = dataclasses.replace(inputs.relief, elev_m=elev, valid=valid, slope_deg=slope_deg(elev, inputs.grid))
    mg2 = RoutingGraph.from_graph_data(build_graph(dataclasses.replace(inputs, relief=relief), stub_models()))
    hole = int(inputs.grid.node_id(3, 4))
    lon, lat = inputs.grid.lon_centers()[4], inputs.grid.lat_centers()[3]
    s = mg2.snap(lon, lat)
    assert s.node != hole and mg2.valid[s.node] and s.distance_m > 0


def test_load_from_disk_and_missing_file_hint(tmp_path):
    data = build_graph(fake_inputs(fake_grid(6, 8)), stub_models())
    path = tmp_path / "graph.npz"
    data.save(path)
    assert load_routing_graph(path).n_edges == data.n_edges
    with pytest.raises(GraphNotBuiltError, match="python -m app.graph"):
        load_routing_graph(tmp_path / "missing.npz")


def test_lifespan_loads_and_dependency_reads_it(tmp_path):
    data = build_graph(fake_inputs(fake_grid(6, 8)), stub_models())
    path = tmp_path / "graph.npz"
    data.save(path)
    app = FastAPI()

    async def run():
        async with routing_graph_lifespan(app, path):
            assert get_routing_graph(SimpleNamespace(app=app)).n_edges == data.n_edges
        assert app.state.routing_graph is None

    asyncio.run(run())
    with pytest.raises(RuntimeError, match="not loaded"):
        get_routing_graph(SimpleNamespace(app=app))


def test_lifespan_fails_clearly_when_graph_is_missing(tmp_path):
    async def run():
        async with routing_graph_lifespan(FastAPI(), tmp_path / "nope.npz"):
            pass

    with pytest.raises(GraphNotBuiltError):
        asyncio.run(run())
