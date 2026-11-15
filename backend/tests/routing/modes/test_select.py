import pytest

from app.core.resources import ProfileId
from app.routing.modes import NoProfileCanRoute, ProfileOutcome, choose
from app.routing.solver import NoFeasibleRoute

A, C = ProfileId.ASTRONAUT, ProfileId.CAR


def ok(profile, reached=2, o2=100.0, t=600.0):
    return ProfileOutcome(profile, reached=reached, requested=2, o2_g=o2, time_s=t)


def bad(profile, why="too steep"):
    return ProfileOutcome(profile, requested=2, error=why)


def test_least_oxygen_per_person_wins_when_both_reach_every_destination():
    best, reason = choose([ok(A, o2=80), ok(C, o2=120)])
    assert best.profile == A and "walking uses less oxygen per person (80 g vs 120 g)" in reason
    assert choose([ok(A, o2=150), ok(C, o2=120)])[0].profile == C


def test_reaching_more_destinations_beats_using_less_oxygen():
    best, reason = choose([ok(A, reached=1, o2=10), ok(C, reached=2, o2=500)])
    assert best.profile == C and "The vehicle reaches 2 of 2 destinations, walking only 1" in reason


def test_a_mode_that_cannot_route_is_never_chosen_and_says_why():
    best, reason = choose([bad(A, "start is on a 30 deg slope"), ok(C)])
    assert best.profile == C and "Walking cannot do this route (start is on a 30 deg slope)" in reason


def test_equal_oxygen_falls_back_to_time():
    best, reason = choose([ok(A, o2=100, t=900), ok(C, o2=100, t=300)])
    assert best.profile == C and "same oxygen use" in reason


def test_no_feasible_mode_raises_a_no_feasible_route_error():
    with pytest.raises(NoProfileCanRoute, match="walking: a; the vehicle: b") as e:
        choose([bad(A, "a"), bad(C, "b")])
    assert isinstance(e.value, NoFeasibleRoute)


def test_point_to_point_wording_does_not_talk_about_destinations():
    a = ProfileOutcome(A, reached=0, requested=0, o2_g=80.0, time_s=600.0)
    c = ProfileOutcome(C, reached=0, requested=0, o2_g=120.0, time_s=300.0)
    _, reason = choose([a, c])
    assert "Both modes reach the end" in reason and "destinations" not in reason
