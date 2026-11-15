"""Profile `car`: a pressurised rover. Slope-limited speed, traction energy (edge-cost-model.md section 6)."""
from __future__ import annotations

import numpy as np

from app.core.profiles import EdgeGeometry
from app.core.resources import ProfileId
from app.routing.profiles.params import MARS_G, CarParams, versioned

FORMULA_VERSION = "car-traction-1-placeholder"


class CarModel:
    profile_id = ProfileId.CAR

    def __init__(self, params: CarParams | None = None):
        self.params = params or CarParams()
        self.formula_version = versioned(FORMULA_VERSION, self.params)

    def speed_ms(self, theta: np.ndarray) -> np.ndarray:
        q = self.params
        frac = np.clip(np.abs(theta) / np.radians(q.hard_limit_deg), 0.0, 1.0)
        return np.maximum(q.v_min_ms, q.v_max_ms * (1.0 - frac**q.p_speed))

    def compute_edge_attrs(self, geom: EdgeGeometry):
        q = self.params
        length, theta = geom.length_m, geom.theta_rad
        theta_max = np.radians(q.hard_limit_deg)

        v = self.speed_ms(theta)
        t = length / v
        force = q.mass_kg * MARS_G * (q.c_rr * np.cos(theta) + np.sin(theta))  # signed: downhill helps
        e_trac = np.maximum(0.0, force * length / q.eta_drive)  # J; no regeneration credit in the MVP
        e_per_m = e_trac / length
        e_flat = q.mass_kg * MARS_G * q.c_rr / q.eta_drive
        margin = 1.0 + (np.abs(theta) / theta_max) ** q.p
        cost = length * margin * (q.alpha * (q.v_max_ms / v) + q.beta * (e_per_m / e_flat))

        attrs = {
            "cost": cost,
            "time_s": t,
            "o2_g": q.crew_n * q.crew_o2_g_per_s * t,
            "co2_g": q.crew_n * q.crew_co2_g_per_s * t,
            "water_g": q.crew_n * q.crew_water_g_per_s * t,
            "energy_wh": (e_trac + q.p_aux_w * t) / 3600.0,
        }
        blocked = np.abs(theta) > theta_max
        return {k: np.where(blocked, np.inf, v_) for k, v_ in attrs.items()}
