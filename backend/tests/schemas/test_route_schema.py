import pytest
from pydantic import ValidationError

from app.layers.contracts import SEASONS
from app.schemas.route import RouteRequest, RouteResponse

BASE = {"profile": "astronaut", "start": {"lon": -70.1, "lat": -11.5},
        "destinations": [{"lon": -69.8, "lat": -11.2}]}


def test_minimal_request_gets_defaults():
    r = RouteRequest(**BASE)
    assert r.end_mode.value == "round_trip" and r.end is None and r.time_limit_s == 5.0


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
    {"destinations": [{"lon": -69.8, "lat": -11.2}] * 26},
    {"start": {"lon": 250.0, "lat": 0.0}},
    {"season": "Winter"},
    {"end_mode": "teleport"},
])
def test_invalid_requests_rejected(patch):
    with pytest.raises(ValidationError):
        RouteRequest(**{**BASE, **patch})


def test_time_limit_is_clamped_and_known_season_accepted():
    assert RouteRequest(**BASE, time_limit_s=999).time_limit_s == 30.0
    assert RouteRequest(**BASE, time_limit_s=0.01).time_limit_s == 1.0
    assert RouteRequest(**BASE, season=SEASONS[1]).season == SEASONS[1]


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
