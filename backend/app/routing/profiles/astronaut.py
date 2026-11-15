"""Profile `astronaut`: walking in a suit. Tobler speed, Minetti energy cost (edge-cost-model.md section 5).

Tobler (1993) and Minetti et al. (2002) come from healthy adults on Earth without suits: good for comparing
routes, not for medical prediction. Mars gravity and the suit enter only through calibration factors.
"""
from __future__ import annotations

import numpy as np

from app.core.profiles import EdgeGeometry
from app.core.resources import ProfileId
from app.routing.profiles.params import AstronautParams, versioned

FORMULA_VERSION = "astronaut-tobler-minetti-1-placeholder"
O2_G_PER_L = 1.429  # densities at 0 C, 1 atm
CO2_G_PER_L = 1.977
MINETTI_MAX_GRADIENT = 0.45  # validity range of the polynomial


def tobler_speed_ms(i: np.ndarray, speed_factor: float) -> np.ndarray:
    """Walking speed (m/s) at gradient i: 6 exp(-3.5 |i + 0.05|) km/h."""
    return speed_factor * 6.0 * np.exp(-3.5 * np.abs(i + 0.05)) / 3.6


def minetti_cost(i: np.ndarray) -> np.ndarray:
    """Metabolic cost of walking, J/(kg m), clipped to the polynomial's validity range."""
    g = np.clip(i, -MINETTI_MAX_GRADIENT, MINETTI_MAX_GRADIENT)
    c = 280.5 * g**5 - 58.7 * g**4 - 76.8 * g**3 + 51.9 * g**2 + 19.6 * g + 2.5
    return np.maximum(c, 0.1)  # never <= 0: keeps the cost ratio positive


class AstronautModel:
    profile_id = ProfileId.ASTRONAUT

    def __init__(self, params: AstronautParams | None = None):
        self.params = params or AstronautParams()
        self.formula_version = versioned(FORMULA_VERSION, self.params)

    def compute_edge_attrs(self, geom: EdgeGeometry):
        q = self.params
        length, i, theta = geom.length_m, geom.gradient, geom.theta_rad
        theta_max = np.radians(q.hard_limit_deg)

        v = tobler_speed_ms(i, q.speed_factor)
        v_flat = tobler_speed_ms(np.zeros(1), q.speed_factor)[0]
        c = minetti_cost(i)
        c_flat = minetti_cost(np.zeros(1))[0]
        # Mass, efficiency, suit penalty and gravity factors cancel in e(i) / e_flat.
        margin = 1.0 + (np.abs(theta) / theta_max) ** q.p
        cost = length * margin * (q.alpha * (v_flat / v) + q.beta * (c / c_flat))

        t = length / v
        e_met = c * q.total_mass_kg * q.efficiency_factor * q.suit_mobility_penalty * q.gravity_factor * length  # J
        o2_l = e_met / (q.o2_kj_per_l * 1000.0)
        attrs = {
            "cost": cost,
            "time_s": t,
            "o2_g": o2_l * O2_G_PER_L + q.o2_leak_g_per_s * t,
            "co2_g": q.rq * o2_l * CO2_G_PER_L,
            "water_g": (e_met + q.env_heat_w * t) / q.h_cool_j_per_g,
            "energy_wh": q.p_suit_w * t / 3600.0,
        }
        blocked = np.abs(theta) > theta_max
        return {k: np.where(blocked, np.inf, v_) for k, v_ in attrs.items()}
