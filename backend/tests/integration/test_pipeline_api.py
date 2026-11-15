"""The whole pipeline through the HTTP API.

    data/raw files -> layer ingestion -> `python -m app.graph` (cost functions + weights) -> graph.npz
    -> app startup (RoutingContext) -> POST /api/route -> cross-checked against the layer endpoints

`synthetic` always runs (tiny fixture data); `real` builds the native 200 m graph from the downloaded
data (about a minute) and is skipped when data/raw is missing.
"""
from pathlib import Path

import numpy as np
import pytest
import yaml
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.configfile import DEFAULT_CONFIG_PATH, load_settings
from app.core.resources import PROFILES, RESOURCES
from app.graph.cli import main as graph_cli
from app.graph.contracts import GraphData
from main import create_app
from tests.conftest import AuthedTestClient, register_and_login
from tests.integration.helpers import make_gentle_data, node_point

REAL_DATA = Path(__file__).resolve().parents[3] / "data"
SECRET = "pipeline-test-secret-key-at-least-32-bytes"
FIXTURE_LON_FAR = node_point(5, 0)["lon"] + 0.2  # 0.2 deg (~12 km) east of a node: still inside the area


def route_body(profile="astronaut", **extra) -> dict:
    """A trip over the fixture grid: start and two destinations, all on node centres."""
    return {"profile": profile, "start": node_point(5, 0),
            "destinations": [node_point(2, 5), node_point(2, 2)],  # inside the fixture weather cells
            "season": "winter", "time_limit_s": 1, **extra}


def real_body(profile="astronaut", **extra) -> dict:
    return {"profile": profile, "start": {"lon": -71.0, "lat": -12.0},
            "destinations": [{"lon": -69.0, "lat": -11.0}, {"lon": -70.5, "lat": -10.5}],
            "season": "winter", "time_limit_s": 1, **extra}


def client_for(data_dir, config=None, **settings) -> AuthedTestClient:
    """An app configured like production: from the YAML file (the same one the graph was built with)."""
    return AuthedTestClient(create_app(load_settings(config, data_dir=data_dir, jwt_secret_key=SECRET, **settings)))


# ----------------------------------------------------------------------------------- synthetic
@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """A data root whose graph was built by the real CLI."""
    root = make_gentle_data(tmp_path_factory.mktemp("pipeline"))
    assert graph_cli(["--data-dir", str(root)]) == 0
    return root


@pytest.fixture(scope="module")
def client(built):
    with client_for(built, capacities={"astronaut": {"o2_g": 1.0, "time_s": 1e9}}) as c:
        yield c


def test_route_is_503_until_the_graph_is_built_then_works(tmp_path, capsys):
    root = make_gentle_data(tmp_path)
    with client_for(root) as c:
        r = c.post("/api/route", json=route_body())
        assert r.status_code == 503 and "graph" in r.json()["detail"].lower()
        assert c.get("/api/get-layer-two").status_code == 200  # the layer endpoints keep working
    assert graph_cli(["--data-dir", str(root)]) == 0
    assert "built:" in capsys.readouterr().out
    with client_for(root) as c:
        assert c.post("/api/route", json=route_body()).status_code == 200
    assert graph_cli(["--data-dir", str(root)]) == 0  # nothing changed: the saved graph is reused
    assert "up to date" in capsys.readouterr().out


def test_every_layer_and_the_router_are_up(client):
    assert client.app.state.layers.status() == {k: "ok" for k in ("base_imagery", "relief", "poi", "weather")}
    assert client.app.state.routing.graph.n_edges > 0


