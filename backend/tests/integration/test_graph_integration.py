"""Layer ingestion/services -> graph (cost functions and weights) -> routing engine, end to end.

`synthetic` uses the shared fixture data root (a tiny DEM, POI and weather files); `real` uses the
downloaded data on the native 200 m grid and is skipped when data/raw is missing.
"""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import tifffile

from app.core.config import Settings
from app.core.resources import PROFILES, RESOURCES, ProfileId
from app.graph.build import BuildConfig, build_graph
from app.graph.cli import main as graph_cli
from app.graph.contracts import GraphData
from app.graph.loader import load_routing_context
from app.graph.nodes import weather_conf_key, weather_risk_key
from app.graph.store import ensure_graph
from app.layers.contracts import SEASONS, LayerDataError, PoiKind
from app.layers.inputs.load import load_all
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
def synthetic_settings(tmp_path_factory):
    root = build_fixture_data(tmp_path_factory.mktemp("graph_data"))
    # The shared fixture DEM is a steep 10 deg plane (tens of km high at this size); use a gentle surface
    # so elevations stay plausible and both profiles can drive on it.
    rows, cols = DEM_SHAPE
    y, x = np.mgrid[0:rows, 0:cols]
    tifffile.imwrite(root / "raw/dem/dem_blend200m_aoi.tif",
                     (1200.0 * np.sin(x / 3.0) + 400.0 * np.cos(y / 2.0)).astype("float32"))
    return Settings(data_dir=root, jwt_secret_key="test")


@pytest.fixture(scope="module")
def inputs(synthetic_settings):
    return load_all(synthetic_settings)


@pytest.fixture(scope="module")
def graph(inputs):
    return build_graph(inputs, default_models(), BuildConfig())


def test_inputs_come_from_the_layer_ingestion_and_validate(synthetic_settings, inputs):
    registry = build_registry(synthetic_settings)
    shape = registry.get("relief").grid()["elevation_m"].shape
    assert inputs.grid.shape == shape  # the shared grid: display and routing use the same one
    assert {f.kind for f in inputs.poi.features} >= {PoiKind.MINERAL_SULFATE, PoiKind.MINERAL_SILICA}
    assert inputs.relief.source_files and inputs.weather.source_files and inputs.poi.source_files


def test_relief_slope_shown_to_users_is_the_slope_the_graph_uses(synthetic_settings, inputs, graph):
    shown = build_registry(synthetic_settings).get("relief").grid()["slope_deg"]
    assert np.allclose(inputs.relief.slope_deg, shown, equal_nan=True)
    assert np.allclose(graph.node["slope_deg"], shown.reshape(-1), equal_nan=True)


def test_graph_weather_matches_the_weather_service_and_keeps_messages(synthetic_settings, inputs):
    service = build_registry(synthetic_settings).get("weather")
    lon, lat = -69.5, -11.5  # a fixture cell centre
    sample = service.sample(lon, lat)
    for key, season in zip(("autumn", "winter", "spring", "summer"), SEASONS):
        risk, _conf = inputs.weather.risk_at(lon, lat, season)
        assert sample[key]["risk"] == {0: "Low", 1: "Moderate", 2: "High"}[int(risk)]
        assert inputs.weather.frame_at(lon, lat, season)["message"] == sample[key]["message"]
    assert inputs.weather.risk_at(-68.2, -13.2, WINTER)[0] == -1  # outside the fixture cells: no estimate


def test_graph_nodes_carry_relief_and_weather(inputs, graph):
    assert graph.n_edges > 0 and graph.grid == inputs.grid
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
    assert plan.total_cost == pytest.approx(rg.path_cost(profile, plan.nodes), rel=1e-6)
    assert set(plan.resources) >= set(RESOURCES) and plan.resources["time_s"] > 0
    assert any("o2_g" in w for w in plan.warnings)  # the 1 g budget is exceeded, and says so


def test_the_engine_never_uses_an_edge_the_profile_cannot_cross(inputs, graph):
    rg = RoutingGraph.from_graph_data(graph)
    plan = plan_route(rg, _query(inputs.grid, ProfileId.ASTRONAUT))
    assert np.isfinite(graph.cost(ProfileId.ASTRONAUT)[rg.edge_ids(plan.nodes)]).all()


