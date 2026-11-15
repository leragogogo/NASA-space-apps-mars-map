import pytest

from app.core.config import Settings
from app.core.resources import ProfileId
from app.graph.loader import build_routing_context
from app.layers.relief.ingest import grid_for
from app.layers.weather.ingest import ingest_weather
from app.layers.weather.service import WeatherGetter
from app.routing.request import RouteRequestError, crew_size, handle_route_request
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
    # stops in the order given (nodes 3, 1, 4): 0->3 (3) + 3->1 (2) + 1->4 (1 + 1 + 5) + 4->0 (4)
    assert d.stop_order == [0, 1, 2] and d.dropped == []
    assert d.total_weight == pytest.approx(16.0)
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
        run(profile="astronaut", dests=(2,), end_mode="fixed", end=pt(4))


def test_a_point_nowhere_near_a_usable_node_is_a_snap_error():
    with pytest.raises(SnapError, match="passable for the car profile"):
        run(dests=(2,), end_mode="fixed", end=pt(5))


def test_start_and_end_on_one_node_is_a_request_error():
    with pytest.raises(RouteRequestError, match="start = end"):
        run(dests=(), end=pt(0, jitter=0.002))


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


def test_more_destinations_than_the_configured_maximum_raise():
    with pytest.raises(RouteRequestError, match="At most 2 destinations"):
        run(dests=(1, 2, 3), settings=Settings(max_destinations=2))
    assert run(dests=(1, 2), settings=Settings(max_destinations=2)).stop_order  # exactly the maximum is fine


def test_the_time_limit_follows_the_configured_range(monkeypatch):
    seen = []
    import app.routing.request as request_module
    real = request_module.plan_route
    monkeypatch.setattr(request_module, "plan_route",
                        lambda graph, query, *a, **k: (seen.append(query.time_limit_s), real(graph, query, *a, **k))[1])
    settings = Settings(default_time_limit_s=4.0, min_time_limit_s=2.0, max_time_limit_s=6.0)
    for asked in (None, 0.1, 999.0):
        handle_route_request(CTX, RouteRequest(profile="car", start=pt(0), destinations=[pt(1)], time_limit_s=asked), settings)
    assert seen == [4.0, 2.0, 6.0]  # default, raised to the minimum, cut to the maximum


# The car pays 5 on 0 <-> 1 (o2 = 2 x cost, shared by a crew of 2), so walking uses less oxygen per person there.
AUTO_CTX = build_routing_context(make_graph_data(6, EDGES, car_edges={(3, 4): 5.0, (0, 1): 5.0, (1, 0): 5.0}))


def run_auto(dests, **extra):
    req = RouteRequest(**{"profile": "auto", "start": pt(0), "destinations": [pt(n) for n in dests],
                          "time_limit_s": 2, **extra})
    return handle_route_request(AUTO_CTX, req, Settings())


def test_auto_walks_when_both_reach_everything_and_walking_uses_less_oxygen_per_person():
    d = run_auto((2,))
    assert d.profile == "astronaut" and d.mode.requested == "auto" and d.mode.chosen == "astronaut"
    assert "less oxygen per person (8 g vs 12 g)" in d.mode.reason
    assert {o.profile for o in d.mode.options} == {"astronaut", "car"} and all(o.feasible for o in d.mode.options)


def test_auto_drives_when_only_the_car_reaches_the_destination():
    d = run_auto((4,))
    assert d.profile == "car" and d.stop_order == [0] and "reaches 1 of 1" in d.mode.reason


def test_auto_explains_a_mode_that_cannot_route_at_all():
    d = run_auto((), end=pt(4))
    walking = next(o for o in d.mode.options if o.profile == "astronaut")
    assert d.profile == "car" and not walking.feasible and walking.reason and walking.o2_g is None
    assert "Walking cannot do this route" in d.mode.reason


def test_auto_with_no_feasible_mode_is_an_error():
    with pytest.raises(NoFeasibleRoute, match="No mode can route"):
        run_auto((2,), end_mode="fixed", end=pt(5))


def test_a_named_profile_is_the_users_choice():
    d = run(profile="car", dests=(1,))
    assert (d.mode.requested, d.mode.chosen, d.mode.reason) == ("car", "car", "Chosen by the user.")
    assert len(d.mode.options) == 1 and d.mode.options[0].feasible


def test_point_to_point_request():
    d = run(dests=(), end=pt(3))
    assert [(leg.from_, leg.to) for leg in d.legs] == [("start", "end")] and d.stop_order == []


def test_crew_size_is_one_walker_or_the_rover_crew():
    assert crew_size(Settings(), ProfileId.ASTRONAUT) == 1
    assert crew_size(Settings(), ProfileId.CAR) == 2  # CarParams default
    assert crew_size(Settings(profiles={"car": {"crew_n": 4}}), ProfileId.CAR) == 4
    assert crew_size(Settings(profiles={"car": {"crew_n": 0}}), ProfileId.CAR) == 1  # never divide by zero