@pytest.mark.parametrize("profile", [p.value for p in PROFILES])
def test_route_response_is_consistent(client, profile):
    r = client.post("/api/route", json=route_body(profile))
    assert r.status_code == 200, r.text
    j = r.json()
    coords = np.array(j["path"]["coordinates"])
    assert j["path"]["type"] == "LineString" and coords.shape[1] == 2 and len(coords) > 2
    start = j["snapped"]["start"]
    assert coords[0].tolist() == [start["lon"], start["lat"]] == coords[-1].tolist()  # round trip
    assert sorted(j["stop_order"]) == [0, 1] and j["dropped"] == []
    assert j["total_weight"] == pytest.approx(sum(leg["weight"] for leg in j["legs"]))
    for res in RESOURCES:  # per-leg resources add up to the totals
        assert j["resources"][res] == pytest.approx(sum(leg["resources"][res] for leg in j["legs"]), rel=1e-6)
    assert j["resources"]["time_s"] > 0 and all(p["distance_m"] <= 1000 for p in
                                                [start, *j["snapped"]["destinations"]])
    # the default test user weighs 80 kg: the astronaut estimate uses it, the car does not depend on mass
    assert j["body_mass_kg"] == (80.0 if profile == "astronaut" else None)
    assert not any("reference astronaut mass" in w for w in j["warnings"])  # graph and models are in sync


def test_route_requires_login(built):
    with TestClient(create_app(Settings(data_dir=built, jwt_secret_key=SECRET))) as anonymous:
        assert anonymous.post("/api/route", json=route_body()).status_code == 401


def test_body_mass_changes_the_estimates_but_never_the_route(client):
    """Mass comes from the database row of whoever sends the token."""
    light = register_and_login(client, "light@example.com", body_mass_kg=55.0)
    heavy = register_and_login(client, "heavy@example.com", body_mass_kg=110.0)
    a = client.post("/api/route", json=route_body(), headers=light).json()
    b = client.post("/api/route", json=route_body(), headers=heavy).json()
    assert (a["body_mass_kg"], b["body_mass_kg"]) == (55.0, 110.0)
    assert a["path"] == b["path"] and a["stop_order"] == b["stop_order"]  # the same route for everyone
    assert a["total_weight"] == b["total_weight"] and a["legs"][0]["weight"] == b["legs"][0]["weight"]
    for res in ("o2_g", "co2_g", "water_g"):
        assert b["resources"][res] > a["resources"][res]
    for res in ("time_s", "energy_wh"):
        assert b["resources"][res] == pytest.approx(a["resources"][res])
    for leg_a, leg_b in zip(a["legs"], b["legs"]):  # per-leg numbers are personalised too
        assert leg_b["resources"]["o2_g"] > leg_a["resources"]["o2_g"]


def test_a_changed_profile_is_used_on_the_next_request(client):
    headers = register_and_login(client, "changing@example.com", body_mass_kg=60.0)
    before = client.post("/api/route", json=route_body(), headers=headers).json()
    assert client.patch("/api/users/me", json={"body_mass_kg": 100.0}, headers=headers).status_code == 200
    after = client.post("/api/route", json=route_body(), headers=headers).json()  # same token, new database value
    assert (before["body_mass_kg"], after["body_mass_kg"]) == (60.0, 100.0)
    assert after["resources"]["o2_g"] > before["resources"]["o2_g"] and after["path"] == before["path"]


def test_the_car_does_not_use_body_mass(client):
    headers = register_and_login(client, "driver@example.com", body_mass_kg=120.0)
    a = client.post("/api/route", json=route_body("car"), headers=headers).json()
    b = client.post("/api/route", json=route_body("car")).json()  # the default 80 kg user
    assert a["body_mass_kg"] is None and a["resources"] == b["resources"]


def test_the_car_is_faster_than_the_astronaut_over_the_same_trip(client):
    t = {p: client.post("/api/route", json=route_body(p)).json()["resources"]["time_s"] for p in ("astronaut", "car")}
    assert t["car"] < t["astronaut"]


def test_weather_warnings_are_the_layer_messages_verbatim(client):
    j = client.post("/api/route", json=route_body("car")).json()
    weather = client.app.state.layers.get("weather")
    dest = j["snapped"]["destinations"][0]
    assert weather.sample(dest["lon"], dest["lat"])["winter"]["message"] in j["warnings"]
    layer = client.get("/api/get-layer-four", params={"season": "winter"}).json()
    served = {f["properties"]["message"] for f in layer["features"]}
    assert any(w in served for w in j["warnings"])  # the router shows what the map shows


