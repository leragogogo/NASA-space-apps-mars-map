import pytest
from pydantic import ValidationError

from app.layers.contracts import SEASONS
from app.routing.contracts import EndMode
from app.schemas.route import ModeSelection, ProfileOption, RouteRequest, RouteResponse

BASE = {"profile": "astronaut", "start": {"lon": -70.1, "lat": -11.5},
        "destinations": [{"lon": -69.8, "lat": -11.2}]}


def test_minimal_request_gets_defaults():
    r = RouteRequest(**BASE)
    assert r.end_mode.value == "round_trip" and r.end is None
    assert r.time_limit_s is None  # the configured default applies at request time


def test_fixed_end_requires_end_and_other_modes_forbid_it():
    end = {"lon": -70.0, "lat": -11.0}
    assert RouteRequest(**BASE, end_mode="fixed", end=end).end is not None
    with pytest.raises(ValidationError):
        RouteRequest(**BASE, end_mode="fixed")
    with pytest.raises(ValidationError):
        RouteRequest(**BASE, end_mode="open", end=end)


@pytest.mark.parametrize("patch", [
    {"profile": "hovercraft"},
    {"destinations": []},
    {"start": {"lon": 250.0, "lat": 0.0}},
    {"season": "S. Winter (Ls 90-180)"},
    {"end_mode": "teleport"},
])
def test_invalid_requests_rejected(patch):
    with pytest.raises(ValidationError):
        RouteRequest(**{**BASE, **patch})


def test_known_season_accepted_and_limits_are_left_to_the_handler():
    assert RouteRequest(**BASE, season="winter").season == "winter"
    # the schema does not know the configured limits: a large time limit or many destinations still parses
    assert RouteRequest(**BASE, time_limit_s=999).time_limit_s == 999
    assert len(RouteRequest(**{**BASE, "destinations": [{"lon": -69.8, "lat": -11.2}] * 60}).destinations) == 60


def test_response_roundtrip_uses_from_alias():
    payload = {
        "profile": "car", "path": {"type": "LineString", "coordinates": [[-70.1, -11.5], [-69.8, -11.2]]},
        "stop_order": [0], "legs": [{"from": "start", "to": 0, "weight": 12.5, "resources": {"o2_g": 3.0}}],
        "total_weight": 12.5, "resources": {"time_s": 60.0},
        "snapped": {"start": {"lon": -70.1, "lat": -11.5, "distance_m": 10.0}, "destinations": []},
    }
    out = RouteResponse(**payload)
    assert out.model_dump(by_alias=True)["legs"][0]["from"] == "start"
    assert out.dropped == [] and out.warnings == []


def test_start_and_end_alone_make_a_point_to_point_request():
    r = RouteRequest(start=BASE["start"], end={"lon": -70.0, "lat": -11.6})
    assert r.end_mode == EndMode.FIXED and r.destinations == [] and r.profile == "auto"


def test_without_end_mode_destinations_make_a_round_trip():
    assert RouteRequest(start=BASE["start"], destinations=BASE["destinations"]).end_mode == EndMode.ROUND_TRIP


def test_auto_and_named_profiles_are_accepted():
    for profile in ("auto", "astronaut", "car"):
        assert RouteRequest(**{**BASE, "profile": profile}).profile == profile


def test_mode_selection_serialises_options():
    m = ModeSelection(requested="auto", chosen="car", reason="r",
                      options=[ProfileOption(profile="car", feasible=True, reached=1, o2_g=1.0, time_s=2.0),
                               ProfileOption(profile="astronaut", feasible=False, reason="x")])
    assert m.model_dump()["options"][1] == {"profile": "astronaut", "feasible": False, "reached": 0,
                                            "o2_g": None, "time_s": None, "reason": "x"}
