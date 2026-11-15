"""Read config/mars.yaml into `Settings`, failing clearly on anything that does not make sense.

The file is the single place for the numbers a product owner may change: profile parameters, budgets, slope
classes and a few routing limits. Defaults in code (`Settings`, `params.py`) only apply when no file is used.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

from app.core.config import REPO_ROOT, STATUS_CONFIRMED, STATUS_PLACEHOLDER, Settings, SlopeClass
from app.core.resources import PROFILES, RESOURCES
from app.routing.profiles.params import AstronautParams, CarParams

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "mars.yaml"
ENV_VAR = "MARS_CONFIG"
PARAM_CLASSES = {"astronaut": AstronautParams, "car": CarParams}
SECTIONS = ("grid", "routing", "poi", "weather", "capacities", "slope_classes", "profiles", "confirmation")
KNOWN_CONFIRMATIONS = ("slope_classes", "profiles.astronaut", "profiles.car", "capacities", "weather.risk_bins")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class ConfigError(ValueError):
    """The configuration file is missing, unreadable or inconsistent. The message names the file and the key."""


def _fail(where: str, message: str):
    raise ConfigError(f"{where}: {message}")


def _mapping(value: Any, where: str, allowed: tuple[str, ...] | None = None) -> Mapping:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        _fail(where, f"expected a mapping, got {type(value).__name__}")
    if allowed is not None and (extra := sorted(set(value) - set(allowed))):
        _fail(where, f"unknown key(s) {extra}; allowed: {list(allowed)}")
    return value


def _number(value: Any, where: str, minimum: float | None = None, integer: bool = False) -> float:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not ok or (integer and int(value) != value):
        _fail(where, f"expected a {'whole ' if integer else ''}number, got {value!r}")
    if minimum is not None and value < minimum:
        _fail(where, f"must be >= {minimum}, got {value}")
    return int(value) if integer else float(value)


def read_config(path: Path) -> dict:
    """The parsed YAML as a dict (validated for shape only; `load_settings` validates the content)."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"{path}: configuration file not found")
    try:
        doc = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as ex:
        raise ConfigError(f"{path}: not valid YAML ({ex})") from ex
    return dict(_mapping(doc, str(path), SECTIONS))


def _slope_classes(raw: Any, where: str) -> tuple[SlopeClass, ...]:
    if not isinstance(raw, list) or not raw:
        _fail(where, "expected a non-empty list of classes")
    fields = ("id", "label", "min_deg", "max_deg", "color", "walkable", "vehicle")
    classes = []
    for i, item in enumerate(raw):
        w = f"{where}[{i}]"
        item = _mapping(item, w, fields)
        if missing := [f for f in fields if f not in item]:
            _fail(w, f"missing {missing}")
        if not _HEX.match(str(item["color"])):
            _fail(f"{w}.color", f"expected a hex colour like #1a9850, got {item['color']!r}")
        for flag in ("walkable", "vehicle"):
            if not isinstance(item[flag], bool):
                _fail(f"{w}.{flag}", f"expected true or false, got {item[flag]!r}")
        classes.append(SlopeClass(str(item["id"]), str(item["label"]), _number(item["min_deg"], f"{w}.min_deg", 0),
                                  _number(item["max_deg"], f"{w}.max_deg", 0), str(item["color"]),
                                  item["walkable"], item["vehicle"]))
    if len({c.id for c in classes}) != len(classes):
        _fail(where, "class ids must be unique")
    for c in classes:
        if c.max_deg <= c.min_deg:
            _fail(where, f"class {c.id}: max_deg must be greater than min_deg")
    if classes[0].min_deg != 0:
        _fail(where, "the first class must start at 0 degrees")
    for a, b in zip(classes, classes[1:]):
        if a.max_deg != b.min_deg:
            _fail(where, f"classes must be contiguous: {a.id} ends at {a.max_deg} but {b.id} starts at {b.min_deg}")
    return tuple(classes)


def _profiles(raw: Any, where: str) -> dict[str, dict]:
    out = {}
    for name, params in _mapping(raw, where, tuple(PARAM_CLASSES)).items():
        params = _mapping(params, f"{where}.{name}")
        cls = PARAM_CLASSES[name]
        valid = tuple(cls.__dataclass_fields__)
        if extra := sorted(set(params) - set(valid)):
            _fail(f"{where}.{name}", f"unknown parameter(s) {extra}; allowed: {list(valid)}")
        try:
            cls(**params)  # the parameter classes validate their own ranges
        except (TypeError, ValueError) as ex:
            _fail(f"{where}.{name}", str(ex))
        out[name] = dict(params)
    return out


def _capacities(raw: Any, where: str) -> dict[str, dict[str, float]]:
    out = {}
    for profile, budget in _mapping(raw, where, tuple(PARAM_CLASSES)).items():
        budget = _mapping(budget, f"{where}.{profile}", RESOURCES)
        out[profile] = {r: _number(v, f"{where}.{profile}.{r}", 0) for r, v in budget.items()}
        if any(v == 0 for v in out[profile].values()):
            _fail(f"{where}.{profile}", "a capacity of 0 would flag every route; omit the resource instead")
    return out


