import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from main import create_app
from tests.conftest import build_fixture_data
from tests.routing.helpers import INF, both, make_graph_data

# 0 - 1 - 2 - 3 on flat ground; 3 -> 4 is a cliff the car can climb but the astronaut cannot; 5 is isolated.
EDGES = [*both(0, 1, 1.0), *both(1, 2, 1.0), *both(2, 3, 1.0), (3, 4, INF), (4, 3, 1.0)]
GRAPH = make_graph_data(6, EDGES, car_edges={(3, 4): 5.0})
LON0, DLON, LAT = -70.875, 0.05, -11.85  # node i sits at (LON0 + i * DLON, LAT)


def pt(node: int, jitter: float = 0.001) -> dict:
    return {"lon": LON0 + node * DLON + jitter, "lat": LAT}


def body(profile="car", dests=(3, 1, 4), **extra) -> dict:
    return {"profile": profile, "start": pt(0), "destinations": [pt(n) for n in dests], "time_limit_s": 1, **extra}


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    root = build_fixture_data(tmp_path_factory.mktemp("routedata"))
    GRAPH.save(root / "graph" / "graph.npz")
    return root


def make_client(data_dir, **settings):
    return TestClient(create_app(Settings(data_dir=data_dir, **settings)))


@pytest.fixture(scope="module")
def client(data_dir):
    with make_client(data_dir) as c:
        yield c


def test_route_is_wired(client):
    assert "/api/route" in client.get("/openapi.json").json()["paths"]


def test_car_round_trip_visits_everything(client):
    r = client.post("/api/route", json=body())
    assert r.status_code == 200
    d = r.json()
    assert sorted(d["stop_order"]) == [0, 1, 2] and d["dropped"] == []
    assert d["total_weight"] == pytest.approx(12.0)
    assert d["path"]["type"] == "LineString"
    assert d["path"]["coordinates"][0] == d["path"]["coordinates"][-1]  # round trip
    assert d["legs"][0]["from"] == "start" and d["legs"][-1]["to"] == "start"
    assert sum(leg["weight"] for leg in d["legs"]) == pytest.approx(d["total_weight"])
    assert set(d["resources"]) == {"time_s", "o2_g", "co2_g", "water_g", "energy_wh"}
    assert d["snapped"]["start"]["distance_m"] > 0 and len(d["snapped"]["destinations"]) == 3
    assert d["snapped"]["end"] is None and d["warnings"] == []


def test_astronaut_drops_unreachable_stop_without_error(client):
    r = client.post("/api/route", json=body("astronaut"))
    assert r.status_code == 200
    d = r.json()
    assert [(x["index"], x["reason"]) for x in d["dropped"]] == [(2, "unreachable_for_profile")]
    assert d["dropped"][0]["point"] == pt(4)  # the requested point, not the snapped one


def test_open_end_has_no_return_leg(client):
    d = client.post("/api/route", json=body(dests=(2,), end_mode="open")).json()
    assert [(leg["from"], leg["to"]) for leg in d["legs"]] == [("start", 0)]


def test_fixed_end_is_labelled_end(client):
    d = client.post("/api/route", json=body(dests=(1,), end_mode="fixed", end=pt(3))).json()
    assert d["legs"][-1]["to"] == "end" and d["snapped"]["end"] is not None


def test_unreachable_fixed_end_is_422(client):
    r = client.post("/api/route", json=body(dests=(2,), end_mode="fixed", end=pt(5)))
    assert r.status_code == 422 and r.json()["detail"]


def test_points_snapping_to_the_same_node_are_422(client):
    r = client.post("/api/route", json=body(dests=(1, 1)))
    assert r.status_code == 422
    assert "destination 0 = destination 1" in r.json()["detail"]
    r = client.post("/api/route", json={**body(dests=(1,)), "start": pt(1)})
    assert "start = destination 0" in r.json()["detail"]


def test_point_outside_graph_is_422(client):
    r = client.post("/api/route", json={**body(), "start": {"lon": -60.0, "lat": -12.0}})
    assert r.status_code == 422 and "outside the routing area" in r.json()["detail"]


def test_point_too_far_from_a_node_is_422(data_dir):
    with make_client(data_dir, max_snap_distance_m=10.0) as c:
        r = c.post("/api/route", json=body(dests=(1,)))
    assert r.status_code == 422 and "maximum 10 m" in r.json()["detail"]


def test_schema_errors_are_422(client):
    assert client.post("/api/route", json={**body(), "profile": "hovercraft"}).status_code == 422
    assert client.post("/api/route", json={**body(), "destinations": []}).status_code == 422
    assert client.post("/api/route", json={**body(), "season": "S. Winter (Ls 90-180)"}).status_code == 422


def test_season_adds_weather_message_verbatim(client):
    d = client.post("/api/route", json=body(dests=(1,), season="winter")).json()
    assert d["warnings"] == ["APPROXIMATE: not enough data to reliably calculate the risk: fixture."]


def test_no_season_no_weather_warning(client):
    assert client.post("/api/route", json=body(dests=(1,))).json()["warnings"] == []


def test_exceeded_budget_adds_warning(data_dir):
    with make_client(data_dir, capacities={"car": {"time_s": 1.0}}) as c:
        d = c.post("/api/route", json=body(dests=(1,))).json()
    assert len(d["warnings"]) == 1 and "time_s" in d["warnings"][0]


def test_missing_graph_is_503_but_layers_still_work(empty_client):
    r = empty_client.post("/api/route", json=body())
    assert r.status_code == 503 and set(r.json()) == {"detail", "fix"}
    assert empty_client.get("/api/hello").status_code == 200


def test_unavailable_weather_gives_a_warning(tmp_path):
    GRAPH.save(tmp_path / "graph" / "graph.npz")  # graph present, weather files absent
    with make_client(tmp_path) as c:
        d = c.post("/api/route", json=body(dests=(1,), season="winter")).json()
    assert d["warnings"] == ["Weather layer unavailable: dust-storm risk is unknown for this route."]
