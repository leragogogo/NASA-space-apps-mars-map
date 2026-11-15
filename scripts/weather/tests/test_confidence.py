import numpy as np
import pandas as pd
import pytest

from weather import config as cfg
from weather.confidence import (evaluate, grid_frames, message, observation_gaps, observed_years,
                                poisson_ci, risk_of)
from weather.tests.helpers import storms

NO_GAPS = pd.DataFrame(columns=["my", "ls_from", "ls_to"])
WINTER = cfg.SEASON_NAMES[1]
AUTUMN = cfg.SEASON_NAMES[0]


def test_risk_bins():
    assert [risk_of(x) for x in (0, 0.99, 1.0, 3.99, 4.0, 100)] == ["Low", "Low", "Moderate", "Moderate", "High", "High"]


def test_poisson_ci():
    lo, hi = poisson_ci(0, 1.0)
    assert lo == 0.0 and hi == pytest.approx(3.689, abs=1e-3)
    lo, hi = poisson_ci(10, 5.0)
    assert lo < 10 / 5.0 < hi


def test_observed_years_without_gaps():
    y = observed_years(NO_GAPS, lat=-12.0)
    assert y[WINTER] == 8.23  # MY24 from Ls150, MY32 to Ls171 (matches the documented AOI value)
    assert y[AUTUMN] == 8.0
    polar = observed_years(NO_GAPS, lat=70.0)  # MOC-era maps stop at 60 deg: MY24-27 excluded
    assert polar[WINTER] < y[WINTER] and polar[WINTER] == pytest.approx(5.0 - 0.1, abs=0.2)


def test_gaps_reduce_observed_years():
    gaps = pd.DataFrame([dict(my=30, ls_from=90, ls_to=180)])
    assert observed_years(gaps, -12.0)[WINTER] == pytest.approx(7.23)


def test_observation_gaps_detected():
    rows = [(my, float(ls), 0.0, 0.0, f"s{my}_{ls}", "no") for my in range(25, 28) for ls in range(0, 360, 5)
            if not (my == 26 and 100 <= ls < 125)]
    gaps = observation_gaps(storms(rows))
    g = gaps[gaps.my == 26]
    assert g.ls_from.tolist() == [100] and g.ls_to.tolist() == [125]
    assert gaps[gaps.my != 26].empty


def test_evaluate_insufficient_when_few_years():
    f = evaluate(storms([]), years=2.0)
    assert f["confidence"] == "insufficient_data" and "rate" not in f and "risk" not in f


def test_evaluate_reliable_zero_storms_keeps_upper_bound_reason():
    f = evaluate(storms([]), years=8.0)
    assert f["confidence"] == "reliable" and f["risk"] == "Low" and f["storm_days"] == 0
    assert "no storms in 8.0 observed Mars years" in f["reasons"][0]


def test_evaluate_reliable_needs_years_and_storms():
    rows = [(24 + i % 8, 100.0 + i, 0.0, 0.0, f"s{i}", "no") for i in range(6)]  # 6 storms, spread over years
    assert evaluate(storms(rows), years=8.0)["confidence"] == "reliable"
    assert evaluate(storms(rows), years=5.0)["confidence"] == "approximate"  # < 6 observed years
    few = rows[:3]
    f = evaluate(storms(few), years=8.0)
    assert f["confidence"] == "approximate" and any("too few" in r for r in f["reasons"])


def test_evaluate_single_year_dominance_reports_typical_and_extreme():
    rows = [(25, 100.0 + i, 0.0, 0.0, f"a{i}", "no") for i in range(30)] + [(27, 100.0, 0.0, 0.0, "b0", "no")]
    f = evaluate(storms(rows), years=8.0)
    assert f["confidence"] == "approximate"
    assert f["extreme_year"] == dict(my=25, storm_days=30, risk="High")
    assert f["typical_year_risk"] == "Low" and f["risk"] == "Moderate"  # 31 storm-days / 8 yrs = 3.9
    assert "MY25" in message(f, WINTER, "here")


def test_evaluate_missing_data_share_makes_it_approximate():
    rows = [(24 + i % 8, 100.0 + i, 0.0, 0.0, f"s{i}", "yes") for i in range(8)]
    f = evaluate(storms(rows), years=8.0)
    assert f["confidence"] == "approximate" and any("missing data" in r for r in f["reasons"])


def test_messages_for_each_confidence():
    rel = evaluate(storms([(24 + i % 8, 100.0 + i, 0, 0, f"s{i}", "no") for i in range(6)]), 8.0)
    assert message(rel, WINTER, "here").startswith(f"{rel['risk']} dust-storm risk in S. Winter")
    ins = evaluate(storms([]), 2.0)
    assert message(ins, WINTER, "here").startswith("NOT ENOUGH DATA")
    assert "No approximate estimate is possible" in message(ins, WINTER, "here")
    ins["neighbour_estimate"] = dict(rate=2.5, risk="Moderate", n_frames=3)
    assert "Approximate estimate from 3 neighbouring frames: Moderate" in message(ins, WINTER, "here")
    appr = evaluate(storms([(24, 100.0, 0, 0, "a", "no")]), 8.0)
    assert message(appr, WINTER, "here").startswith("APPROXIMATE: not enough data")


def test_grid_frames_shape_ordering_and_messages():
    d = storms([(26, 100.0, -70.0, -12.0, "a", "no")])
    frames = grid_frames(d, NO_GAPS, (-72, -14, -68, -10), 1.0)
    assert len(frames) == 4 * 4 * 4  # 4x4 cells x 4 seasons
    assert frames[0]["lon"] == -71.5 and frames[0]["lat"] == -13.5 and frames[0]["season"] == cfg.SEASON_NAMES[0]
    assert all(f["message"] for f in frames) and "typical_year_risk" not in frames[0]
    assert {f["confidence"] for f in frames} <= {"reliable", "approximate", "insufficient_data"}


def test_grid_frames_fills_neighbour_estimate_for_insufficient_frames():
    # make every season of MY28-32 unobserved: low latitudes keep MY24-27, polar frames (> 60) keep nothing
    gaps = pd.DataFrame([dict(my=m, ls_from=0, ls_to=360) for m in range(28, 33)])
    d = storms([(26, 100.0, 0.0, 59.5, "a", "no")])
    frames = grid_frames(d, gaps, (-1, 58, 1, 63), 1.0)
    polar = [f for f in frames if f["lat"] > 60 and f["season"] == WINTER]
    low = [f for f in frames if f["lat"] < 60 and f["season"] == WINTER]
    assert all(f["confidence"] == "insufficient_data" for f in polar)
    assert low and all(f["confidence"] != "insufficient_data" for f in low)
    near = [f for f in polar if f["lat"] <= 61.5]
    assert near and all("neighbour_estimate" in f for f in near)
    assert all("Approximate estimate from" in f["message"] for f in near)