def test_a_point_without_weather_data_says_so_instead_of_staying_silent(client):
    # node (0, 7) lies outside the fixture's weather cells: the route must warn, not imply "no risk"
    j = client.post("/api/route", json=route_body("car", destinations=[node_point(2, 5), node_point(0, 7)])).json()
    assert any("No weather data" in w for w in j["warnings"])
    assert any("dust-storm" in w for w in j["warnings"])  # the covered destination still shows its message


def test_budget_warnings_use_the_configured_capacities(client):
    warnings = client.post("/api/route", json=route_body("astronaut")).json()["warnings"]
    assert any("o2_g" in w and "exceeds the budget" in w for w in warnings)
    assert not any("time_s" in w and "exceeds" in w for w in warnings)  # a 1e9 s budget is not exceeded
    car = client.post("/api/route", json=route_body("car")).json()["warnings"]
    assert not any("exceeds the budget" in w for w in car)  # no capacities configured for the car


def test_the_slope_the_map_shows_is_the_slope_the_router_uses(built, client):
    settings = Settings(data_dir=built, jwt_secret_key=SECRET)
    graph = GraphData.load(settings.graph_file)
    snapped = client.post("/api/route", json=route_body()).json()["snapped"]["start"]
    shown = client.get("/api/get-layer-two/point", params={"lon": snapped["lon"], "lat": snapped["lat"]}).json()
    node = int(graph.grid.node_id(*graph.grid.lonlat_to_rc(snapped["lon"], snapped["lat"])))
    assert shown["slope_deg"] == pytest.approx(float(graph.node["slope_deg"][node]), abs=0.01)
    assert shown["elevation_m"] == pytest.approx(float(graph.node["elev_m"][node]), abs=0.1)


def test_bad_requests_are_rejected_clearly(client):
    outside = route_body(start={"lon": 10.0, "lat": 10.0})
    r = client.post("/api/route", json=outside)
    assert r.status_code == 422 and "outside" in r.json()["detail"]
    same = route_body(destinations=[node_point(2, 5), node_point(2, 5, jitter=0.001)])  # both snap to one node
    far = route_body(start={"lon": FIXTURE_LON_FAR, "lat": node_point(5, 0)["lat"]})
    r = client.post("/api/route", json=same)
    assert r.status_code == 422 and "destination 0" in r.json()["detail"]
    r = client.post("/api/route", json=far)  # inside the area but farther than 1 km from any node
    assert r.status_code == 422 and "maximum 1000 m" in r.json()["detail"]
    assert client.post("/api/route", json={**route_body(), "profile": "tank"}).status_code == 422


# ----------------------------------------------------------------------------------- configuration
def custom_config(tmp_path, **astronaut) -> Path:
    doc = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    doc["profiles"]["astronaut"].update(astronaut)
    doc["capacities"] = {"astronaut": {"o2_g": 1.0}}
    path = tmp_path / "custom.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return path


def test_the_configuration_file_drives_the_graph_and_the_api(tmp_path, capsys):
    root = make_gentle_data(tmp_path / "data")
    config = custom_config(tmp_path, suit_mass_kg=65.0)
    assert graph_cli(["--data-dir", str(root), "--config", str(config)]) == 0  # graph built with the file's numbers
    with client_for(root, config) as c:
        j = c.post("/api/route", json=route_body()).json()
        assert j["body_mass_kg"] == 80.0 and not any("reference astronaut mass" in w for w in j["warnings"])
        assert any("o2_g" in w and "exceeds the budget" in w for w in j["warnings"])  # capacities come from the file
    with client_for(root) as c:  # the app runs with the default file: the graph is stale for it
        j = c.post("/api/route", json=route_body()).json()
        assert j["body_mass_kg"] is None and any("reference astronaut mass" in w for w in j["warnings"])
    assert graph_cli(["--data-dir", str(root), "--config", str(config)]) == 0
    assert "up to date" in capsys.readouterr().out.splitlines()[-1]  # same file again: reused
    assert graph_cli(["--data-dir", str(root)]) == 0  # the default file has other parameters: rebuilt
    assert "built:" in capsys.readouterr().out.splitlines()[-1]


