"""The real per-profile cost and resource formulas (work package E)."""
from app.routing.profiles.astronaut import AstronautModel
from app.routing.profiles.car import CarModel
from app.routing.profiles.params import AstronautParams, CarParams


def default_models() -> list:
    """Both profile models with the built-in placeholder parameters, in the order the graph builder expects."""
    return [AstronautModel(), CarModel()]


def models_from_settings(settings) -> list:
    """Both profile models with the parameters of the configuration file (`Settings.profiles`).

    Parameters the file does not list keep the built-in defaults. The graph builder and the API both call this,
    so the stored graph and the request-time estimates use the same numbers.
    """
    given = getattr(settings, "profiles", None) or {}
    return [AstronautModel(AstronautParams(**given.get("astronaut", {}))), CarModel(CarParams(**given.get("car", {})))]


__all__ = ["AstronautModel", "AstronautParams", "CarModel", "CarParams", "default_models", "models_from_settings"]
