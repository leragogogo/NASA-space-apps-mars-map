from pathlib import Path

import pytest
import yaml

from app.core.config import Settings
from app.core.configfile import DEFAULT_CONFIG_PATH, ConfigError, load_settings, read_config
from app.routing.profiles import AstronautModel, AstronautParams, CarParams, default_models, models_from_settings


@pytest.fixture
def shipped() -> dict:
    return yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())


def write(tmp_path: Path, doc: dict, name: str = "cfg.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return path


# ------------------------------------------------------------------ the shipped file
def test_the_shipped_file_loads_and_lists_every_model_parameter(shipped):
    settings = load_settings()
    assert settings.grid_coarsen == 1 and len(settings.slope_classes) == 5
    # "all the configurations we need": every parameter of both models appears in the file
    assert set(shipped["profiles"]["astronaut"]) == set(AstronautParams.__dataclass_fields__)
    assert set(shipped["profiles"]["car"]) == set(CarParams.__dataclass_fields__)


def test_the_shipped_file_starts_unconfirmed_so_the_placeholders_are_visible():
    assert set(load_settings().unconfirmed) == {"slope_classes", "profiles.astronaut", "profiles.car", "capacities",
                                                "weather.risk_bins"}


def test_the_shipped_values_equal_the_built_in_defaults_when_nothing_was_changed():
    # guards against the file and params.py silently drifting while both still hold placeholders
    assert [m.formula_version for m in models_from_settings(load_settings())] == \
           [m.formula_version for m in default_models()]


# ------------------------------------------------------------------ values reach the settings
def test_values_from_the_file_override_the_defaults(tmp_path, shipped):
    shipped["grid"]["coarsen"] = 2
    shipped["routing"] = {"reserve_margin": 0.3, "max_snap_distance_m": 250}
    shipped["poi"]["sample_radius_km"] = 5
    shipped["capacities"] = {"astronaut": {"o2_g": 2000, "time_s": 28800}, "car": {"energy_wh": 20000}}
    s = load_settings(write(tmp_path, shipped))
    assert (s.grid_coarsen, s.reserve_margin, s.max_snap_distance_m, s.poi_sample_radius_km) == (2, 0.3, 250, 5.0)
    assert s.capacities == {"astronaut": {"o2_g": 2000.0, "time_s": 28800.0}, "car": {"energy_wh": 20000.0}}


def test_profile_parameters_from_the_file_reach_the_models(tmp_path, shipped):
    shipped["profiles"]["astronaut"]["suit_mass_kg"] = 65.0
    shipped["profiles"]["car"]["crew_n"] = 3
    astronaut, car = models_from_settings(load_settings(write(tmp_path, shipped)))
    assert astronaut.params.suit_mass_kg == 65.0 and car.params.crew_n == 3
    assert astronaut.formula_version != AstronautModel().formula_version  # so a saved graph becomes stale


def test_parameters_missing_from_the_file_keep_the_built_in_defaults(tmp_path):
    s = load_settings(write(tmp_path, {"profiles": {"astronaut": {"alpha": 0.7, "beta": 0.3}}}))
    astronaut, car = models_from_settings(s)
    assert (astronaut.params.alpha, astronaut.params.suit_mass_kg) == (0.7, AstronautParams().suit_mass_kg)
    assert car.params == CarParams()


def test_overrides_win_over_the_file(tmp_path, shipped):
    s = load_settings(write(tmp_path, shipped), data_dir=tmp_path, grid_coarsen=4, capacities={"car": {"time_s": 1.0}})
    assert s.data_dir == tmp_path and s.grid_coarsen == 4 and s.capacities == {"car": {"time_s": 1.0}}


# ------------------------------------------------------------------ where the file comes from
def test_a_file_that_was_asked_for_but_is_missing_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path / "nope.yaml")
    with pytest.raises(ConfigError, match="not found"):
        read_config(tmp_path / "nope.yaml")