def test_graph_survives_save_load_and_is_reused_while_fresh(inputs, graph, tmp_path):
    path = tmp_path / "g.npz"
    graph.save(path)
    assert GraphData.load(path).fingerprint() == graph.fingerprint()
    _, built = ensure_graph(path, inputs, default_models(), BuildConfig())
    assert built is False
    # editing a model parameter marks the saved graph stale
    from app.routing.profiles import AstronautModel, AstronautParams, CarModel
    _, built = ensure_graph(path, inputs, [AstronautModel(AstronautParams(suit_mass_kg=90.0)), CarModel()],
                            BuildConfig())
    assert built is True


def test_a_changed_source_file_marks_the_saved_graph_stale(inputs, graph, tmp_path):
    path = tmp_path / "g.npz"
    graph.save(path)
    changed = replace(inputs, relief=replace(inputs.relief, source_files=("dem/dem_blend200m_aoi.tif:" + "0" * 64,)))
    _, built = ensure_graph(path, changed, default_models(), BuildConfig())
    assert built is True


def test_cli_builds_the_graph_the_app_loads_and_the_app_loader_reads_it(synthetic_settings, tmp_path, capsys):
    data_dir = synthetic_settings.data_dir
    assert graph_cli(["--data-dir", str(data_dir)]) == 0  # default output = Settings.graph_file
    assert "built:" in capsys.readouterr().out
    ctx = load_routing_context(synthetic_settings)  # what the API loads at startup
    assert ctx.graph.n_edges > 0 and ctx.grid == load_all(synthetic_settings).grid


def test_a_missing_layer_is_reported_with_its_fix(tmp_path, capsys):
    with pytest.raises(LayerDataError, match="--only dem"):
        load_all(Settings(data_dir=tmp_path))
    assert graph_cli(["--data-dir", str(tmp_path)]) == 2
    assert "cannot build the graph" in capsys.readouterr().err


def test_coarsen_option_changes_the_shared_grid(synthetic_settings):
    native = load_all(synthetic_settings)
    coarse = load_all(replace(synthetic_settings, grid_coarsen=2))
    assert coarse.grid.shape == (native.grid.nrows // 2, native.grid.ncols // 2)


# ----------------------------------------------------------------------------------- real data
_REAL = all((REAL_DATA / "raw" / p).is_file() for p in ("dem/dem_blend200m_aoi.tif",
                                                        "weather/context_weather_frames.geojson"))
real_only = pytest.mark.skipif(not _REAL, reason="data/raw not downloaded (run scripts/download_data.py)")


@pytest.fixture(scope="module")
def real():
    settings = Settings(data_dir=REAL_DATA, jwt_secret_key="test")
    registry = build_registry(settings)
    inputs = load_all(settings)  # native 200 m grid
    data = build_graph(inputs, default_models(), BuildConfig())
    return registry, inputs, data, RoutingGraph.from_graph_data(data)


@real_only
def test_real_graph_has_the_expected_shape(real):
    _, inputs, data, _ = real
    assert inputs.grid.shape == (1073, 1200) and data.n_edges > 10_000_000
    assert (data.cost(ProfileId.ASTRONAUT) < np.inf).mean() > 0.8  # most terrain is walkable
    assert (data.cost(ProfileId.CAR) < np.inf).mean() > 0.99


@real_only
def test_real_weather_in_the_graph_matches_the_weather_service(real):
    registry, inputs, _, _ = real
    service = registry.get("weather")
    for lon, lat in ((-69.5, -11.5), (-70.5, -12.5), (-71.5, -12.5)):  # cell centres inside the grid
        sample = service.sample(lon, lat)
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
    assert plan.resources["time_s"] > 0 and plan.warnings  # an 8 h budget is exceeded on a multi-stop trip


@real_only
def test_real_car_is_faster_than_the_astronaut(real):
    _, inputs, _, rg = real
    node = lambda lon, lat: int(inputs.grid.node_id(*inputs.grid.lonlat_to_rc(lon, lat)))  # noqa: E731
    a, b = node(-71.0, -12.0), node(-69.0, -11.0)
    times = {p: plan_route(rg, RouteQuery(profile=p, start_node=a, destination_nodes=(b,),
                                          end_mode=EndMode.ROUND_TRIP, time_limit_s=1)).resources["time_s"]
             for p in PROFILES}
    assert times[ProfileId.CAR] < times[ProfileId.ASTRONAUT]
