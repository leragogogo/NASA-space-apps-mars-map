"""Layer getters -> graph (cost functions and weights) -> routing engine, end to end.

`synthetic` uses the shared fixture data root (a tiny DEM, POI and weather files); `real` uses the
downloaded data and is skipped when data/raw is missing.
"""
from pathlib import Path

import numpy as np
import pytest
import tifffile

from app.core.config import Settings
from app.core.resources import PROFILES, RESOURCES, ProfileId
from app.graph.build import BuildConfig, build_graph
from app.graph.cli import main as graph_cli
from app.graph.contracts import GraphData
from app.graph.getters import graph_inputs_from_registry
from app.graph.nodes import weather_conf_key, weather_risk_key
from app.graph.store import ensure_graph
from app.layers.contracts import SEASONS, LayerDataError, PoiKind
from app.layers.registry import build_registry
from app.routing.contracts import EndMode, RouteQuery
from app.routing.graph import RoutingGraph
from app.routing.profiles import default_models
from app.routing.service import plan_route
from tests.conftest import DEM_SHAPE, build_fixture_data

REAL_DATA = Path(__file__).resolve().parents[3] / "data"
WINTER = SEASONS[1]


# ----------------------------------------------------------------------------------- synthetic
@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    root = build_fixture_data(tmp_path_factory.mktemp("graph_data"))
    # The shared fixture DEM is a steep 10 deg plane (tens of km high at this size); use a gentle surface
    # so elevations stay plausible and both profiles can drive on it.
    rows, cols = DEM_SHAPE
    y, x = np.mgrid[0:rows, 0:cols]
    tifffile.imwrite(root / "raw/dem/dem_blend200m_aoi.tif",
                     (1200.0 * np.sin(x / 3.0) + 400.0 * np.cos(y / 2.0)).astype("float32"))
    settings = Settings(data_dir=root)
    return settings, build_registry(settings)


@pytest.fixture(scope="module")
def inputs(synthetic):
    settings, registry = synthetic
    return graph_inputs_from_registry(registry, settings, coarsen=1)


@pytest.fixture(scope="module")
def graph(inputs):
    return build_graph(inputs, default_models(), BuildConfig())


def test_inputs_come_from_the_getters_and_validate(synthetic, inputs):
    _, registry = synthetic
    getter = registry.get("relief").grid()
    assert inputs.grid.shape == getter["elevation_m"].shape
    # Display slope and routing slope are the same array.
    assert np.allclose(inputs.relief.slope_deg, getter["slope_deg"], equal_nan=True)
    assert np.allclose(inputs.relief.elev_m, getter["elevation_m"], equal_nan=True)
    assert [f.id for f in inputs.poi.features] == [f["properties"]["id"] for f in registry.get("poi").features()]
    kinds = {f.kind for f in inputs.poi.features}
    assert PoiKind.MINERAL_SULFATE in kinds and PoiKind.MINERAL_SILICA in kinds
    assert inputs.relief.source_files and inputs.weather.source_files and inputs.poi.source_files


def test_weather_matches_the_getter_and_keeps_messages(synthetic, inputs):
    _, registry = synthetic
    getter = registry.get("weather")
    lon, lat = -69.5, -11.5  # a fixture cell
    sample = getter.sample(lon, lat)
    for key, season in zip(("autumn", "winter", "spring", "summer"), SEASONS):
        risk, conf = inputs.weather.risk_at(lon, lat, season)
        assert sample[key]["risk"] == {0: "Low", 1: "Moderate", 2: "High"}[int(risk)]
        frame = inputs.weather.frame_at(lon, lat, season)
        assert frame["message"] == sample[key]["message"] and frame["confidence"] == sample[key]["confidence"]
    assert inputs.weather.caveat == getter.describe("winter")["caveat"]
    # a point outside the fixture cells has no estimate, which the graph must carry as such
    assert inputs.weather.risk_at(-68.2, -13.2, WINTER)[0] == -1