def _confirmation(raw: Any, where: str) -> tuple[str, ...]:
    """The sections not yet signed off. A confirmed section must name its source."""
    entries = _mapping(raw, where, KNOWN_CONFIRMATIONS)
    unconfirmed = []
    for section in KNOWN_CONFIRMATIONS:
        entry = _mapping(entries.get(section), f"{where}.{section}", ("status", "source"))
        status = entry.get("status", STATUS_PLACEHOLDER)
        if status not in (STATUS_PLACEHOLDER, STATUS_CONFIRMED):
            _fail(f"{where}.{section}.status", f"expected {STATUS_PLACEHOLDER} or {STATUS_CONFIRMED}, got {status!r}")
        if status == STATUS_CONFIRMED and not str(entry.get("source") or "").strip():
            _fail(f"{where}.{section}", "a confirmed section must name its source (document, person, date)")
        if status != STATUS_CONFIRMED:
            unconfirmed.append(section)
    return tuple(unconfirmed)


def _check_slope_limits(classes: tuple[SlopeClass, ...], profiles: Mapping[str, dict], where: str) -> None:
    """The overlay and the router must agree on what is walkable and drivable."""
    limits = {name: profiles.get(name, {}).get("hard_limit_deg", PARAM_CLASSES[name]().hard_limit_deg)
              for name in PARAM_CLASSES}
    for name, flag in (("astronaut", "walkable"), ("car", "vehicle")):
        top = max((c.max_deg for c in classes if getattr(c, flag)), default=0.0)
        if top != limits[name]:
            _fail(where, f"the steepest {flag} class ends at {top} degrees but profiles.{name}.hard_limit_deg is "
                         f"{limits[name]}: the map would show something the router does not do")


def load_settings(config_path: Path | str | None = None, **overrides) -> Settings:
    """`Settings` from the YAML file, then `overrides` (for example `data_dir`) on top.

    The path is `config_path`, else the MARS_CONFIG environment variable, else config/mars.yaml. A missing
    default file means built-in defaults; a missing file that was asked for is an error.
    """
    explicit = config_path or os.environ.get(ENV_VAR)
    path = Path(explicit) if explicit else DEFAULT_CONFIG_PATH
    if not path.is_file():
        if explicit:
            raise ConfigError(f"{path}: configuration file not found")
        log.warning("No configuration file at %s: using built-in placeholder defaults", path)
        return Settings(**overrides)

    doc, where = read_config(path), str(path)
    kwargs: dict[str, Any] = {}
    grid = _mapping(doc.get("grid"), f"{where}: grid", ("coarsen",))
    if "coarsen" in grid:
        kwargs["grid_coarsen"] = _number(grid["coarsen"], f"{where}: grid.coarsen", 1, integer=True)
    routing_keys = ("reserve_margin", "max_snap_distance_m", "max_destinations", "default_time_limit_s",
                    "min_time_limit_s", "max_time_limit_s")
    routing = _mapping(doc.get("routing"), f"{where}: routing", routing_keys)
    if "reserve_margin" in routing:
        margin = _number(routing["reserve_margin"], f"{where}: routing.reserve_margin", 0)
        if margin >= 1:
            _fail(f"{where}: routing.reserve_margin", "must be below 1 (it is a share of the budget)")
        kwargs["reserve_margin"] = margin
    if "max_snap_distance_m" in routing:
        kwargs["max_snap_distance_m"] = _number(routing["max_snap_distance_m"], f"{where}: routing.max_snap_distance_m", 1)
    if "max_destinations" in routing:
        kwargs["max_destinations"] = _number(routing["max_destinations"], f"{where}: routing.max_destinations", 1, integer=True)
    for key in ("default_time_limit_s", "min_time_limit_s", "max_time_limit_s"):
        if key in routing:
            kwargs[key] = _number(routing[key], f"{where}: routing.{key}", 0.001)
    lo, default, hi = (kwargs.get(k, getattr(Settings, k)) for k in ("min_time_limit_s", "default_time_limit_s",
                                                                       "max_time_limit_s"))
    if not lo <= default <= hi:
        _fail(f"{where}: routing", f"need min_time_limit_s <= default_time_limit_s <= max_time_limit_s, "
                                   f"got {lo} / {default} / {hi}")
    poi = _mapping(doc.get("poi"), f"{where}: poi", ("sample_radius_km",))
    if "sample_radius_km" in poi:
        kwargs["poi_sample_radius_km"] = _number(poi["sample_radius_km"], f"{where}: poi.sample_radius_km", 0.001)
    weather = _mapping(doc.get("weather"), f"{where}: weather", ("risk_bins",))
    if "risk_bins" in weather:
        bins = _mapping(weather["risk_bins"], f"{where}: weather.risk_bins", ("moderate_from", "high_from"))
        moderate = _number(bins.get("moderate_from", 1.0), f"{where}: weather.risk_bins.moderate_from", 0.001)
        high = _number(bins.get("high_from", 4.0), f"{where}: weather.risk_bins.high_from", 0.001)
        if high <= moderate:
            _fail(f"{where}: weather.risk_bins", f"high_from ({high}) must be greater than moderate_from ({moderate})")
        kwargs["weather_risk_bins"] = {"moderate_from": moderate, "high_from": high}
    kwargs["capacities"] = _capacities(doc.get("capacities"), f"{where}: capacities")
    profiles = _profiles(doc.get("profiles"), f"{where}: profiles")
    kwargs["profiles"] = profiles
    if "slope_classes" in doc:
        classes = _slope_classes(doc["slope_classes"], f"{where}: slope_classes")
        _check_slope_limits(classes, profiles, where)
        kwargs["slope_classes"] = classes
    kwargs["unconfirmed"] = _confirmation(doc.get("confirmation"), f"{where}: confirmation")
    return Settings(**{**kwargs, **overrides})