def test_the_environment_variable_selects_the_file(tmp_path, shipped, monkeypatch):
    shipped["grid"]["coarsen"] = 3
    monkeypatch.setenv("MARS_CONFIG", str(write(tmp_path, shipped)))
    assert load_settings().grid_coarsen == 3


def test_a_missing_default_file_falls_back_to_built_in_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.configfile.loader.DEFAULT_CONFIG_PATH", tmp_path / "none.yaml")
    monkeypatch.delenv("MARS_CONFIG", raising=False)
    assert load_settings(data_dir=tmp_path) == Settings(data_dir=tmp_path)


def test_invalid_yaml_and_wrong_shapes_are_reported(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("grid: [unclosed")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_settings(bad)
    bad.write_text("- just\n- a list\n")
    with pytest.raises(ConfigError, match="expected a mapping"):
        load_settings(bad)


# ------------------------------------------------------------------ validation
@pytest.mark.parametrize("change, message", [
    (lambda d: d.update(typo={}), "unknown key"),
    (lambda d: d["grid"].update(coarsen=0), r"grid\.coarsen.*>= 1"),
    (lambda d: d["grid"].update(coarsen=1.5), "whole number"),
    (lambda d: d["routing"].update(reserve_margin=1.0), "below 1"),
    (lambda d: d["routing"].update(max_snap_distance_m="far"), "expected a number"),
    (lambda d: d["profiles"]["astronaut"].update(suit_mas_kg=1), "unknown parameter"),
    (lambda d: d["profiles"]["astronaut"].update(alpha=-1), "alpha"),
    (lambda d: d["profiles"].update(tank={}), "unknown key"),
    (lambda d: d.update(capacities={"astronaut": {"nitrogen_g": 5}}), "unknown key"),
    (lambda d: d.update(capacities={"astronaut": {"o2_g": 0}}), "capacity of 0"),
    (lambda d: d.update(capacities={"astronaut": {"o2_g": -5}}), r">= 0"),
])
def test_bad_values_fail_with_the_key_named(tmp_path, shipped, change, message):
    change(shipped)
    with pytest.raises(ConfigError, match=message):
        load_settings(write(tmp_path, shipped))


@pytest.mark.parametrize("change, message", [
    (lambda c: c.pop(1), "contiguous"),
    (lambda c: c[0].update(min_deg=1), "start at 0"),
    (lambda c: c[1].update(id="easy_walk"), "unique"),
    (lambda c: c[0].update(color="green"), "hex colour"),
    (lambda c: c[0].update(walkable="yes"), "true or false"),
    (lambda c: c[2].update(max_deg=15), "greater than min_deg"),
    (lambda c: c[0].pop("label"), "missing"),
])
def test_bad_slope_classes_are_rejected(tmp_path, shipped, change, message):
    change(shipped["slope_classes"])
    with pytest.raises(ConfigError, match=message):
        load_settings(write(tmp_path, shipped))


def test_slope_classes_must_agree_with_the_profile_limits(tmp_path, shipped):
    shipped["profiles"]["astronaut"]["hard_limit_deg"] = 12.0  # the map would still call 12-20 degrees walkable
    with pytest.raises(ConfigError, match="steepest walkable class ends at 20"):
        load_settings(write(tmp_path, shipped))
    shipped["profiles"]["astronaut"]["hard_limit_deg"] = 20.0
    shipped["profiles"]["car"]["hard_limit_deg"] = 40.0
    with pytest.raises(ConfigError, match="steepest vehicle class ends at 25"):
        load_settings(write(tmp_path, shipped))


def test_changing_a_limit_together_with_the_classes_is_accepted(tmp_path, shipped):
    shipped["profiles"]["astronaut"]["hard_limit_deg"] = 15.0  # a stricter astronaut limit ...
    shipped["slope_classes"][2]["walkable"] = False  # ... with the 15-20 degree class no longer walkable
    assert load_settings(write(tmp_path, shipped)).profiles["astronaut"]["hard_limit_deg"] == 15.0


# ------------------------------------------------------------------ confirming a section
def test_confirming_a_section_needs_a_source(tmp_path, shipped):
    shipped["confirmation"]["slope_classes"] = {"status": "confirmed", "source": ""}
    with pytest.raises(ConfigError, match="must name its source"):
        load_settings(write(tmp_path, shipped))
    shipped["confirmation"]["slope_classes"] = {"status": "confirmed", "source": "Mission planning memo, J. Doe, 2026-12-01"}
    assert "slope_classes" not in load_settings(write(tmp_path, shipped)).unconfirmed


@pytest.mark.parametrize("entry, message", [({"status": "maybe"}, "expected placeholder or confirmed"),
                                            ({"state": "confirmed"}, "unknown key")])
def test_bad_confirmation_entries_are_rejected(tmp_path, shipped, entry, message):
    shipped["confirmation"]["capacities"] = entry
    with pytest.raises(ConfigError, match=message):
        load_settings(write(tmp_path, shipped))


def test_a_section_without_a_confirmation_entry_counts_as_unconfirmed(tmp_path):
    assert set(load_settings(write(tmp_path, {})).unconfirmed) == {"slope_classes", "profiles.astronaut", "profiles.car",
                                                                    "capacities", "weather.risk_bins"}


# ------------------------------------------------------------------ request limits and weather thresholds
def test_request_limits_and_weather_thresholds_reach_the_settings(tmp_path, shipped):
    shipped["routing"].update(max_destinations=40, default_time_limit_s=5, min_time_limit_s=2, max_time_limit_s=60)
    shipped["weather"]["risk_bins"] = {"moderate_from": 2.0, "high_from": 6.0}
    s = load_settings(write(tmp_path, shipped))
    limits = s.route_limits
    assert (limits.max_destinations, limits.default_time_limit_s, limits.min_time_limit_s, limits.max_time_limit_s) \
        == (40, 5.0, 2.0, 60.0)
    assert limits.clamp_time_limit(None) == 5.0 and limits.clamp_time_limit(1000) == 60.0
    assert s.weather_risk_bins == {"moderate_from": 2.0, "high_from": 6.0}


def test_the_built_in_limits_match_the_routing_contract_defaults():
    from app.routing.contracts import RouteLimits
    assert Settings().route_limits == RouteLimits()  # the YAML and the code start from the same numbers
    assert load_settings().route_limits == RouteLimits()


def test_the_graph_is_built_at_startup_in_the_shipped_file_and_not_by_default(tmp_path, shipped):
    assert load_settings().build_graph_on_startup is True
    assert Settings().build_graph_on_startup is False  # code defaults never build by accident (tests, tools)
    shipped["routing"]["build_graph_on_startup"] = False
    assert load_settings(write(tmp_path, shipped)).build_graph_on_startup is False


@pytest.mark.parametrize("change, message", [
    (lambda d: d["routing"].update(build_graph_on_startup="yes"), "true or false"),
    (lambda d: d["routing"].update(max_destinations=0), "max_destinations.*>= 1"),
    (lambda d: d["routing"].update(max_destinations=2.5), "whole number"),
    (lambda d: d["routing"].update(default_time_limit_s=50), "min_time_limit_s <= default_time_limit_s"),
    (lambda d: d["routing"].update(min_time_limit_s=40), "min_time_limit_s <= default_time_limit_s"),
    (lambda d: d["routing"].update(max_time_limit_s=0), "max_time_limit_s"),
    (lambda d: d["weather"]["risk_bins"].update(high_from=0.5), "greater than moderate_from"),
    (lambda d: d["weather"]["risk_bins"].update(moderate_from=-1), "moderate_from"),
    (lambda d: d["weather"]["risk_bins"].update(extreme_from=9), "unknown key"),
    (lambda d: d["weather"].update(colours={}), "unknown key"),
])
def test_bad_limits_and_thresholds_are_rejected(tmp_path, shipped, change, message):
    change(shipped)
    with pytest.raises(ConfigError, match=message):
        load_settings(write(tmp_path, shipped))