def test_graph_nodes_carry_relief_and_weather(inputs, graph):
    assert graph.n_edges > 0 and graph.grid == inputs.grid
    assert np.allclose(graph.node["slope_deg"], inputs.relief.slope_deg.reshape(-1), equal_nan=True)
    for k in range(4):
        assert (graph.node[weather_risk_key(k)] == inputs.weather.risk[k].reshape(-1)).all()
        assert (graph.node[weather_conf_key(k)] == inputs.weather.confidence[k].reshape(-1)).all()
    for p in PROFILES:
        assert (graph.cost(p) > 0).all()


def _query(grid, profile, **kw):
    node = lambda lon, lat: int(grid.node_id(*grid.lonlat_to_rc(lon, lat)))  # noqa: E731
    return RouteQuery(profile=profile, start_node=node(-71.5, -13.0),
                      destination_nodes=(node(-69.0, -11.0), node(-70.5, -10.5)), time_limit_s=1,
                      season=WINTER, **kw)


@pytest.mark.parametrize("profile", list(PROFILES), ids=lambda p: p.value)
def test_routing_engine_plans_a_route_over_the_built_graph(inputs, graph, profile):
    rg = RoutingGraph.from_graph_data(graph)
    q = _query(inputs.grid, profile)
    plan = plan_route(rg, q, capacities={"o2_g": 1.0, "time_s": 1e9})
    assert plan.nodes[0] == plan.nodes[-1] == q.start_node  # round trip
    assert set(plan.stop_order) == {0, 1} and not plan.dropped
    # the engine's total equals the graph's own weights summed along the returned path
    assert plan.total_cost == pytest.approx(rg.path_cost(profile, plan.nodes), rel=1e-6)
    assert set(plan.resources) >= set(RESOURCES) and plan.resources["time_s"] > 0
    assert any("o2_g" in w for w in plan.warnings)  # the 1 g budget is exceeded, and says so


def test_the_engine_never_uses_an_edge_the_profile_cannot_cross(inputs, graph):
    rg = RoutingGraph.from_graph_data(graph)
    plan = plan_route(rg, _query(inputs.grid, ProfileId.ASTRONAUT))
    ids = rg.edge_ids(plan.nodes)
    assert np.isfinite(graph.cost(ProfileId.ASTRONAUT)[ids]).all()


def test_graph_survives_save_load_and_is_reused_while_fresh(inputs, graph, tmp_path):
    path = tmp_path / "g.npz"
    graph.save(path)
    again = GraphData.load(path)
    assert again.fingerprint() == graph.fingerprint()
    _, built = ensure_graph(path, inputs, default_models(), BuildConfig())
    assert built is False
    # editing a model parameter marks the saved graph stale
    from app.routing.profiles import AstronautModel, AstronautParams, CarModel
    _, built = ensure_graph(path, inputs, [AstronautModel(AstronautParams(suit_mass_kg=90.0)), CarModel()],
                            BuildConfig())
    assert built is True


def test_cli_builds_from_the_getters(synthetic, tmp_path, capsys):
    settings, _ = synthetic
    out = tmp_path / "cli.npz"
    assert graph_cli(["--data-dir", str(settings.data_dir), "--coarsen", "1", "--out", str(out)]) == 0
    assert "built:" in capsys.readouterr().out
    assert GraphData.load(out).n_edges > 0


def test_a_missing_layer_is_reported_with_its_fix(tmp_path):
    registry = build_registry(Settings(data_dir=tmp_path))
    with pytest.raises(LayerDataError, match="download_data.py"):
        graph_inputs_from_registry(registry, Settings(data_dir=tmp_path))


def test_coarsen_must_be_positive(synthetic):
    settings, registry = synthetic
    with pytest.raises(ValueError):
        graph_inputs_from_registry(registry, settings, coarsen=0)


