"""Stand-in profile models so the graph can be built and tested before the real cost formulas
exist (work package E). Not physical models: cost = edge length (scaled), resources proportional."""
from __future__ import annotations

import numpy as np

from app.core.profiles import EdgeGeometry
from app.core.resources import EDGE_ATTRS, ProfileId


class StubProfile:
    def __init__(self, profile_id: ProfileId, formula_version: str = "stub-1",
                 hard_limit_deg: float | None = None, scale: float = 1.0):
        self.profile_id = profile_id
        self.formula_version = formula_version
        self.hard_limit_deg = hard_limit_deg
        self.scale = scale

    def compute_edge_attrs(self, geom: EdgeGeometry):
        length = geom.length_m
        attrs = {"cost": length * self.scale, "time_s": length / 1.0, "o2_g": length * 0.1,
                 "co2_g": length * 0.12, "water_g": length * 0.3, "energy_wh": length * 0.01}
        if self.hard_limit_deg is not None:
            blocked = np.abs(np.degrees(geom.theta_rad)) > self.hard_limit_deg
            for name in EDGE_ATTRS:
                attrs[name] = np.where(blocked, np.inf, attrs[name])
        return attrs


def stub_models(astronaut_limit_deg: float | None = 15.0, car_limit_deg: float | None = 35.0):
    return [StubProfile(ProfileId.ASTRONAUT, hard_limit_deg=astronaut_limit_deg),
            StubProfile(ProfileId.CAR, hard_limit_deg=car_limit_deg, scale=2.0)]
