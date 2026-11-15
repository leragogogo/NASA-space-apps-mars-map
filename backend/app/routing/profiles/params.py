"""Parameters of the two profile models.

Every number here is a PLACEHOLDER, not a real suit or rover specification (edge-cost-model.md sections 5-6).
These are the built-in fallbacks. The values actually used come from `config/mars.yaml` (`profiles.<profile>`),
loaded by `app.core.configfile.load_settings` and turned into models by `models_from_settings`; a parameter the
file does not list keeps the default below.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

MARS_G = 3.71  # m/s2


def versioned(base: str, params) -> str:
    """`base` plus a short hash of the parameters, so editing a number marks saved graphs stale."""
    digest = hashlib.sha256(json.dumps(asdict(params), sort_keys=True).encode()).hexdigest()[:8]
    return f"{base}+{digest}"


def _check_weights(alpha: float, beta: float, p: float, limit_deg: float) -> None:
    if alpha < 0 or beta < 0 or alpha + beta <= 0:
        raise ValueError("alpha and beta must be >= 0 and not both 0")
    if p <= 0:
        raise ValueError("p must be > 0")
    if not 0 < limit_deg < 90:
        raise ValueError("hard_limit_deg must be in (0, 90)")


@dataclass(frozen=True)
class AstronautParams:
    # TODO(product owner): confirm the slope limit. 20 deg is the Artemis suit's stated capability (lunar; NASA
    # Exploration EVA Testing and Analogs, 2021). Keep it below ~24 deg: the Minetti model is valid to gradient 0.45.
    hard_limit_deg: float = 20.0
    # TODO(product owner): confirm the cost weights alpha (time) and beta (energy) and the exponent p.
    alpha: float = 0.5
    beta: float = 0.5
    p: float = 2.0
    # TODO(product owner): real suited-astronaut masses. Placeholders.
    body_mass_kg: float = 80.0
    suit_mass_kg: float = 50.0
    gear_mass_kg: float = 20.0
    efficiency_factor: float = 1.0
    # TODO(calibration): empirical values for a pressurised suit on regolith. Placeholders.
    suit_mobility_penalty: float = 1.3
    speed_factor: float = 0.6
    gravity_factor: float = 1.0
    # TODO(product owner / suit spec): suit power, leak, environment heat and cooling. Placeholders.
    p_suit_w: float = 150.0
    o2_leak_g_per_s: float = 0.001
    env_heat_w: float = 100.0
    h_cool_j_per_g: float = 2400.0  # latent heat of water, sublimator cooling (approximate)
    rq: float = 0.85  # respiratory quotient
    o2_kj_per_l: float = 20.1  # energy per litre of O2 consumed

    def __post_init__(self):
        _check_weights(self.alpha, self.beta, self.p, self.hard_limit_deg)
        for name in ("body_mass_kg", "speed_factor", "h_cool_j_per_g", "o2_kj_per_l", "efficiency_factor",
                     "suit_mobility_penalty", "gravity_factor"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        for name in ("suit_mass_kg", "gear_mass_kg", "p_suit_w", "o2_leak_g_per_s", "env_heat_w", "rq"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")

    @property
    def total_mass_kg(self) -> float:
        return self.body_mass_kg + self.suit_mass_kg + self.gear_mass_kg


@dataclass(frozen=True)
class CarParams:
    # TODO(product owner): confirm the slope limit. 25 deg is the Apollo rover's design maximum (lunar; LPSC 2026
    # abstract); a pressurized rover may need less.
    hard_limit_deg: float = 25.0
    # TODO(product owner): confirm the cost weights and the exponent p.
    alpha: float = 0.5
    beta: float = 0.5
    p: float = 2.0
    # TODO(product owner): real rover specification. Placeholders.
    mass_kg: float = 1000.0
    c_rr: float = 0.25  # rolling resistance on regolith
    eta_drive: float = 0.6
    v_max_ms: float = 4.0
    v_min_ms: float = 0.5
    p_speed: float = 2.0
    p_aux_w: float = 500.0
    # TODO(product owner): crew size and per-person rates (seated, pressurised cabin assumed). Placeholders.
    crew_n: int = 2
    crew_o2_g_per_s: float = 0.0097
    crew_co2_g_per_s: float = 0.0116
    crew_water_g_per_s: float = 0.035

    def __post_init__(self):
        _check_weights(self.alpha, self.beta, self.p, self.hard_limit_deg)
        if not 0 < self.v_min_ms <= self.v_max_ms:
            raise ValueError("need 0 < v_min_ms <= v_max_ms")
        for name in ("mass_kg", "c_rr", "eta_drive", "p_speed"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        for name in ("p_aux_w", "crew_o2_g_per_s", "crew_co2_g_per_s", "crew_water_g_per_s"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")
        if self.crew_n < 0:
            raise ValueError("crew_n must be >= 0")
