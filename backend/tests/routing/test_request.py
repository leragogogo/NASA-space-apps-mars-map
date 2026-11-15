import pytest

from app.core.config import Settings
from app.graph.loader import build_routing_context
from app.layers.relief.ingest import grid_for
from app.layers.weather.ingest import ingest_weather
from app.layers.weather.service import WeatherGetter
from app.routing.request import RouteRequestError, handle_route_request
from app.routing.snap import SnapError
from app.routing.solver import NoFeasibleRoute
from app.schemas.route import RouteRequest
from tests.conftest import build_fixture_data
from tests.routing.helpers import INF, both, make_graph_data

# 0 - 1 - 2 - 3 on flat ground; 3 -> 4 is a cliff the car can climb but the astronaut cannot; 5 is isolated.
EDGES = [*both(0, 1, 1.0), *both(1, 2, 1.0), *both(2, 3, 1.0), (3, 4, INF), (4, 3, 1.0)]
CTX = build_routing_context(make_graph_data(6, EDGES, car_edges={(3, 4): 5.0}))
LON0, DLON, LAT = -70.875, 0.05, -11.85  # node i sits at (LON0 + i * DLON, LAT)
WINTER = "winter"


def pt(node: int, jitter: float = 0.001) -> dict:
    return {"lon": LON0 + node * DLON + jitter, "lat": LAT}


def run(profile="car", dests=(3, 1, 4), settings=None, weather=None, **extra):
    req = RouteRequest(**{"profile": profile, "start": pt(0), "destinations": [pt(n) for n in dests],
                          "time_limit_s": 1, **extra})
    return handle_route_request(CTX, req, settings or Settings(), weather)


@pytest.fixture(scope="module")
def weather(tmp_path_factory):
    settings = Settings(data_dir=build_fixture_data(tmp_path_factory.mktemp("wdata")))
    return WeatherGetter(settings, ingest_weather(settings, grid_for(settings)))


def test_car_round_trip_visits_everything():
    d = run()
    assert sorted(d.stop_order) == [0, 1, 2] and d.dropped == []
    assert d.total_weight == pytest.approx(12.0)
    assert d.path["type"] == "LineString" and d.path["coordinates"][0] == d.path["coordinates"][-1]
    assert d.legs[0].from_ == "start" and d.legs[-1].to == "start"
    assert sum(leg.weight for leg in d.legs) == pytest.approx(d.total_weight)
    assert set(d.resources) == {"time_s", "o2_g", "co2_g", "water_g", "energy_wh"}
    assert d.snapped.start.distance_m > 0 and len(d.snapped.destinations) == 3 and d.snapped.end is None
    assert d.warnings == []


def test_response_serialises_legs_with_from_alias():
    assert "from" in run().model_dump(by_alias=True)["legs"][0]


def test_astronaut_drops_unreachable_stop_without_error():
    d = run("astronaut")
    assert [(x.index, x.reason.value) for x in d.dropped] == [(2, "unreachable_for_profile")]
    assert d.dropped[0].point.model_dump() == pt(4)  # the requested point, not the snapped one


def test_open_end_has_no_return_leg():
    assert [(leg.from_, leg.to) for leg in run(dests=(2,), end_mode="open").legs] == [("start", 0)]


def test_fixed_end_is_labelled_end():
    d = run(dests=(1,), end_mode="fixed", end=pt(3))
    assert d.legs[-1].to == "end" and d.snapped.end is not None


def test_unreachable_fixed_end_raises():
    with pytest.raises(NoFeasibleRoute):
        run(dests=(2,), end_mode="fixed", end=pt(5))


def test_points_snapping_to_the_same_node_raise():
    with pytest.raises(RouteRequestError, match="destination 0 = destination 1"):
        run(dests=(1, 1))
    with pytest.raises(RouteRequestError, match="start = destination 0"):
        run(dests=(0,))


def test_point_outside_graph_raises():
    req = RouteRequest(profile="car", start={"lon": -60.0, "lat": -12.0}, destinations=[pt(1)])
    with pytest.raises(SnapError, match="outside the routing area"):
        handle_route_request(CTX, req, Settings())


def test_point_too_far_from_a_node_raises():
    with pytest.raises(SnapError, match="maximum 10 m"):
        run(dests=(1,), settings=Settings(max_snap_distance_m=10.0))


def test_season_adds_weather_message_verbatim(weather):
    d = run(dests=(1,), weather=weather, season=WINTER)
    assert d.warnings == ["APPROXIMATE: not enough data to reliably calculate the risk: fixture."]


def test_no_season_no_weather_warning(weather):
    assert run(dests=(1,), weather=weather).warnings == []


def test_unavailable_weather_gives_a_warning():
    assert run(dests=(1,), season=WINTER).warnings == [
        "Weather layer unavailable: dust-storm risk is unknown for this route."]


def test_exceeded_budget_adds_warning():
    d = run(dests=(1,), settings=Settings(capacities={"car": {"time_s": 1.0}}))
    assert len(d.warnings) == 1 and "time_s" in d.warnings[0]
