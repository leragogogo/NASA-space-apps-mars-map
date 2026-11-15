"""Profile `astronaut`: walking in a suit. Tobler speed, Minetti energy cost (edge-cost-model.md section 5).

Tobler (1993) and Minetti et al. (2002) come from healthy adults on Earth without suits: good for comparing
routes, not for medical prediction. Mars gravity and the suit enter only through calibration factors.
"""
from __future__ import annotations

import numpy as np

from app.core.profiles import EdgeGeometry
from app.core.resources import ProfileId
from app.routing.profiles.params import AstronautParams, versioned
from app.routing.profiles.terrain import dune_factor, effective_slope_rad, hazard_blocked, roughness_factor

FORMULA_VERSION = "astronaut-tobler-minetti-2-placeholder"
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

    def resources(self, geom: EdgeGeometry, body_mass_kg: float | None = None) -> dict[str, np.ndarray]:
        """Time and consumption per edge for an astronaut of `body_mass_kg` (default: the reference mass).

        Only oxygen, CO2 and cooling water depend on mass (they follow the metabolic energy, which is linear
        in total mass); time and suit energy do not. The graph builder calls this with the reference mass,
        and the API calls it again for the requesting user's mass, so the two cannot drift apart.
        The route cost does not use mass at all (see `compute_edge_attrs`).
        """
        q = self.params
        mass = q.body_mass_kg if body_mass_kg is None else float(body_mass_kg)
        if mass <= 0:
            raise ValueError("body_mass_kg must be > 0")
        total_kg = mass + q.suit_mass_kg + q.gear_mass_kg
        length, i = geom.length_m, geom.gradient
        t = length / tobler_speed_ms(i, q.speed_factor)
        e_met = minetti_cost(i) * total_kg * q.efficiency_factor * q.suit_mobility_penalty * q.gravity_factor * length  # J
        o2_l = e_met / (q.o2_kj_per_l * 1000.0)
        return {
            "time_s": t,
            "o2_g": o2_l * O2_G_PER_L + q.o2_leak_g_per_s * t,
            "co2_g": q.rq * o2_l * CO2_G_PER_L,
            "water_g": (e_met + q.env_heat_w * t) / q.h_cool_j_per_g,
            "energy_wh": q.p_suit_w * t / 3600.0,
        }

    def compute_edge_attrs(self, geom: EdgeGeometry):
        q = self.params
        length, i = geom.length_m, geom.gradient
        theta_max = np.radians(q.hard_limit_deg)
        slope = effective_slope_rad(geom)  # travel gradient or the map slope across it, whichever is steeper

        v = tobler_speed_ms(i, q.speed_factor)
        v_flat = tobler_speed_ms(np.zeros(1), q.speed_factor)[0]
        c = minetti_cost(i)
        c_flat = minetti_cost(np.zeros(1))[0]
        # Mass, efficiency, suit penalty and gravity factors cancel in e(i) / e_flat, so the cost (and the
        # route) is the same for every astronaut.
        margin = 1.0 + (slope / theta_max) ** q.p
        terrain = roughness_factor(geom, q.roughness_weight, q.roughness_ref_m) * dune_factor(geom, q.dune_penalty)
        cost = length * margin * terrain * (q.alpha * (v_flat / v) + q.beta * (c / c_flat))

        attrs = {"cost": cost, **self.resources(geom)}
        blocked = (slope > theta_max) | hazard_blocked(geom, q.dune_blocked, q.rsl_blocked)
        return {k: np.where(blocked, np.inf, v_) for k, v_ in attrs.items()}