def test_coarsening_averages_the_getter_arrays_and_keeps_the_grid_aligned(synthetic):
    settings, registry = synthetic
    native = graph_inputs_from_registry(registry, settings, coarsen=1)
    coarse = graph_inputs_from_registry(registry, settings, coarsen=2)
    rows, cols = native.grid.shape
    assert coarse.grid.shape == (rows // 2, cols // 2)
    e = native.relief.elev_m.astype(np.float64)
    assert coarse.relief.elev_m[0, 0] == pytest.approx(e[:2, :2].mean(), rel=1e-5)
    # same top-left corner, cells twice as big
    assert (coarse.grid.west, coarse.grid.north) == (native.grid.west, native.grid.north)
    assert coarse.grid.dlon == pytest.approx(2 * native.grid.dlon)


# ----------------------------------------------------------------------------------- real data
_REAL = all((REAL_DATA / "raw" / p).is_file() for p in ("dem/dem_blend200m_aoi.tif",
                                                        "weather/context_weather_frames.geojson"))
real_only = pytest.mark.skipif(not _REAL, reason="data/raw not downloaded (run scripts/download_data.py)")


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    settings = Settings(data_dir=REAL_DATA)
    registry = build_registry(settings)
    inputs = graph_inputs_from_registry(registry, settings)  # native 200 m grid
    data = build_graph(inputs, default_models(), BuildConfig())
    return registry, inputs, data, RoutingGraph.from_graph_data(data)


@real_only
def test_real_graph_has_the_expected_shape(real):
    _, inputs, data, _ = real
    assert inputs.grid.shape == (1073, 1200) and data.n_edges > 10_000_000
    assert (data.cost(ProfileId.ASTRONAUT) < np.inf).mean() > 0.8  # most terrain is walkable
    assert (data.cost(ProfileId.CAR) < np.inf).mean() > 0.99


@real_only
def test_real_weather_in_the_graph_matches_the_getter(real):
    registry, inputs, data, _ = real
    getter = registry.get("weather")
    for lon, lat in ((-69.5, -11.5), (-70.5, -12.5), (-71.5, -12.5)):  # cell centres inside the grid
        sample = getter.sample(lon, lat)
        for key, season in zip(("autumn", "winter", "spring", "summer"), SEASONS):
            risk, _conf = inputs.weather.risk_at(lon, lat, season)
            assert {0: "Low", 1: "Moderate", 2: "High"}[int(risk)] == sample[key]["risk"]
            assert inputs.weather.frame_at(lon, lat, season)["message"] == sample[key]["message"]


@real_only
@pytest.mark.parametrize("profile", list(PROFILES), ids=lambda p: p.value)
def test_real_route_over_the_real_graph(real, profile):
    _, inputs, data, rg = real
    q = _query(inputs.grid, profile)
    plan = plan_route(rg, q, capacities={"time_s": 8 * 3600})
    assert plan.nodes[0] == plan.nodes[-1] == q.start_node and set(plan.stop_order) == {0, 1}
    assert plan.total_cost == pytest.approx(rg.path_cost(profile, plan.nodes), rel=1e-6)
    assert np.isfinite(data.cost(profile)[rg.edge_ids(plan.nodes)]).all()
    assert plan.resources["time_s"] > 0 and plan.warnings  # 8 h budget is exceeded on a multi-stop trip


@real_only
def test_real_car_is_cheaper_in_time_than_the_astronaut(real):
    _, inputs, _, rg = real
    node = lambda lon, lat: int(inputs.grid.node_id(*inputs.grid.lonlat_to_rc(lon, lat)))  # noqa: E731
    a, b = node(-71.0, -12.0), node(-69.0, -11.0)
    times = {}
    for p in PROFILES:
        plan = plan_route(rg, RouteQuery(profile=p, start_node=a, destination_nodes=(b,),
                                         end_mode=EndMode.ROUND_TRIP, time_limit_s=1))
        times[p] = plan.resources["time_s"]
    assert times[ProfileId.CAR] < times[ProfileId.ASTRONAUT]
