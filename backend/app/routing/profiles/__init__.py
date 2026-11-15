"""The real per-profile cost and resource formulas (work package E)."""
from app.routing.profiles.astronaut import AstronautModel
from app.routing.profiles.car import CarModel
from app.routing.profiles.params import AstronautParams, CarParams


def default_models() -> list:
    """Both profile models with their placeholder parameters, in the order the graph builder expects."""
    return [AstronautModel(), CarModel()]


__all__ = ["AstronautModel", "AstronautParams", "CarModel", "CarParams", "default_models"]