def test_changing_a_profile_parameter_changes_the_resource_estimates_not_the_route(tmp_path):
    base_root, heavy_root = make_gentle_data(tmp_path / "a"), make_gentle_data(tmp_path / "b")
    default, heavy = custom_config(tmp_path), None
    heavy = tmp_path / "heavy.yaml"
    doc = yaml.safe_load(default.read_text())
    doc["profiles"]["astronaut"]["suit_mass_kg"] = 120.0
    heavy.write_text(yaml.safe_dump(doc, sort_keys=False))
    assert graph_cli(["--data-dir", str(base_root), "--config", str(default)]) == 0
    assert graph_cli(["--data-dir", str(heavy_root), "--config", str(heavy)]) == 0
    with client_for(base_root, default) as a, client_for(heavy_root, heavy) as b:
        ra, rb = (c.post("/api/route", json=route_body()).json() for c in (a, b))
    assert ra["path"] == rb["path"] and ra["total_weight"] == pytest.approx(rb["total_weight"])  # same route
    assert rb["resources"]["o2_g"] > ra["resources"]["o2_g"]  # a heavier suit burns more oxygen


def test_request_limits_from_the_configuration_apply_through_the_api(tmp_path):
    root = make_gentle_data(tmp_path / "data")
    doc = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    doc["routing"].update(max_destinations=1, default_time_limit_s=2, min_time_limit_s=1, max_time_limit_s=3)
    config = tmp_path / "limits.yaml"
    config.write_text(yaml.safe_dump(doc, sort_keys=False))
    assert graph_cli(["--data-dir", str(root), "--config", str(config)]) == 0
    with client_for(root, config) as c:
        r = c.post("/api/route", json=route_body())  # two destinations, one allowed
        assert r.status_code == 422 and "At most 1 destinations" in r.json()["detail"]
        one = route_body(destinations=[node_point(2, 5)])
        one.pop("time_limit_s")  # no time limit asked for: the configured default applies
        assert c.post("/api/route", json=one).status_code == 200
    with client_for(root) as c:  # the default configuration allows both destinations
        assert c.post("/api/route", json=route_body()).status_code == 200


def test_an_invalid_configuration_stops_the_graph_build_with_a_clear_message(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("profiles:\n  astronaut:\n    suit_mas_kg: 5\n")
    assert graph_cli(["--data-dir", str(tmp_path), "--config", str(bad)]) == 2
    err = capsys.readouterr().err
    assert "invalid configuration" in err and "suit_mas_kg" in err


# ----------------------------------------------------------------------------------- real data
_REAL = all((REAL_DATA / "raw" / p).exists() for p in ("dem/dem_blend200m_aoi.tif",
                                                       "weather/context_weather_frames.geojson", "features"))
real_only = pytest.mark.skipif(not _REAL, reason="data/raw not downloaded (run scripts/download_data.py)")


@pytest.fixture(scope="module")
def real_client(tmp_path_factory):
    root = tmp_path_factory.mktemp("real_pipeline")
    (root / "raw").symlink_to(REAL_DATA / "raw", target_is_directory=True)  # graph.npz goes in the temp dir
    assert graph_cli(["--data-dir", str(root)]) == 0  # native 200 m grid
    with client_for(root, capacities={"astronaut": {"o2_g": 2000.0, "time_s": 8 * 3600.0}}) as c:
        yield c


@real_only
def test_real_pipeline_serves_routes_on_the_native_graph(real_client):
    ctx = real_client.app.state.routing
    assert ctx.grid.shape == (1073, 1200) and ctx.graph.n_edges > 10_000_000
    for profile in ("astronaut", "car"):
        r = real_client.post("/api/route", json=real_body(profile))
        assert r.status_code == 200, r.text
        j = r.json()
        assert sorted(j["stop_order"]) == [0, 1] and j["resources"]["time_s"] > 0
        assert any("dust-storm" in w for w in j["warnings"])  # the weather message reaches the route
    astronaut = real_client.post("/api/route", json=real_body("astronaut"))
    assert any("exceeds the budget" in w for w in astronaut.json()["warnings"])  # an 8 h budget is exceeded
