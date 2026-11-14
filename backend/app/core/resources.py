"""Profile ids, edge attribute names and units shared by graph, routing and the API.

Single source of truth: adding a resource means adding its name here (and a formula per
profile); the graph arrays are generic over these names.
See context/skills/mars-mvp-data/references/edge-cost-model.md.
"""
from __future__ import annotations

from enum import StrEnum


class ProfileId(StrEnum):
    ASTRONAUT = "astronaut"
    CAR = "car"


PROFILES: tuple[ProfileId, ...] = tuple(ProfileId)

COST = "cost"
RESOURCES: tuple[str, ...] = ("time_s", "o2_g", "co2_g", "water_g", "energy_wh")
EDGE_ATTRS: tuple[str, ...] = (COST, *RESOURCES)

UNITS: dict[str, str] = {
    COST: "flat-equivalent m",
    "time_s": "s",
    "o2_g": "g",
    "co2_g": "g",
    "water_g": "g",
    "energy_wh": "Wh",
}

SEP = "__"


def attr_key(profile: ProfileId | str, attr: str) -> str:
    """Array name used in storage, e.g. ('astronaut', 'o2_g') -> 'astronaut__o2_g'."""
    if attr not in EDGE_ATTRS:
        raise ValueError(f"unknown edge attribute {attr!r}; expected one of {EDGE_ATTRS}")
    return f"{ProfileId(profile).value}{SEP}{attr}"


def split_attr_key(key: str) -> tuple[ProfileId, str]:
    profile, sep, attr = key.partition(SEP)
    if not sep or attr not in EDGE_ATTRS:
        raise ValueError(f"not an edge attribute key: {key!r}")
    return ProfileId(profile), attr
